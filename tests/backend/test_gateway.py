import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
import pytest  # noqa: E402
from app.core.errors import GatewayError  # noqa: E402
from app.database import db  # noqa: E402
from app.privacy.mapping import mapping_store  # noqa: E402
from app.services import gateway_service as gw  # noqa: E402
from app.services.llm import local_providers  # noqa: E402

DOC = "Applicant: Rahul Sharma\nAadhaar: 1234-5678-9012\nPAN: ABCDE1234F\nCity: Pune"
RAW = ["Rahul Sharma", "1234-5678-9012", "ABCDE1234F", "Pune"]


@pytest.fixture(autouse=True)
def _setup(monkeypatch, tmp_path):
    monkeypatch.setattr(gw.config, "AUDIT_DB_PATH", str(tmp_path / "audit.db"))
    db.init_db()
    monkeypatch.setattr(gw.config, "LLM_FALLBACK", "")
    yield
    assert mapping_store.active_count() == 0, "mapping must be destroyed on every path"


def run(text=DOC, task="summarize", provider="mock", rid="req_t1"):
    return asyncio.run(gw.process_document(text, task, provider, rid))


def test_happy_path_and_audit(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "echo")
    r = run()
    for raw in RAW:
        assert raw not in r["outbound_payload"]
        assert raw in r["final_response"]
    rec = db.get_audit("req_t1")
    assert rec["sanitized_payload"] == r["outbound_payload"]
    assert rec["model"] == "mock-llm-1" and rec["status"] == "success"
    assert set(rec["entity_types"]) == {"PERSON", "AADHAAR", "PAN", "ADDRESS"}
    for raw in RAW:
        assert raw not in str(rec)  # audit never holds originals
    assert r["gateway_overhead_ms"] >= 0


@pytest.mark.parametrize("mode", ["reorder", "drop", "paraphrase", "unknown"])
def test_llm_modifications(monkeypatch, mode):
    monkeypatch.setenv("MOCK_MODE", mode)
    r = run(rid=f"req_{mode}")
    if mode == "drop":
        assert r["missing_placeholders"]                    # reported, not invented
        assert "Rahul Sharma" not in r["final_response"]
    if mode == "unknown":
        assert "<PERSON_99>" in r["final_response"] and "<EMAIL_9>" in r["unknown_placeholders"]


def test_leak_blocks_llm_call(monkeypatch):
    called = []
    monkeypatch.setattr(local_providers.MockProvider, "generate", lambda *a, **k: called.append(1))
    # sabotage masking: pretend sanitizer forgot to mask
    def leaky(text, rid):
        from app.privacy import sanitize_document as real
        res = real(text, rid)
        res["sanitized_text"] = text  # raw text leaks into payload
        return res
    monkeypatch.setattr(gw, "sanitize_document", leaky)
    with pytest.raises(GatewayError) as ei:
        run(rid="req_leak")
    assert ei.value.code == "OUTBOUND_PII_LEAKAGE_BLOCKED" and ei.value.http_status == 409
    assert not called, "provider must never be called when guard fails"
    blocked_record = db.get_audit("req_leak")
    assert blocked_record["status"] == "blocked"
    assert blocked_record["sanitized_payload"] is None  # rejected candidate may contain raw PII
    for raw in RAW:
        assert raw not in str(blocked_record)
    for raw in RAW:
        assert raw not in str(ei.value.to_dict())


def test_guard_failure_does_not_persist_unchecked_payload(monkeypatch):
    def broken_guard(*_args, **_kwargs):
        raise RuntimeError("guard unavailable")

    monkeypatch.setattr(gw, "validate_outbound_payload", broken_guard)
    with pytest.raises(GatewayError) as ei:
        run(rid="req_guard_error")
    assert ei.value.code == "INTERNAL_ERROR"
    rec = db.get_audit("req_guard_error")
    assert rec["sanitized_payload"] is None
    for raw in RAW:
        assert raw not in str(rec)


def test_provider_error_maps_and_cleans_up(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "fail")
    with pytest.raises(GatewayError) as ei:
        run(rid="req_fail")
    assert ei.value.code == "LLM_PROVIDER_ERROR"


def test_timeout_maps(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "timeout")
    with pytest.raises(GatewayError) as ei:
        run(rid="req_to")
    assert ei.value.code == "LLM_PROVIDER_TIMEOUT"


def test_fallback_used_when_primary_fails(monkeypatch):
    monkeypatch.setattr(gw.config, "LLM_FALLBACK", "mock")
    class Boom(local_providers.MockProvider):
        name = "boomprov"
        async def generate(self, text, task):
            raise local_providers.LLMError("http_500")
    monkeypatch.setattr(gw, "get_provider", lambda n, rid=None: Boom() if n == "boom" else local_providers.MockProvider())
    monkeypatch.setenv("MOCK_MODE", "echo")
    r = run(provider="boom", rid="req_fb")
    assert r["fallback_used"] is True and r["provider"] == "mock"
    assert "Rahul Sharma" not in r["outbound_payload"]


@pytest.mark.parametrize("text,task,prov,code", [
    ("", "summarize", "mock", "INVALID_REQUEST"),
    ("hi", "translate", "mock", "INVALID_REQUEST"),
    ("hi", "summarize", "nope", "INVALID_REQUEST"),
    ("x" * 30000, "summarize", "mock", "INPUT_TOO_LARGE"),
])
def test_validation(text, task, prov, code):
    with pytest.raises(GatewayError) as ei:
        run(text, task, prov, "req_v")
    assert ei.value.code == code


def test_no_pii_text_still_works(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "echo")
    r = run("The annual income is Rs 8,50,000.", rid="req_nopii")
    assert r["entities"] == [] and r["status"] == "success"
