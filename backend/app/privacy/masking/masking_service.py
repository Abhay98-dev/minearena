"""Mask detected spans with consistent typed placeholders (right-to-left, span based)."""
import re
from collections import defaultdict
from typing import Dict, List

from ..detection.detection_service import detect, resolve_overlaps
from ..mapping import mapping_store
from ..schemas import Span


def _propagate(text: str, spans: List[Span]) -> List[Span]:
    """Also mask other occurrences of already-detected values (catches repeats the detector missed).
    For multi-word PERSON values, lone name tokens are masked too, unless the token belongs to
    two different people (then it is ambiguous and left to the detector)."""
    extra: List[Span] = []
    values: Dict[tuple, str] = {}
    for s in spans:
        values[(s.type, mapping_store.normalize(s.type, text[s.start:s.end]))] = text[s.start:s.end]

    needles: Dict[str, str] = {}  # surface -> type
    for (typ, _), surface in values.items():
        if typ in ("AADHAAR", "PAN", "GSTIN", "VOTER_ID", "PASSPORT", "EMAIL_ADDRESS", "PHONE_NUMBER"):
            continue  # structured IDs are format-detected everywhere already
        needles[surface] = typ

    tok_owner: Dict[str, set] = defaultdict(set)
    for surface, typ in list(needles.items()):
        if typ == "PERSON":
            for tok in surface.split():
                # Lowercase names are valid too; ambiguity across two people
                # is still checked by tok_owner before propagating a lone token.
                if len(tok) >= 3 and (tok[0].isupper() or surface.islower()):
                    tok_owner[tok].add(surface.casefold())
    for tok, owners in tok_owner.items():
        if len(owners) == 1 and tok not in needles:
            needles[tok] = "PERSON"

    for surface, typ in needles.items():
        rx = re.compile(r"(?<![A-Za-z0-9])" + re.escape(surface) + r"(?![A-Za-z0-9])", re.I)
        for m in rx.finditer(text):
            extra.append(Span(m.start(), m.end(), typ, 0.7, "propagated"))
    return extra


def sanitize(text: str, request_id: str) -> dict:
    spans = detect(text)
    spans = resolve_overlaps(spans + _propagate(text, spans), text)
    handle = mapping_store.create(request_id)
    entry = mapping_store.get(handle)

    entities = []
    assigned = []
    for s in spans:  # left-to-right so numbering follows first appearance
        ph = entry.placeholder_for(s.type, text[s.start:s.end])
        assigned.append((s, ph))
        entities.append({"type": s.type, "placeholder": ph, "start": s.start, "end": s.end,
                         "confidence": round(s.confidence, 3)})

    out = text
    for s, ph in sorted(assigned, key=lambda x: x[0].start, reverse=True):  # right-to-left keeps offsets valid
        out = out[:s.start] + ph + out[s.end:]
    return {"sanitized_text": out, "entities": entities, "mapping_handle": handle}
