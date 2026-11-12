"""Gateway orchestration (Member 1). Order is security-critical - do not reorder:
validate -> sanitize -> guard(exact outbound payload) -> LLM(sanitized only) -> reinsert -> audit -> destroy mapping."""
import asyncio
import time
from datetime import datetime, timezone

from app.core import config
from app.core.errors import GatewayError
from app.database import db
from app.privacy import destroy_mapping, reinsert_placeholders, sanitize_document, validate_outbound_payload
from app.services.llm.base import LLMError, LLMTimeout
from app.services.llm.factory import get_provider

TASKS = ("summarize", "extract")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


async def _call_llm(provider, payload_text: str, task: str, request_id: str):
    """Returns (text, provider_used, fallback_used). Fallback also receives sanitized text only."""
    try:
        return await asyncio.wait_for(provider.generate(payload_text, task), config.LLM_TIMEOUT_S + 5), provider, False
    except (LLMTimeout, asyncio.TimeoutError) as e:
        err = GatewayError("LLM_PROVIDER_TIMEOUT", request_id)
        cause = e
    except LLMError as e:
        err = GatewayError("LLM_PROVIDER_ERROR", request_id)
        cause = e
    if config.LLM_FALLBACK and config.LLM_FALLBACK != provider.name:
        fb = get_provider(config.LLM_FALLBACK, request_id)
        try:
            return await asyncio.wait_for(fb.generate(payload_text, task), config.LLM_TIMEOUT_S * 3), fb, True
        except Exception:
            pass
    raise err from cause


async def process_document(text: str, task: str, provider: str, request_id: str) -> dict:
    t0 = time.perf_counter()
    handle = None
    audit = {"request_id": request_id, "timestamp": _now(), "status": "error", "provider": provider, "model": None,
             "entity_types": [], "sanitized_payload": None, "leakage_count": 0, "missing_count": 0,
             "llm_time_ms": 0, "processing_time_ms": 0, "gateway_overhead_ms": 0, "error_code": None}
    try:
        # 1. validate
        if not isinstance(text, str) or not text.strip() or task not in TASKS:
            raise GatewayError("INVALID_REQUEST", request_id)
        if len(text) > config.MAX_INPUT_CHARS:
            raise GatewayError("INPUT_TOO_LARGE", request_id)
        prov = get_provider(provider, request_id)

        # 2. detect + mask (CPU bound -> thread)
        try:
            san = await asyncio.to_thread(sanitize_document, text, request_id)
        except Exception as e:
            raise GatewayError("PII_PROCESSING_FAILED", request_id) from e
        handle = san["mapping_handle"]
        audit["entity_types"] = sorted({e["type"] for e in san["entities"]})

        # 3. guard the EXACT string that would leave the organisation
        outbound = prov.build_payload(san["sanitized_text"], task)
        guard = await asyncio.to_thread(validate_outbound_payload, outbound, handle)
        audit["leakage_count"] = guard["leakage_count"]
        if not guard["safe"]:
            # Never persist the rejected candidate: it may contain the very PII
            # the guard detected. Nothing was sent, so there is no outbound
            # payload to record for this blocked request.
            audit["status"] = "blocked"; audit["error_code"] = "OUTBOUND_PII_LEAKAGE_BLOCKED"
            raise GatewayError("OUTBOUND_PII_LEAKAGE_BLOCKED", request_id,
                               {"leakage_count": guard["leakage_count"],
                                "finding_types": sorted({f.get("type", f["kind"]) for f in guard["findings"]})})
        # Store an outbound payload only after the guard has accepted it.
        audit["sanitized_payload"] = outbound

        # 4. external LLM - sanitized text only
        t_llm = time.perf_counter()
        llm_text, used, fb = await _call_llm(prov, san["sanitized_text"], task, request_id)
        audit["llm_time_ms"] = _ms(t_llm)
        audit["provider"], audit["model"] = used.name, used.model
        if fb:  # fallback's payload is what actually left; rebuild audit with it (same sanitized text)
            audit["sanitized_payload"] = used.build_payload(san["sanitized_text"], task)

        # 5. local reinsertion
        try:
            rein = await asyncio.to_thread(reinsert_placeholders, llm_text, handle)
        except Exception as e:
            raise GatewayError("REINSERTION_FAILED", request_id) from e
        audit["missing_count"] = len(rein["missing_placeholders"])

        # 6. audit + respond
        audit["status"] = "success"
        audit["processing_time_ms"] = _ms(t0)
        audit["gateway_overhead_ms"] = audit["processing_time_ms"] - audit["llm_time_ms"]
        db.save_audit(audit)
        return {
            "request_id": request_id, "status": "success", "original_text": text,
            "sanitized_text": san["sanitized_text"], "outbound_payload": audit["sanitized_payload"],
            "entities": san["entities"], "llm_response": llm_text, "final_response": rein["restored_text"],
            "provider": audit["provider"], "model": audit["model"], "fallback_used": fb,
            "leakage_detected": False, "leakage_count": 0,
            "processing_time_ms": audit["processing_time_ms"], "llm_time_ms": audit["llm_time_ms"],
            "gateway_overhead_ms": audit["gateway_overhead_ms"],
            "missing_placeholders": rein["missing_placeholders"], "unknown_placeholders": rein["unknown_placeholders"],
        }
    except GatewayError as e:
        audit["error_code"] = e.code
        if audit["status"] != "blocked":
            audit["status"] = "error"
        audit["processing_time_ms"] = _ms(t0)
        if e.code != "INVALID_REQUEST":  # nothing meaningful to audit for malformed input
            try:
                db.save_audit(audit)
            except Exception:
                pass
        raise
    except Exception as e:  # never leak internals
        audit["error_code"] = "INTERNAL_ERROR"
        try:
            db.save_audit(audit)
        except Exception:
            pass
        raise GatewayError("INTERNAL_ERROR", request_id) from e
    finally:
        if handle:
            destroy_mapping(handle)
