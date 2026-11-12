"""PERSON / ADDRESS detection.

Two layers, merged by detection_service:
  1. heuristic_ner  - always on, dependency-free, rule/context based (Indian English + Hinglish).
  2. GlinerNER      - local zero-shot NER; loaded lazily; enabled by PRIVACY_NER=gliner|both.

Everything runs locally. No network call is made at inference time
(GLiNER downloads weights ONCE at first load; pre-download before the demo).
"""
import logging
import os
import re
from typing import List, Optional

from ..schemas import Span

_TOK = r"(?:[A-Z]\.|[A-Z][A-Za-z'\-]+)"  # "Rahul" or an initial "K."
_NAME = _TOK + r"(?:[ \t]+" + _TOK + r"){0,4}"
_NAME_2 = _TOK + r"(?:[ \t]+" + _TOK + r"){1,4}"  # 2+ tokens: avoids matching lone first names or sentence-initial nouns

# "My name is X", "Mera naam X hai", "Mr./Shri X"
_P_TRIGGER = re.compile(r"(?i:my\s+name\s+is|mera\s+naam|mera\s+nam|naam\s+hai|name\s+is)\s+(" + _NAME + r")")
_P_HONORIFIC = re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Shri|Smt|Sri|Dr|Kumari)\.?\s+(" + _NAME + r")")
_P_LABEL = re.compile(
    r"\b(?i:co-applicant|applicant|customer|claimant|policy\s*holder|policyholder|nominee|"
    r"account\s*holder|full\s*name|name|father'?s\s*name|mother'?s\s*name|spouse|guarantor|"
    r"insured|beneficiary|patient)(?i:\s*name)?[ \t]*[:\-][ \t]*(" + _NAME + r")"
)
_P_I = re.compile(r"\bI,[ \t]*(" + _NAME + r")[ \t]*,")  # "I, Suresh Patil, residing at ..."
_P_TRAIL = re.compile(r"\b(" + _NAME + r")[ \t]+(?i:ne|ka|ki|ke)\b")  # Hinglish: "Rahul Sharma ne ..."

# "X and her/his husband/wife Y", "Full Name visited/lives/..."
_P_RELATION = re.compile(
    r"\b(?i:husband|wife|spouse|son|daughter|father|mother|brother|sister|friend|colleague|partner)[ \t]+"
    + r"(" + _NAME + r")"
)
_P_COUPLE = re.compile(
    r"\b(" + _NAME_2 + r")[ \t]+(?i:and[ \t]+(?:her|his)[ \t]+(?:husband|wife|spouse))\b"
)
_P_VERB = re.compile(
    r"\b(" + _NAME_2 + r")[ \t]+(?i:visited|contacted|called|submitted|signed|applied|requested|deposited|withdrew|transferred|paid|lives|resides|resided|works)\b"
)

_A_LABEL = re.compile(
    r"(?im)\b(?:permanent\s+|residential\s+|current\s+|correspondence\s+)?address(?:\s+is)?[ \t]*[:\-]?[ \t]*(.+?)(?:\.(?=\s+[A-Z])|\.?[ \t]*$)"
)
_A_CITY = re.compile(r"(?im)^[ \t]*(?:city|town|village|location|district|state)[ \t]*[:\-][ \t]*(.+?)[ \t]*$")
_A_LIVES = re.compile(
    r"(?i:lives?\s+(?:in|at)|reside[sd]?\s+(?:in|at)|residing\s+(?:in|at)|resident\s+of|staying\s+(?:in|at)|based\s+(?:in|at))\s+"
    r"((?:[0-9][\w/\-]*[ ,]+)?[A-Z][A-Za-z0-9\-]*(?:\.[A-Za-z0-9]+)*(?:[ ,]+[A-Z0-9][A-Za-z0-9\-]*(?:\.[A-Za-z0-9]+)*){0,5})"
)
_A_HINGLISH = re.compile(r"\b([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+){0,2})[ \t]+(?i:mein|me|main)[ \t]+(?i:rehta|rehti|rehte|rahta|rahti|rehna)")

# Role / form words that are never part of a name. Used to (a) strip them from the front of a
# heuristic name span ("Applicant Priya Nair" -> "Priya Nair") and (b) reject GLiNER spans that are
# only role words ("customer", "Loan Officer", "branch").
ROLE_WORDS = {
    "applicant", "co-applicant", "coapplicant", "customer", "claimant", "nominee", "agent", "officer",
    "loan", "manager", "branch", "bank", "sir", "madam", "dear", "insured", "policyholder", "policy",
    "holder", "beneficiary", "patient", "guarantor", "spouse", "husband", "wife", "father", "mother",
    "son", "daughter", "brother", "sister", "papa", "mummy", "bhai", "ji", "user", "client", "employee",
    "executive", "team", "support", "address", "location", "name", "person", "field", "value",
    "document", "the", "a", "an", "his", "her", "their", "my", "our", "and", "of", "to", "account",
    "aadhaar", "aadhar", "pan", "passport", "voter", "gstin", "kyc", "form", "claim", "ticket",
    "insurance", "relationship", "representative", "staff", "member", "owner", "proprietor", "director",
    "partner", "witness", "signatory", "borrower", "lender", "employer", "tenant", "landlord", "doctor",
    "hospital", "company", "pvt", "ltd", "limited", "private", "city", "state", "district",
}
# Honorifics are kept out of PERSON values so the same person is not split into "Smt. X" and "X".
HONORIFICS = {"mr", "mrs", "ms", "miss", "shri", "sri", "smt", "dr", "kumari", "late", "prof", "w/o", "s/o", "d/o", "c/o"}

_STOP_LEADING = {"Main", "Mai", "Hum", "Mera", "Meri", "I", "He", "She", "They", "My", "The",
                 "Applicant", "Co-applicant", "Customer", "Claimant", "Nominee", "Dear", "Insured",
                 "Policyholder", "Borrower", "Guarantor", "Beneficiary", "Patient", "Agent", "Yesterday",
                 "Today", "Also", "Then", "When", "Later", "However"}
_NON_NAME = {"Aadhaar", "Aadhar", "Pan", "Passport", "Loan", "Insurance", "Policy", "Claim", "Ticket"}

_WORD = re.compile(r"[\w'\-/]+")
# placeholder-shaped text: "<PERSON_1>", "PERSON_1", "ADDRESS_1" - never a name
_PLACEHOLDERISH = re.compile(r"<\s*[A-Za-z_]+_\d+\s*>|\b[A-Z]+(?:_[A-Z]+)*_\d+\b")

log = logging.getLogger("minearena.privacy")


def _strip(text: str, s: int, e: int):
    """Trim whitespace/punctuation from span edges."""
    while s < e and text[s] in " \t,.;:-":
        s += 1
    while e > s and text[e - 1] in " \t,.;:-":
        e -= 1
    return s, e


def _drop_leading_stop(text: str, s: int, e: int):
    tok = re.match(r"[A-Za-z]+", text[s:e])
    while tok and tok.group(0) in _STOP_LEADING:
        s += tok.end()
        while s < e and text[s] in " \t":
            s += 1
        tok = re.match(r"[A-Za-z]+", text[s:e])
    return s, e


def heuristic_ner(text: str) -> List[Span]:
    out: List[Span] = []

    def add(m, typ, conf, grp=1, fix_stop=False):
        s, e = m.start(grp), m.end(grp)
        if fix_stop:
            s, e = _drop_leading_stop(text, s, e)
        s, e = _strip(text, s, e)
        if typ == "PERSON":
            se = _trim_person(text, s, e)  # "Shri Gopal Rao" -> "Gopal Rao"
            if se is None:
                return
            s, e = se
        if e - s < 2:
            return
        if typ == "PERSON" and text[s:e].split()[0] in _NON_NAME:
            return
        out.append(Span(s, e, typ, conf, "heuristic"))

    for m in _P_TRIGGER.finditer(text):
        add(m, "PERSON", 0.9, fix_stop=True)
    for m in _P_HONORIFIC.finditer(text):
        add(m, "PERSON", 0.85)
    for m in _P_LABEL.finditer(text):
        add(m, "PERSON", 0.88)
    for m in _P_I.finditer(text):
        add(m, "PERSON", 0.8)
    for m in _P_TRAIL.finditer(text):
        add(m, "PERSON", 0.6, fix_stop=True)
    for m in _P_RELATION.finditer(text):
        add(m, "PERSON", 0.78)
    for m in _P_COUPLE.finditer(text):
        add(m, "PERSON", 0.78, fix_stop=True)
    for m in _P_VERB.finditer(text):
        add(m, "PERSON", 0.75, fix_stop=True)
    for m in _A_LABEL.finditer(text):
        add(m, "ADDRESS", 0.88)
    for m in _A_CITY.finditer(text):
        add(m, "ADDRESS", 0.8)
    for m in _A_LIVES.finditer(text):
        add(m, "ADDRESS", 0.8)
    for m in _A_HINGLISH.finditer(text):
        add(m, "ADDRESS", 0.75, fix_stop=True)
    return out


def _words(text: str, s: int, e: int) -> List[re.Match]:
    return list(_WORD.finditer(text, s, e))


def _trim_person(text: str, s: int, e: int):
    """Strip leading honorifics / role words and trailing role words from a PERSON span."""
    ws = _words(text, s, e)
    while ws and (ws[0].group(0).lower().rstrip(".") in HONORIFICS or ws[0].group(0).lower() in ROLE_WORDS):
        ws.pop(0)
    while ws and ws[-1].group(0).lower() in ROLE_WORDS:
        ws.pop()
    if not ws:
        return None
    return _strip(text, ws[0].start(), ws[-1].end())


def _only_role_words(text: str) -> bool:
    toks = [t.lower().rstrip(".") for t in _WORD.findall(text)]
    return not toks or all(t in ROLE_WORDS or t in HONORIFICS for t in toks)


def _minus_placeholders(text: str, s: int, e: int):
    """Pieces of [s, e) that are not placeholder text (GLiNER tags "<PERSON_1>" as a person)."""
    pieces = [(s, e)]
    for m in _PLACEHOLDERISH.finditer(text, max(0, s - 20), min(len(text), e + 20)):
        nxt = []
        for a, b in pieces:
            if m.end() <= a or m.start() >= b:
                nxt.append((a, b))
                continue
            if a < m.start():
                nxt.append((a, m.start()))
            if m.end() < b:
                nxt.append((m.end(), b))
        pieces = nxt
    return [_strip(text, a, b) for a, b in pieces]


class GlinerNER:
    """Local GLiNER wrapper. Model id configurable via GLINER_MODEL.

    Label wording matters: this model was trained on "person" / "address" / "location"
    (model card). "person name" returns nothing, which is how names silently went undetected before.
    """

    LABELS = {"person": "PERSON", "address": "ADDRESS", "location": "ADDRESS"}
    LOCATION_MIN_SCORE = 0.8   # bare "location" hits are noisier ("branch", "Pune branch")
    CHUNK_WORDS = 250          # model max_len is 384 words; stay well under it
    CHUNK_OVERLAP = 30

    def __init__(self, model_id: Optional[str] = None, threshold: Optional[float] = None):
        from gliner import GLiNER  # lazy import; optional dependency
        self.model_id = model_id or os.getenv("GLINER_MODEL", "urchade/gliner_multi_pii-v1")
        self.model = GLiNER.from_pretrained(self.model_id)
        self.threshold = threshold if threshold is not None else float(os.getenv("GLINER_THRESHOLD", "0.35"))

    def _chunks(self, text: str):
        """Word-window chunks with overlap, yielded as (char_offset, chunk_text)."""
        words = list(re.finditer(r"\S+", text))
        if len(words) <= self.CHUNK_WORDS:
            yield 0, text
            return
        step = self.CHUNK_WORDS - self.CHUNK_OVERLAP
        for i in range(0, len(words), step):
            win = words[i:i + self.CHUNK_WORDS]
            a, b = win[0].start(), win[-1].end()
            yield a, text[a:b]
            if i + self.CHUNK_WORDS >= len(words):
                break

    def predict(self, text: str) -> List[Span]:
        best = {}
        for off, chunk in self._chunks(text):
            for ent in self.model.predict_entities(chunk, list(self.LABELS), threshold=self.threshold):
                label = ent["label"]
                typ = self.LABELS.get(label)
                score = float(ent.get("score", 0.5))
                if not typ or (label == "location" and score < self.LOCATION_MIN_SCORE):
                    continue
                for s, e in _minus_placeholders(text, off + ent["start"], off + ent["end"]):
                    if typ == "PERSON":
                        se = _trim_person(text, s, e)
                        if se is None:
                            continue
                        s, e = se
                    if e - s < 2 or _only_role_words(text[s:e]) or not re.search(r"[A-Za-z]", text[s:e]):
                        continue
                    if label == "location" and not text[s].isupper():
                        continue
                    key = (s, e, typ)
                    if score > best.get(key, -1):
                        best[key] = score
        return [Span(s, e, t, sc, "gliner") for (s, e, t), sc in sorted(best.items())]


_gliner_singleton: Optional[GlinerNER] = None
_gliner_failed = False
_gliner_error: Optional[str] = None


def get_gliner() -> Optional[GlinerNER]:
    """Returns GLiNER or None (never raises). Loaded once per process.
    A load failure is logged loudly and reported by engine_status(), never hidden."""
    global _gliner_singleton, _gliner_failed, _gliner_error
    mode = os.getenv("PRIVACY_NER", "heuristic").lower()
    if mode not in ("gliner", "both") or _gliner_failed:
        return None
    if _gliner_singleton is None:
        try:
            _gliner_singleton = GlinerNER()
            log.info("GLiNER loaded: %s (threshold %.2f)", _gliner_singleton.model_id, _gliner_singleton.threshold)
        except Exception as e:  # missing package / weights: degrade to heuristics, but say so
            _gliner_failed = True
            _gliner_error = f"{type(e).__name__}: {str(e)[:200]}"
            log.error("GLiNER failed to load; names/addresses fall back to regex heuristics only. %s",
                      _gliner_error)
            return None
    return _gliner_singleton


def gliner_status() -> dict:
    mode = os.getenv("PRIVACY_NER", "heuristic").lower()
    if mode not in ("gliner", "both"):
        return {"status": "disabled", "mode": mode}
    if _gliner_failed:
        return {"status": "failed", "mode": mode, "error": _gliner_error}
    if _gliner_singleton is None:
        return {"status": "not_loaded", "mode": mode}
    return {"status": "loaded", "mode": mode, "model": _gliner_singleton.model_id,
            "threshold": _gliner_singleton.threshold}


def detect_names_addresses(text: str) -> List[Span]:
    spans = heuristic_ner(text)
    g = get_gliner()
    if g is not None:
        spans.extend(g.predict(text))
    return spans
