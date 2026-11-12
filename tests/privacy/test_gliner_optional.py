"""Real-model checks for the GLiNER name/address layer. Skipped when gliner or its weights are missing.

Pre-download once:  python -c "from gliner import GLiNER; GLiNER.from_pretrained('urchade/gliner_multi_pii-v1')"
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from app.privacy import destroy_mapping, reinsert_placeholders, sanitize_document  # noqa: E402
from app.privacy.detection import ner_engine  # noqa: E402

LEAK_DOC = ("Loan application. Applicant Priya Nair and her husband Arjun Nair visited the branch. "
            "Priya Nair PAN ABCDE1234F, Aadhaar 2345 6789 0123. Business GSTIN 27ABCDE1234F1Z5. "
            "Address: 14 Shivaji Nagar, Pune 411005. Arjun ka passport number is K1234567.")


@pytest.fixture(autouse=True)
def gliner_on(monkeypatch):
    monkeypatch.setenv("PRIVACY_NER", "both")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")  # never download inside the test run
    if ner_engine.get_gliner() is None:
        pytest.skip(f"GLiNER unavailable: {ner_engine.gliner_status()}")


def _san(text, rid):
    r = sanitize_document(text, rid)
    return r, r["sanitized_text"]


def test_live_leak_document_is_fully_masked():
    r, s = _san(LEAK_DOC, "g1")
    for raw in ("Priya", "Arjun", "Nair", "Shivaji", "Pune", "ABCDE1234F", "2345 6789 0123", "K1234567"):
        assert raw not in s, raw
    persons = {e["placeholder"] for e in r["entities"] if e["type"] == "PERSON"}
    assert persons == {"<PERSON_1>", "<PERSON_2>"}, persons  # one placeholder per person, consistently
    assert s.count("<PERSON_1>") == 2 and "Applicant <PERSON_1>" in s
    out = reinsert_placeholders("<PERSON_2> is the spouse of <PERSON_1>.", r["mapping_handle"])
    assert out["restored_text"] == "Arjun Nair is the spouse of Priya Nair."
    destroy_mapping(r["mapping_handle"])


def test_free_text_names_without_trigger_words():
    r, s = _san("Yesterday Kavitha Subramaniam raised a ticket saying the EMI was debited twice. "
                "Her brother Venkatesh also holds an account. She stays near Lalbagh, Basavanagudi, "
                "Bengaluru 560004.", "g2")
    for raw in ("Kavitha", "Subramaniam", "Venkatesh", "Basavanagudi", "560004"):
        assert raw not in s, raw
    destroy_mapping(r["mapping_handle"])


def test_hinglish_initials_and_honorifics():
    r, s = _san("Mere papa Ramesh Chand Gupta ka claim reject ho gaya. Smt. Lakshmi Devi w/o Shri Gopal Rao "
                "ne bola, aur K. Ramesh ko form bhejna hai.", "g3")
    for raw in ("Ramesh", "Gupta", "Lakshmi", "Gopal"):
        assert raw not in s, raw
    assert "Smt." in s and "Shri" in s  # honorifics stay; only the name is masked
    destroy_mapping(r["mapping_handle"])


def test_role_words_and_org_names_not_masked():
    r, s = _san("The customer called the Loan Officer at the Pune branch about a car loan.", "g4")
    assert "customer" in s and "Loan Officer" in s
    assert not [e for e in r["entities"] if e["type"] == "PERSON"]
    destroy_mapping(r["mapping_handle"])


def test_placeholders_never_retagged():
    g = ner_engine.get_gliner()
    spans = g.predict("My name is <PERSON_1>. I live at <ADDRESS_1>. ADDRESS_1 again.")
    assert spans == []
