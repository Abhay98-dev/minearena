"""Request-scoped, thread-safe, in-memory mapping store. One MappingEntry per request.
Never log or return the contents. Destroyed by destroy_mapping() (gateway calls it in `finally`)."""
import re
import threading
import time
import uuid
from typing import Dict, List, Optional

TTL_SECONDS = 900  # safety net: purge forgotten mappings after 15 min


class MappingNotFound(KeyError):
    pass


def normalize(entity_type: str, value: str) -> str:
    if entity_type == "AADHAAR":
        return re.sub(r"\D", "", value)
    if entity_type in ("PAN", "GSTIN", "VOTER_ID", "PASSPORT"):
        return re.sub(r"\s+", "", value).upper()
    return " ".join(value.split()).casefold()  # PERSON / ADDRESS


class MappingEntry:
    def __init__(self, request_id: str):
        self.request_id = request_id
        self.created = time.time()
        self._lock = threading.Lock()
        self.counters: Dict[str, int] = {}
        self.by_key: Dict[tuple, str] = {}       # (type, normalized) -> placeholder
        self.original: Dict[str, str] = {}       # placeholder -> first surface form
        self.types: Dict[str, str] = {}          # placeholder -> type
        self.surfaces: List[tuple] = []          # (placeholder, type, surface form) for leakage guard

    def placeholder_for(self, entity_type: str, value: str) -> str:
        key = (entity_type, normalize(entity_type, value))
        with self._lock:
            ph = self.by_key.get(key)
            if ph is None:
                n = self.counters.get(entity_type, 0) + 1
                self.counters[entity_type] = n
                ph = f"<{entity_type}_{n}>"
                self.by_key[key] = ph
                self.original[ph] = value
                self.types[ph] = entity_type
            if (ph, entity_type, value) not in self.surfaces:
                self.surfaces.append((ph, entity_type, value))
            return ph


_STORE: Dict[str, MappingEntry] = {}
_GLOBAL_LOCK = threading.Lock()


def _purge_expired() -> None:
    now = time.time()
    for h in [h for h, e in _STORE.items() if now - e.created > TTL_SECONDS]:
        _STORE.pop(h, None)


def create(request_id: str) -> str:
    handle = "mh_" + uuid.uuid4().hex
    with _GLOBAL_LOCK:
        _purge_expired()
        _STORE[handle] = MappingEntry(request_id)
    return handle


def get(handle: str) -> MappingEntry:
    with _GLOBAL_LOCK:
        entry = _STORE.get(handle)
    if entry is None:
        raise MappingNotFound("mapping handle not found or expired")
    return entry


def destroy(handle: str) -> None:
    with _GLOBAL_LOCK:
        _STORE.pop(handle, None)


def active_count() -> int:  # for tests / health
    with _GLOBAL_LOCK:
        return len(_STORE)
