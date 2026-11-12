"""HTTP contract checks for the Member 3 frontend integration."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.core import config  # noqa: E402
from app.main import app  # noqa: E402
from app.privacy.mapping import mapping_store  # noqa: E402
from app.services import gateway_service as gw  # noqa: E402

DOC = "My name is Rahul Sharma. My Aadhaar number is 1234-5678-9012 and my PAN is ABCDE1234F."
RAW = ("Rahul Sharma", "1234-5678-9012", "ABCDE1234F")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "AUDIT_DB_PATH", str(tmp_path / "audit.db"))
    monkeypatch.setattr(config, "LLM_FALLBACK", "")
    monkeypatch.setenv("PRIVACY_NER", "heuristic")
    monkeypatch.setenv("PRIVACY_USE_PRESIDIO", "0")
    monkeypatch.setenv("MOCK_MODE", "echo")
    with TestClient(app) as test_client:
        yield test_client
    assert mapping_store.active_count() == 0


def test_health_and_process_contract(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}

    response = client.post(
        "/api/v1/gateway/process",
        json={"text": DOC, "task": "summarize", "provider": "mock"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["request_id"].startswith("req_")
    assert body["status"] == "success"
    assert body["sanitized_text"] == (
        "My name is <PERSON_1>. My Aadhaar number is <AADHAAR_1> and my PAN is <PAN_1>."
    )
    assert "<PERSON_1>" in body["outbound_payload"]
    assert body["fallback_used"] is False
    assert body["llm_time_ms"] >= 0 and body["gateway_overhead_ms"] >= 0
    assert all(raw not in body["outbound_payload"] for raw in RAW)
    assert all(raw in body["final_response"] for raw in RAW)


def test_lowercase_name_is_masked_before_provider_payload(client):
    text = "my name is rahul sharma. His account is active."
    response = client.post(
        "/api/v1/gateway/process",
        json={"text": text, "task": "summarize", "provider": "mock"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "<PERSON_1>" in body["sanitized_text"]
    assert "rahul sharma" not in body["outbound_payload"].casefold()
    assert "rahul sharma" in body["final_response"].casefold()


def test_audit_and_metrics_contract(client):
    result = client.post(
        "/api/v1/gateway/process",
        json={"text": DOC, "task": "summarize", "provider": "mock"},
    ).json()
    record_response = client.get(f"/api/v1/audit/{result['request_id']}")
    assert record_response.status_code == 200
    record = record_response.json()
    assert record["sanitized_payload"] == result["outbound_payload"]
    assert record["model"] == "mock-llm-1"
    assert all(raw not in str(record) for raw in RAW)

    listed = client.get("/api/v1/audit")
    assert listed.status_code == 200
    assert any(row["request_id"] == result["request_id"] for row in listed.json()["records"])
    metrics = client.get("/api/v1/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["n"] == 1
    assert metrics.json()["leaks"] == 0


def test_frontend_cors_preflight(client):
    origin = config.CORS_ORIGINS[0]
    response = client.options(
        "/api/v1/gateway/process",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "POST" in response.headers["access-control-allow-methods"]


def test_validation_error_does_not_echo_request_body(client):
    sentinel = "SENSITIVE-REQUEST-SENTINEL"
    response = client.post(
        "/api/v1/gateway/process",
        json={"text": sentinel, "task": "unsupported", "provider": "mock"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert body["error"]["request_id"] is None
    assert sentinel not in response.text


def test_blocked_payload_error_contract_and_safe_audit(client, monkeypatch):
    real_sanitizer = gw.sanitize_document

    def deliberately_leaky(text, request_id):
        result = real_sanitizer(text, request_id)
        result["sanitized_text"] = text
        return result

    monkeypatch.setattr(gw, "sanitize_document", deliberately_leaky)
    response = client.post(
        "/api/v1/gateway/process",
        json={"text": DOC, "task": "summarize", "provider": "mock"},
    )
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "OUTBOUND_PII_LEAKAGE_BLOCKED"
    assert body["error"]["request_id"].startswith("req_")
    assert all(raw not in response.text for raw in RAW)

    record = client.get(f"/api/v1/audit/{body['error']['request_id']}").json()
    assert record["status"] == "blocked"
    assert record["sanitized_payload"] is None
    assert all(raw not in str(record) for raw in RAW)
