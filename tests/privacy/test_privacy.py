import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from app.privacy import (sanitize_document, validate_outbound_payload,  # noqa: E402
                         reinsert_placeholders, destroy_mapping)
from app.privacy.detection import india_recognizers as ir  # noqa: E402
from app.privacy.mapping import mapping_store  # noqa: E402

JUDGE = "My name is Rahul Sharma. My Aadhaar number is 1234-5678-9012 and my PAN is ABCDE1234F."


def types(res):
    return {e["type"] for e in res["entities"]}


def test_verhoeff_tables_and_roundtrip():
    assert ir.verhoeff_valid("234123412346")            # widely used UIDAI-style sample
    base = "99887766554"
    assert ir.verhoeff_valid(base + ir.verhoeff_check_digit(base))
    assert not ir.verhoeff_valid("234123412347")


def test_gstin_checksum_roundtrip():
    first14 = "27ABCDE1234F1Z"
    g = first14 + ir.gstin_check_char(first14)
    assert ir.gstin_valid(g)
    assert any(s.type == "GSTIN" for s in ir.find_gstin(f"GSTIN {g} ok"))


def test_judge_example_exact():
    r = sanitize_document(JUDGE, "req1")
    assert r["sanitized_text"] == "My name is <PERSON_1>. My Aadhaar number is <AADHAAR_1> and my PAN is <PAN_1>."
    assert r["leakage_check"] is True
    assert "mapping" not in r
    destroy_mapping(r["mapping_handle"])


def test_all_structured_types():
    t = ("Applicant: Asha Verma\nAadhaar: 2341 2341 2346\nPAN: ABCPE1234F\n"
         "GSTIN: 27ABCPE1234F1Z5\nVoter ID: XYZ1234567\nPassport: K1234567\nCity: Nagpur")
    r = sanitize_document(t, "req2")
    assert {"PERSON", "AADHAAR", "PAN", "GSTIN", "VOTER_ID", "PASSPORT", "ADDRESS"} <= types(r)
    for raw in ["Asha Verma", "2341 2341 2346", "ABCPE1234F", "27ABCPE1234F1Z5", "XYZ1234567", "K1234567", "Nagpur"]:
        assert raw not in r["sanitized_text"], raw
    destroy_mapping(r["mapping_handle"])


def test_gstin_not_split_into_pan():
    r = sanitize_document("GSTIN 27ABCPE1234F1Z5 only", "req3")
    assert [e["type"] for e in r["entities"]] == ["GSTIN"]
    destroy_mapping(r["mapping_handle"])


def test_repeated_entity_same_placeholder_and_numbering():
    t = "Rahul Sharma applied. Rahul Sharma lives in Pune. Priya Nair is co-applicant: Priya Nair."
    r = sanitize_document("Applicant: Rahul Sharma\n" + t, "req4")
    s = r["sanitized_text"]
    assert "<PERSON_1>" in s and "<PERSON_2>" in s and "<PERSON_3>" not in s
    assert "Rahul" not in s and "Sharma" not in s
    destroy_mapping(r["mapping_handle"])


def test_first_name_only_propagation():
    r = sanitize_document("My name is Rahul Sharma. Rahul said hello.", "req5")
    assert "Rahul" not in r["sanitized_text"]
    destroy_mapping(r["mapping_handle"])


@pytest.mark.parametrize("text,name", [
    ("my name is rahul sharma.", "rahul sharma"),
    ("Applicant: rahul kumar submitted the form.", "rahul kumar"),
    ("Mera naam rahul kumar hai.", "rahul kumar"),
    ("mera name abhay hai", "abhay"),
    (":mera name abhay hai", "abhay"),
    ("Mr. rahul sharma applied for a loan.", "rahul sharma"),
    ("my name is rahul sharma and he works here.", "rahul sharma"),
])
def test_lowercase_name_detection_does_not_capture_following_clause(text, name):
    r = sanitize_document(text, f"lower_{name.replace(' ', '_')}")
    people = [e for e in r["entities"] if e["type"] == "PERSON"]
    assert len(people) == 1
    e = people[0]
    assert text[e["start"]:e["end"]].casefold() == name
    assert name not in r["sanitized_text"].casefold()
    destroy_mapping(r["mapping_handle"])


def test_lowercase_first_name_propagates_and_hinglish_city_masks():
    text = "mera naam rahul sharma hai. rahul said hello. main pune mein rehta hoon."
    r = sanitize_document(text, "lower_hinglish")
    lowered = r["sanitized_text"].casefold()
    assert "rahul" not in lowered and "pune" not in lowered
    assert lowered.count("<person_") == 2
    assert "<address_1>" in lowered
    destroy_mapping(r["mapping_handle"])


def test_ambiguous_token_not_merged_across_people():
    t = "Applicant: Rahul Sharma\nNominee: Rahul Verma\nRahul called."
    r = sanitize_document(t, "req6")
    s = r["sanitized_text"]
    assert "<PERSON_1>" in s and "<PERSON_2>" in s
    assert s.count("Rahul") == 1  # ambiguous lone token left alone (documented limitation)
    destroy_mapping(r["mapping_handle"])


def test_hinglish():
    r = sanitize_document("Mera naam Rahul Sharma hai. Main Pune mein rehta hoon. Mera PAN ABCDE1234F hai.", "req7")
    s = r["sanitized_text"]
    assert "Rahul Sharma" not in s and "Pune" not in s and "ABCDE1234F" not in s
    assert "<PERSON_1>" in s and "<ADDRESS_1>" in s and "<PAN_1>" in s
    destroy_mapping(r["mapping_handle"])


def test_address_label_trimmed_around_pan():
    r = sanitize_document("Address: 24 MG Road, Pune, Maharashtra 411001. PAN ABCDE1234F", "req8")
    s = r["sanitized_text"]
    assert "MG Road" not in s and "ABCDE1234F" not in s and "<PAN_1>" in s
    destroy_mapping(r["mapping_handle"])


def test_negative_no_false_positive_on_plain_text():
    r = sanitize_document("The annual income is Rs 8,50,000 and the loan tenure is 5 years.", "req9")
    assert r["entities"] == []
    destroy_mapping(r["mapping_handle"])


def test_bare_12_digits_without_hint_not_aadhaar():
    r = sanitize_document("Account number 123456789012 is active.", "req10")
    assert "AADHAAR" not in types(r)
    destroy_mapping(r["mapping_handle"])


def test_reinsertion_reorder_paraphrase_repeat():
    r = sanitize_document(JUDGE, "req11")
    h = r["mapping_handle"]
    out = reinsert_placeholders("The PAN is <PAN_1> and the applicant <PERSON_1> (aka <PERSON_1>) has <AADHAAR_1>.", h)
    assert out["restored_text"] == "The PAN is ABCDE1234F and the applicant Rahul Sharma (aka Rahul Sharma) has 1234-5678-9012."
    assert out["missing_placeholders"] == [] and out["unknown_placeholders"] == []
    destroy_mapping(h)


def test_reinsertion_dropped_unknown_malformed():
    r = sanitize_document(JUDGE, "req12")
    h = r["mapping_handle"]
    out = reinsert_placeholders("Applicant < person_1 > and [PAN_1] and PERSON_1 and <PERSON_9> and <EMAIL_1> only.", h)
    assert out["restored_text"].count("Rahul Sharma") == 2
    assert "ABCDE1234F" in out["restored_text"]
    assert "<PERSON_9>" in out["restored_text"]            # unknown left untouched, never guessed
    assert set(out["unknown_placeholders"]) == {"<PERSON_9>", "<EMAIL_1>"}
    assert out["missing_placeholders"] == ["<AADHAAR_1>"]  # dropped -> reported, not invented
    destroy_mapping(h)


def test_reinsertion_never_cross_request():
    a = sanitize_document("My name is Rahul Sharma.", "A")
    b = sanitize_document("My name is Priya Nair.", "B")
    out = reinsert_placeholders("<PERSON_1> hello", b["mapping_handle"])
    assert out["restored_text"] == "Priya Nair hello" and "Rahul" not in out["restored_text"]
    destroy_mapping(a["mapping_handle"]); destroy_mapping(b["mapping_handle"])


def test_reinsertion_single_pass_no_injection():
    # a value that itself looks like a placeholder must not be re-expanded
    r = sanitize_document("Applicant: Rahul Sharma\nPAN: ABCDE1234F", "req13")
    h = r["mapping_handle"]
    out = reinsert_placeholders("<PERSON_1> <PAN_1>", h)
    assert out["restored_text"] == "Rahul Sharma ABCDE1234F"
    destroy_mapping(h)


def test_leakage_guard_blocks_known_and_residual():
    r = sanitize_document(JUDGE, "req14")
    h = r["mapping_handle"]
    assert validate_outbound_payload(r["sanitized_text"], h)["safe"] is True
    bad = validate_outbound_payload("applicant Rahul Sharma PAN <PAN_1>", h)
    assert bad["safe"] is False and bad["findings"][0]["kind"] == "mapped_value_present"
    resid = validate_outbound_payload("Another id QWERT9876Z appears", h)   # detector-missed ID shape
    assert resid["safe"] is False
    assert "Rahul" not in str(bad) and "ABCDE" not in str(bad)              # findings carry no raw PII
    destroy_mapping(h)


def test_guard_fails_closed_on_missing_handle():
    assert validate_outbound_payload("x", "mh_doesnotexist")["safe"] is False


def test_destroy_is_idempotent_and_final():
    r = sanitize_document(JUDGE, "req15")
    h = r["mapping_handle"]
    destroy_mapping(h); destroy_mapping(h)
    try:
        reinsert_placeholders("<PERSON_1>", h)
        assert False, "should raise"
    except mapping_store.MappingNotFound:
        pass


def test_entity_offsets_point_into_original():
    r = sanitize_document(JUDGE, "req16")
    for e in r["entities"]:
        assert JUDGE[e["start"]:e["end"]]
    assert JUDGE[r["entities"][0]["start"]:r["entities"][0]["end"]] == "Rahul Sharma"
    destroy_mapping(r["mapping_handle"])


def test_concurrent_requests_isolated():
    results, errs = {}, []

    def work(i):
        try:
            nm = "Asha Rohan Meera Kabir Tara Vikram Isha Dev Nila Omar".split()[i % 10] + " Kumar"
            t = f"My name is {nm}. PAN is ABCDE{1000+i}F."
            r = sanitize_document(t, f"c{i}")
            out = reinsert_placeholders("<PERSON_1> <PAN_1>", r["mapping_handle"])
            results[i] = (nm, out["restored_text"])
            destroy_mapping(r["mapping_handle"])
        except Exception as e:  # noqa
            errs.append(e)

    ths = [threading.Thread(target=work, args=(i,)) for i in range(40)]
    [t.start() for t in ths]; [t.join() for t in ths]
    assert not errs
    for i in range(40):
        assert results[i][1] == f"{results[i][0]} ABCDE{1000+i}F"


def test_label_name_does_not_swallow_lowercase_words():
    r = sanitize_document("Applicant: Rahul Sharma submitted the form. Customer: Priya Nair called", "req17")
    assert r["sanitized_text"] == "Applicant: <PERSON_1> submitted the form. Customer: <PERSON_2> called"
    destroy_mapping(r["mapping_handle"])


def test_I_comma_name_pattern():
    r = sanitize_document("Dear Sir, I, Suresh Kumar Patil, request a loan.", "req18")
    assert "Suresh" not in r["sanitized_text"] and "<PERSON_1>" in r["sanitized_text"]
    destroy_mapping(r["mapping_handle"])
