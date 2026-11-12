"""PUBLIC CONTRACT of the privacy engine (Member 2). Member 1 imports only these four functions.

    from app.privacy import sanitize_document, validate_outbound_payload, reinsert_placeholders, destroy_mapping

All calls are synchronous and CPU-bound -> gateway should run them via asyncio.to_thread().
Nothing here makes a network call at inference time.
"""
from .detection.detection_service import detect
from .masking.masking_service import sanitize
from .mapping import mapping_store
from .reinsertion.reinsertion_service import reinsert
from .security.leakage_guard import validate

__all__ = ["sanitize_document", "validate_outbound_payload", "reinsert_placeholders", "destroy_mapping"]


def sanitize_document(text: str, request_id: str) -> dict:
    """-> {sanitized_text, entities[{type,placeholder,start,end,confidence}], mapping_handle, leakage_check}
    leakage_check == True means the guard PASSED (no leakage found)."""
    res = sanitize(text, request_id)
    res["leakage_check"] = validate(res["sanitized_text"], res["mapping_handle"])["safe"]
    return res


def validate_outbound_payload(sanitized_text: str, mapping_handle: str) -> dict:
    """-> {safe: bool, leakage_count: int, findings: [...]} (findings never contain raw PII)."""
    return validate(sanitized_text, mapping_handle)


def reinsert_placeholders(llm_response: str, mapping_handle: str) -> dict:
    """-> {restored_text, restored_placeholders, missing_placeholders, unknown_placeholders}"""
    return reinsert(llm_response, mapping_handle)


def destroy_mapping(mapping_handle: str) -> None:
    """Idempotent. Call in a `finally` block."""
    mapping_store.destroy(mapping_handle)
