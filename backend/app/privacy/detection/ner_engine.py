"""PERSON / ADDRESS detection.

Two layers, merged by detection_service:
  1. heuristic_ner  - always on, dependency-free, rule/context based (Indian English + Hinglish).
  2. GlinerNER      - local zero-shot NER; loaded lazily; enabled by PRIVACY_NER=gliner|both.

Everything runs locally. No network call is made at inference time
(GLiNER downloads weights ONCE at first load; pre-download before the demo).
"""
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

_STOP_LEADING = {"Main", "Mai", "Hum", "Mera", "Meri", "I", "He", "She", "They", "My", "The"}
_NON_NAME = {"Aadhaar", "Aadhar", "Pan", "Passport", "Loan", "Insurance", "Policy", "Claim", "Ticket"}


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


class GlinerNER:
    """Local GLiNER wrapper. Model id configurable via GLINER_MODEL."""

    LABELS = {"person name": "PERSON", "address": "ADDRESS", "city": "ADDRESS"}

    def __init__(self, model_id: Optional[str] = None, threshold: float = 0.5):
        from gliner import GLiNER  # lazy import; optional dependency
        self.model = GLiNER.from_pretrained(model_id or os.getenv("GLINER_MODEL", "urchade/gliner_multi_pii-v1"))
        self.threshold = threshold

    def _chunks(self, text: str, size: int = 900):
        i = 0
        while i < len(text):
            j = min(len(text), i + size)
            if j < len(text):
                nl = text.rfind("\n", i, j)
                if nl > i + size // 2:
                    j = nl
            yield i, text[i:j]
            i = j

    def predict(self, text: str) -> List[Span]:
        out: List[Span] = []
        for off, chunk in self._chunks(text):
            for ent in self.model.predict_entities(chunk, list(self.LABELS), threshold=self.threshold):
                typ = self.LABELS.get(ent["label"])
                if typ:
                    out.append(Span(off + ent["start"], off + ent["end"], typ, float(ent.get("score", 0.5)), "gliner"))
        return out


_gliner_singleton: Optional[GlinerNER] = None
_gliner_failed = False


def get_gliner() -> Optional[GlinerNER]:
    """Returns GLiNER or None (never raises). Loaded once per process."""
    global _gliner_singleton, _gliner_failed
    mode = os.getenv("PRIVACY_NER", "heuristic").lower()
    if mode not in ("gliner", "both") or _gliner_failed:
        return None
    if _gliner_singleton is None:
        try:
            _gliner_singleton = GlinerNER()
        except Exception:  # missing package / weights: degrade to heuristics
            _gliner_failed = True
            return None
    return _gliner_singleton


def detect_names_addresses(text: str) -> List[Span]:
    spans = heuristic_ner(text)
    g = get_gliner()
    if g is not None:
        spans.extend(g.predict(text))
    return spans
