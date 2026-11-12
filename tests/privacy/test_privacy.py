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


def test_ambiguous_token_not_merged_across_people():
    t = "Applicant: Rahul Sharma\nNominee: Rahul Verma\nRahul called."
    r = sanitize_document(t, "req6")
    s = r["sanitized_text"]
    assert "<PERSON_1>" in s and "<PERSON_2>" in s
    # The lone "Rahul" could be either person: it gets its OWN placeholder - never left in clear
    # text (leak) and never merged into one of the two people (wrong-person restoration).
    assert "Rahul" not in s and "<PERSON_3>" in s
    out = reinsert_placeholders("<PERSON_3> called.", r["mapping_handle"])
    assert out["restored_text"] == "Rahul called."
    destroy_mapping(r["mapping_handle"])


def test_shared_surname_never_leaks():
    # live-Gemini regression: "Nair" (shared by two people) used to go out in clear text
    t = "Applicant: Priya Nair\nSpouse: Arjun Nair\nNair family visited the branch."
    r = sanitize_document(t, "req6b")
    s = r["sanitized_text"]
    assert "Nair" not in s and "Priya" not in s and "Arjun" not in s
    assert r["leakage_check"] is True
    destroy_mapping(r["mapping_handle"])


def test_single_owner_first_name_reuses_placeholder():
    # live-Gemini regression: one person must not get two placeholders
    r = sanitize_document("My name is Kavita Rao. Kavita called the branch twice.", "req6c")
    s = r["sanitized_text"]
    assert s == "My name is <PERSON_1>. <PERSON_1> called the branch twice."
    out = reinsert_placeholders("<PERSON_1> called.", r["mapping_handle"])
    assert out["restored_text"] == "Kavita Rao called."
    destroy_mapping(r["mapping_handle"])


def test_role_word_not_glued_to_name():
    r = sanitize_document("Applicant Priya Nair and her husband Arjun Nair visited the branch.", "req6d")
    first = r["entities"][0]
    t = "Applicant Priya Nair and her husband Arjun Nair visited the branch."
    assert t[first["start"]:first["end"]] == "Priya Nair"
    assert r["sanitized_text"].startswith("Applicant <PERSON_1>")
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


def test_relation_and_verb_heuristics_regression():
    r1 = sanitize_document("Priya Nair and her husband Arjun Nair visited the branch yesterday.", "req19")
    assert "Priya" not in r1["sanitized_text"] and "Arjun" not in r1["sanitized_text"]
    assert "<PERSON_1>" in r1["sanitized_text"] and "<PERSON_2>" in r1["sanitized_text"]
    destroy_mapping(r1["mapping_handle"])

    r2 = sanitize_document("Kabir Ahmed lives in Hyderabad.", "req20")
    assert "Kabir Ahmed" not in r2["sanitized_text"] and "Hyderabad" not in r2["sanitized_text"]
    assert "<PERSON_1>" in r2["sanitized_text"] and "<ADDRESS_1>" in r2["sanitized_text"]
    destroy_mapping(r2["mapping_handle"])


def test_reinsertion_adversarial_formatting():
    r = sanitize_document("Applicant: Rahul Sharma\nCo-applicant: Priya Nair\nPAN: ABCDE1234F", "req21")
    h = r["mapping_handle"]

    # Markdown bold & backticks
    out_md = reinsert_placeholders("**<PERSON_1>** has `<PAN_1>`.", h)
    assert out_md["restored_text"] == "**Rahul Sharma** has `ABCDE1234F`."

    # Adjacent placeholders
    out_adj = reinsert_placeholders("<PERSON_1><PERSON_2>", h)
    assert out_adj["restored_text"] == "Rahul SharmaPriya Nair"

    # Possessive
    out_pos = reinsert_placeholders("<PERSON_1>'s PAN is <PAN_1>.", h)
    assert out_pos["restored_text"] == "Rahul Sharma's PAN is ABCDE1234F."

    # Repeated 50x
    out_rep = reinsert_placeholders(" ".join(["<PERSON_1>"] * 50), h)
    assert out_rep["restored_text"] == " ".join(["Rahul Sharma"] * 50)

    # Lowercase variant
    out_lc = reinsert_placeholders("<person_1> and <pan_1>", h)
    assert out_lc["restored_text"] == "Rahul Sharma and ABCDE1234F"

    destroy_mapping(h)


def test_reinsertion_unclosed_bracket_observation():
    # Document observed behavior on malformed "<PERSON_1" (bare-form branch matches PERSON_1 after '<')
    r = sanitize_document("My name is Rahul Sharma.", "req22")
    h = r["mapping_handle"]
    out = reinsert_placeholders("<PERSON_1", h)
    assert out["restored_text"] == "<Rahul Sharma"
    destroy_mapping(h)


# ---- teammate review (12 Nov): messy real-world input. Rules-only mode on purpose: these must hold
# ---- even if GLiNER fails to load.
SCREENSHOT_1 = ("hi mera naam aditya hai aur me pune me reheta hu also mera adhaar no 5555-6666-7894 hai and "
                "mere dost ka name rahul hai aur uska adhar no 1111.2222.8888 hai")


def test_screenshot_1_lowercase_hinglish_and_dotted_aadhaar():
    r = sanitize_document(SCREENSHOT_1, "rev1")
    s = r["sanitized_text"]
    for raw in ("aditya", "pune", "5555-6666-7894", "1111.2222.8888", "rahul"):
        assert raw not in s, raw
    assert s.count("<AADHAAR_") == 2 and "<ADDRESS_1>" in s
    assert " me <ADDRESS_1> me reheta" in s  # only the city, not the pronoun around it
    assert r["leakage_check"] is True
    destroy_mapping(r["mapping_handle"])


@pytest.mark.parametrize("value", ["1234.5678.9012", "1234/5678/9012", "1234-5678-9012", "1234 5678 9012"])
def test_aadhaar_any_separator_detected_and_guarded(value):
    r = sanitize_document(f"Aadhaar: {value}", "rev2")
    assert r["sanitized_text"] == "Aadhaar: <AADHAAR_1>"
    destroy_mapping(r["mapping_handle"])
    # the guard alone must also catch it (e.g. if detection had missed it)
    h = sanitize_document("nothing here", "rev2b")["mapping_handle"]
    assert validate_outbound_payload(f"aadhaar {value}", h)["safe"] is False
    destroy_mapping(h)


def test_dotted_numbers_that_are_not_aadhaar():
    t = "Invoice 2024.1101.0001.77, version 1.2.3, amount 12,500.50"
    r = sanitize_document(t, "rev3")
    assert r["sanitized_text"] == t
    destroy_mapping(r["mapping_handle"])


def test_abbreviated_aadhaar_labels():
    r = sanitize_document("a.id=2345 6789 0123, unique id=345678901234, u.id= 4567-8901-2345, ekyc id 567890123456",
                          "rev4")
    assert r["sanitized_text"] == "a.id=<AADHAAR_1>, unique id=<AADHAAR_2>, u.id= <AADHAAR_3>, ekyc id <AADHAAR_4>"
    destroy_mapping(r["mapping_handle"])


def test_spaced_ids_with_keyword_and_plain_text_without():
    r = sanitize_document("pan = ABCDE 1234 F and voter = XYZ 1234567 and passport no K 1234567", "rev5")
    assert r["sanitized_text"] == "pan = <PAN_1> and voter = <VOTER_ID_1> and passport no <PASSPORT_1>"
    assert r["leakage_check"] is True
    destroy_mapping(r["mapping_handle"])
    # same shapes without the keyword are ordinary text
    r2 = sanitize_document("Room ABC 1234567 and block A 1234567", "rev5b")
    assert r2["entities"] == []
    destroy_mapping(r2["mapping_handle"])


def test_spaced_and_compact_pan_share_one_placeholder():
    r = sanitize_document("PAN ABCDE1234F. Confirm pan: ABCDE-1234-F", "rev6")
    assert r["sanitized_text"].count("<PAN_1>") == 2 and "<PAN_2>" not in r["sanitized_text"]
    destroy_mapping(r["mapping_handle"])


def test_json_payload_stays_valid_json():
    import json
    t = '{"name": "rahul sharma", "address": "12 MG Road, Pune 411001", "pan": "ABCDE1234F", "city": "pune"}'
    r = sanitize_document(t, "rev7")
    data = json.loads(r["sanitized_text"])  # masking must not break the structure
    assert data == {"name": "<PERSON_1>", "address": "<ADDRESS_1>", "pan": "<PAN_1>", "city": "<ADDRESS_2>"}
    destroy_mapping(r["mapping_handle"])


def test_key_value_payload():
    r = sanitize_document("Name=Rahul Sharma; city=Pune; PAN=ABCDE1234F", "rev8")
    assert r["sanitized_text"] == "Name=<PERSON_1>; city=<ADDRESS_1>; PAN=<PAN_1>"
    destroy_mapping(r["mapping_handle"])


def test_lowercase_english_name_and_city():
    r = sanitize_document("my name is aditya kulkarni and i live in nashik", "rev9")
    assert r["sanitized_text"] == "my name is <PERSON_1> and i live in <ADDRESS_1>"
    destroy_mapping(r["mapping_handle"])
    r2 = sanitize_document("i live in a flat near the station", "rev9b")
    assert r2["entities"] == []  # "a flat" is not a place
    destroy_mapping(r2["mapping_handle"])


@pytest.mark.parametrize("text,city", [
    ("main mumbai mein rehti hoon", "mumbai"),
    ("hum log delhi me rahte hain", "delhi"),
    ("ramesh aur me pune me rehte hai", "pune"),
    ("Sector 22, Noida mein rehte hain", "Noida"),
    ("Mera ghar Kothrud me hai, Pune me rehna hai", "Pune"),
])
def test_hinglish_residence_spellings(text, city):
    r = sanitize_document(text, "rev10")
    assert city not in r["sanitized_text"]
    destroy_mapping(r["mapping_handle"])


def test_id_normalize_ignores_separators():
    from app.privacy.mapping.mapping_store import normalize
    assert normalize("PAN", "ABCDE-1234-F") == normalize("PAN", "abcde 1234 f") == "ABCDE1234F"
    assert normalize("AADHAAR", "1111.2222.8888") == "111122228888"


def test_care_of_relationship_pattern():
    r = sanitize_document("Kamla Devi W/O Ramesh Rao, C/O Suresh Rao", "req_careof")
    assert "Ramesh Rao" not in r["sanitized_text"]
    assert "Suresh Rao" not in r["sanitized_text"]
    destroy_mapping(r["mapping_handle"])
