"""Unit and full-pipeline tests for India-specific phone, PIN, place and UPI detection."""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from app.privacy import destroy_mapping, sanitize_document, validate_outbound_payload  # noqa: E402
from app.privacy.detection import india_recognizers as ir  # noqa: E402
from app.privacy.detection.india_gazetteer import find_contextual_places  # noqa: E402
from app.privacy.detection.india_gazetteer import STATE_ALIASES  # noqa: E402
from app.privacy.detection.detection_service import resolve_overlaps  # noqa: E402
from app.privacy.detection.ner_engine import heuristic_ner  # noqa: E402
from app.privacy.detection import presidio_engine  # noqa: E402
from app.privacy.mapping import mapping_store  # noqa: E402
from app.core.errors import GatewayError  # noqa: E402
from app.services import gateway_service  # noqa: E402


@pytest.mark.parametrize("value", [
    "9876543210", "+919876543210", "919876543210", "09876543210",
    "98765-43210", "98765 43210",
])
def test_indian_mobile_formats(value):
    spans = ir.find_phone(value)
    assert len(spans) == 1
    assert spans[0].type == "PHONE"
    assert value[spans[0].start:spans[0].end] == value


@pytest.mark.parametrize("text", [
    "Call 1234567890", "Phone number 1234567890", "Phone 987654321", "Transaction ID 9876543210",
    "OTP 9876543210",
])
def test_invalid_or_transaction_numbers_are_not_mobile(text):
    assert ir.find_phone(text) == []


@pytest.mark.parametrize("text", [
    "Address: 24 MG Road, Pune, Maharashtra 411001",
    "My PIN code is 400001",
    "Bengaluru, Karnataka 560001",
])
def test_indian_pin_codes_with_address_or_location_context(text):
    assert any(s.type == "PINCODE" for s in ir.find_pincode(text))


@pytest.mark.parametrize("text", [
    "OTP 123456", "Transaction ID 411001", "Random value 560001", "PIN code 012345",
])
def test_unrelated_or_invalid_six_digit_values_are_not_pin_codes(text):
    assert ir.find_pincode(text) == []


@pytest.mark.parametrize("text,expected_type,value", [
    ("My hometown is Pune.", "CITY", "Pune"),
    ("Customer resides in Bengaluru, Karnataka.", "CITY", "Bengaluru"),
    ("Customer resides in Bengaluru, Karnataka.", "STATE", "Karnataka"),
    ("I am from Mumbai.", "CITY", "Mumbai"),
    ("I belong to Maharashtra.", "STATE", "Maharashtra"),
    ("mera ghar Pune mein hai.", "CITY", "Pune"),
    ("mai Bengaluru se hu.", "CITY", "Bengaluru"),
    ("mai Gujarat se hu.", "STATE", "Gujarat"),
])
def test_contextual_gazetteer_types(text, expected_type, value):
    spans = find_contextual_places(text)
    assert any(s.type == expected_type and text[s.start:s.end].casefold() == value.casefold() for s in spans)


def test_all_indian_states_and_union_territories_and_common_aliases():
    assert len(STATE_ALIASES) == 36
    for canonical, aliases in STATE_ALIASES.items():
        for alias in aliases:
            text = f"I belong to {alias}."
            assert any(s.type == "STATE" and text[s.start:s.end].casefold() == alias.casefold()
                       for s in find_contextual_places(text)), canonical


def test_presidio_registry_adds_new_regex_and_gazetteer_recognizers(monkeypatch):
    presidio_analyzer = pytest.importorskip("presidio_analyzer")
    import presidio_analyzer.nlp_engine

    holder = {}

    class Registry:
        def __init__(self):
            self.recognizers = []
            holder["registry"] = self

        def add_recognizer(self, recognizer):
            self.recognizers.append(recognizer)

    class Provider:
        def __init__(self, nlp_configuration):
            pass

        def create_engine(self):
            return object()

    class Analyzer:
        def __init__(self, nlp_engine, registry, supported_languages):
            self.registry = registry

    monkeypatch.setattr(presidio_analyzer, "RecognizerRegistry", Registry)
    monkeypatch.setattr(presidio_analyzer, "AnalyzerEngine", Analyzer)
    monkeypatch.setattr(presidio_analyzer.nlp_engine, "NlpEngineProvider", Provider)
    registered = presidio_engine._build().registry.recognizers
    names = {recognizer.name for recognizer in registered}
    assert {"CustomPHONERecognizer", "CustomPINCODERecognizer", "CustomUPI_IDRecognizer",
            "CustomCITYRecognizer", "CustomSTATERecognizer"} <= names


@pytest.mark.parametrize("text", [
    "The history of Pune is interesting.",
    "Karnatakaville is not Karnataka.",
    "I like Bengaluru's architecture.",
])
def test_general_geography_and_partial_words_are_not_personal_locations(text):
    assert find_contextual_places(text) == []


@pytest.mark.parametrize("value", ["abhay@okaxis", "9876543210@ybl", "rahul@paytm", "user@oksbi"])
def test_known_upi_ids(value):
    spans = ir.find_upi_id(value)
    assert len(spans) == 1
    assert spans[0].type == "UPI_ID"
    assert value[spans[0].start:spans[0].end] == value


def test_upi_handle_is_configurable(monkeypatch):
    monkeypatch.setenv("UPI_HANDLES", "mybank")
    assert len(ir.find_upi_id("UPI ID user@mybank")) == 1


@pytest.mark.parametrize("value", [
    "person@gmail.com", "person@paytm.com", "not-an-upi", "user@x",
])
def test_email_and_invalid_vpa_are_not_upi_ids(value):
    assert ir.find_upi_id(value) == []


def test_address_overlap_keeps_legacy_address_mask_and_does_not_split_city_state_pin():
    text = "Permanent address: 24 MG Road, Pune, Maharashtra 411001"
    spans = resolve_overlaps(
        ir.find_all_structured(text) + find_contextual_places(text)
        + heuristic_ner(text),
        text,
    )
    assert any(s.type == "ADDRESS" and text[s.start:s.end].startswith("24 MG Road") for s in spans)
    assert not any(s.type in {"CITY", "STATE", "PINCODE"} for s in spans)


def test_phone_inside_upi_is_masked_as_one_complete_upi_value():
    text = "UPI ID 9876543210@ybl"
    result = sanitize_document(text, "upi-overlap")
    assert [e["type"] for e in result["entities"]] == ["UPI_ID"]
    assert result["sanitized_text"] == "UPI ID <UPI_ID_1>"
    destroy_mapping(result["mapping_handle"])


def test_all_five_new_types_flow_through_gateway_mask_guard_mock_and_reinsertion(monkeypatch):
    text = ("Mobile: +91 98765-43210. My PIN code is 400001. My hometown is Pune. "
            "I belong to Maharashtra. UPI ID abhay@okaxis.")
    records = []
    monkeypatch.setattr(gateway_service.db, "save_audit", lambda record: records.append(dict(record)))
    monkeypatch.setenv("MOCK_MODE", "echo")
    result = asyncio.run(gateway_service.process_document(text, "summarize", "mock", "five-india-pii"))
    expected = {"PHONE", "PINCODE", "CITY", "STATE", "UPI_ID"}
    assert expected <= {entity["type"] for entity in result["entities"]}
    for raw in ("+91 98765-43210", "400001", "Pune", "Maharashtra", "abhay@okaxis"):
        assert raw not in result["outbound_payload"]
        assert raw in result["final_response"]
    assert result["fallback_used"] is False
    assert records and records[0]["status"] == "success"
    assert all(raw not in records[0]["sanitized_payload"] for raw in
               ("+91 98765-43210", "400001", "Pune", "Maharashtra", "abhay@okaxis"))
    assert mapping_store.active_count() == 0


def test_leakage_guard_catches_residual_phone_pin_upi_and_contextual_place():
    text = ("Mobile: 9876543210. My PIN code is 411001. My hometown is Pune. "
            "I belong to Maharashtra. UPI ID abhay@okaxis.")
    result = sanitize_document(text, "guard-india-types")
    raw = "Call 9876543210, PIN code 411001, my hometown is Pune, I belong to Maharashtra, UPI abhay@okaxis"
    check = validate_outbound_payload(raw, result["mapping_handle"])
    assert not check["safe"]
    assert {f["type"] for f in check["findings"] if "type" in f} >= {
        "PHONE", "PINCODE", "CITY", "STATE", "UPI_ID"
    }
    destroy_mapping(result["mapping_handle"])


def test_unmapped_residual_new_categories_block_gateway_before_provider(monkeypatch):
    handle = mapping_store.create("residual-india-pii")
    text = ("Call 9876543210. PIN code 411001. My hometown is Pune. "
            "I belong to Maharashtra. UPI ID abhay@okaxis.")

    def deliberately_incomplete_sanitizer(_text, _request_id):
        return {"sanitized_text": text, "entities": [], "mapping_handle": handle}

    class SpyProvider:
        name = "mock"
        model = "test"
        called = False

        def build_payload(self, payload_text, task):
            return payload_text

        async def generate(self, payload_text, task):
            self.called = True
            return payload_text

    provider = SpyProvider()
    monkeypatch.setattr(gateway_service, "sanitize_document", deliberately_incomplete_sanitizer)
    monkeypatch.setattr(gateway_service, "get_provider", lambda *_: provider)
    monkeypatch.setattr(gateway_service.db, "save_audit", lambda *_: None)
    with pytest.raises(GatewayError) as exc:
        asyncio.run(gateway_service.process_document(text, "summarize", "mock", "residual-india-pii"))
    assert exc.value.code == "OUTBOUND_PII_LEAKAGE_BLOCKED"
    assert provider.called is False
    assert mapping_store.active_count() == 0


def test_repeated_mobile_pin_and_upi_values_reuse_placeholders():
    result = sanitize_document(
        "Phone 9876543210. Phone +91 98765 43210. PIN code 411001 and PIN 411001. "
        "UPI abhay@okaxis; pay abhay@okaxis.",
        "repeat-india-types",
    )
    types_by_value = {}
    for entity in result["entities"]:
        types_by_value.setdefault(entity["type"], []).append(entity["placeholder"])
    assert len(set(types_by_value["PHONE"])) == 1
    assert len(set(types_by_value["PINCODE"])) == 1
    assert len(set(types_by_value["UPI_ID"])) == 1
    destroy_mapping(result["mapping_handle"])
