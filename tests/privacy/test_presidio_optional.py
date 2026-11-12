"""P2-2: Optional Microsoft Presidio integration tests.
Skips cleanly if presidio-analyzer / spacy / en_core_web_sm are not installed.
Run: PRIVACY_USE_PRESIDIO=1 pytest tests/privacy/test_presidio_optional.py -v
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

presidio_analyzer = pytest.importorskip("presidio_analyzer")
spacy = pytest.importorskip("spacy")

JUDGE = "My name is Rahul Sharma. My Aadhaar number is 1234-5678-9012 and my PAN is ABCDE1234F."


def _has_spacy_model(name: str = "en_core_web_sm") -> bool:
    try:
        spacy.load(name)
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _has_spacy_model(), reason="spacy model en_core_web_sm not downloaded")
def test_presidio_predefined_recognizers_exist():
    import presidio_analyzer.predefined_recognizers as pr
    expected = ("InAadhaarRecognizer", "InPanRecognizer", "InPassportRecognizer", "InVoterRecognizer")
    present = [name for name in expected if hasattr(pr, name)]
    assert len(present) >= 1, f"Expected India recognizers in predefined_recognizers, found: {present}"


@pytest.mark.skipif(not _has_spacy_model(), reason="spacy model en_core_web_sm not downloaded")
def test_presidio_path_matches_judge_example(monkeypatch):
    from app.privacy import sanitize_document, destroy_mapping

    monkeypatch.setenv("PRIVACY_USE_PRESIDIO", "0")
    r_no_presidio = sanitize_document(JUDGE, "req_nop")
    destroy_mapping(r_no_presidio["mapping_handle"])

    monkeypatch.setenv("PRIVACY_USE_PRESIDIO", "1")
    r_presidio = sanitize_document(JUDGE, "req_p")
    destroy_mapping(r_presidio["mapping_handle"])

    assert r_presidio["sanitized_text"] == r_no_presidio["sanitized_text"]
    assert r_presidio["leakage_check"] is True


@pytest.mark.skipif(not _has_spacy_model(), reason="spacy model en_core_web_sm not downloaded")
def test_presidio_detects_all_indian_structured_ids(monkeypatch):
    from app.privacy import sanitize_document, destroy_mapping

    monkeypatch.setenv("PRIVACY_USE_PRESIDIO", "1")
    t = (
        "Applicant: Asha Verma\n"
        "Aadhaar: 2341 2341 2346\n"
        "PAN: ABCPE1234F\n"
        "GSTIN: 27ABCPE1234F1Z5\n"
        "Voter ID: XYZ1234567\n"
        "Passport: K1234567\n"
        "City: Nagpur"
    )
    r = sanitize_document(t, "req_p_all")
    types_found = {e["type"] for e in r["entities"]}
    assert {"PERSON", "AADHAAR", "PAN", "GSTIN", "VOTER_ID", "PASSPORT", "ADDRESS"} <= types_found
    for raw in ["Asha Verma", "2341 2341 2346", "ABCPE1234F", "27ABCPE1234F1Z5", "XYZ1234567", "K1234567", "Nagpur"]:
        assert raw not in r["sanitized_text"]
    destroy_mapping(r["mapping_handle"])

