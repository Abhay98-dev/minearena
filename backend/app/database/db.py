"""SQLite audit store (stdlib). Stores ONLY sanitized payload + metadata. Never originals/mappings."""
import json
import sqlite3
import threading
from contextlib import contextmanager
from typing import List, Optional

from app.core import config

_LOCK = threading.Lock()
_COLS = ("request_id", "timestamp", "status", "provider", "model", "entity_types", "sanitized_payload",
         "leakage_count", "missing_count", "llm_time_ms", "processing_time_ms", "gateway_overhead_ms", "error_code")


@contextmanager
def _conn():
    c = sqlite3.connect(config.AUDIT_DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db() -> None:
    with _LOCK, _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS audit_logs (
            request_id TEXT PRIMARY KEY, timestamp TEXT, status TEXT, provider TEXT, model TEXT,
            entity_types TEXT, sanitized_payload TEXT, leakage_count INTEGER, missing_count INTEGER,
            llm_time_ms INTEGER, processing_time_ms INTEGER, gateway_overhead_ms INTEGER, error_code TEXT)""")


def save_audit(rec: dict) -> None:
    row = dict(rec)
    row["entity_types"] = json.dumps(row.get("entity_types", []))
    with _LOCK, _conn() as c:
        c.execute(f"INSERT OR REPLACE INTO audit_logs ({','.join(_COLS)}) VALUES ({','.join('?' * len(_COLS))})",
                  [row.get(k) for k in _COLS])


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["entity_types"] = json.loads(d["entity_types"] or "[]")
    return d


def list_audit(limit: int = 100) -> List[dict]:
    with _LOCK, _conn() as c:
        return [_row(r) for r in c.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?", (limit,))]


def get_audit(request_id: str) -> Optional[dict]:
    with _LOCK, _conn() as c:
        r = c.execute("SELECT * FROM audit_logs WHERE request_id=?", (request_id,)).fetchone()
        return _row(r) if r else None


def metrics() -> dict:
    with _LOCK, _conn() as c:
        r = c.execute("""SELECT COUNT(*) n,
            SUM(status='success') ok, SUM(status='blocked') blocked, SUM(status='error') err,
            COALESCE(SUM(leakage_count),0) leaks,
            AVG(processing_time_ms) avg_total, AVG(gateway_overhead_ms) avg_overhead, AVG(llm_time_ms) avg_llm
            FROM audit_logs""").fetchone()
        return {k: (round(v, 1) if isinstance(v, float) else (v or 0)) for k, v in dict(r).items()}
