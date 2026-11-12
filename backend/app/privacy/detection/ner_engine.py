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
import threading
from typing import List, Optional

from ..schemas import Span

_TOK = r"(?:[A-Z]\.|[A-Z][A-Za-z'\-]+)"  # "Rahul" or an initial "K."
_NAME = _TOK + r"(?:[ \t]+" + _TOK + r"){0,4}"
_NAME_2 = _TOK + r"(?:[ \t]+" + _TOK + r"){1,4}"  # 2+ tokens: avoids matching lone first names or sentence-initial nouns

# "My name is X", "Mera naam X hai", "Mr./Shri X"
_P_TRIGGER = re.compile(r"(?i:my\s+name\s+is|mera\s+naam|mera\s+nam|naam\s+hai|name\s+is)\s+(" + _NAME + r")")
_P_HONORIFIC = re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Shri|Smt|Sri|Dr|Kumari)\.?\s+(" + _NAME + r")")
_LABELS_PERSON = (r"co-applicant|applicant|customer|claimant|policy\s*holder|policyholder|nominee|"
                  r"account\s*holder|full\s*name|name|naam|father'?s\s*name|mother'?s\s*name|spouse|guarantor|"
                  r"insured|beneficiary|patient|customer_name|full_name|first_name|last_name")
# Label + delimiter in prose ("Name: X"), key=value ("name=X") and JSON ('"name": "X"')
_DELIM = r"[\"']?[ \t]*[:=\-][ \t]*[\"']?"
_P_LABEL = re.compile(r"\b(?i:" + _LABELS_PERSON + r")(?i:\s*name)?" + _DELIM + r"(" + _NAME + r")")

# Lower-case names, as people type in chat: "mera naam aditya hai", "my name is aditya kulkarni and ...",
# "mere dost ka name rahul hai", '"name": "rahul sharma"'. The value runs until a stop word.
_LC_WORDS = r"[A-Za-z][A-Za-z'\-]+(?:[ \t]+[A-Za-z][A-Za-z'\-]+){0,3}"
_P_TRIGGER_LC = re.compile(
    r"(?i:\bmy\s+name\s+is|\bmy\s+name|\bmera\s+naam|\bmera\s+nam|\bmeraa\s+naam|\bname\s+is|\bnaam\s+hai|"
    r"\b(?:ka|ki|ke)\s+(?:naam|name)(?:\s+(?:hai|is))?)[ \t]+(" + _LC_WORDS + r")")
_P_LABEL_LC = re.compile(r"\b(?i:" + _LABELS_PERSON + r")" + _DELIM + r"(" + _LC_WORDS + r")")
LC_STOP = {
    "hai", "h", "hu", "hoon", "hun", "he", "hain", "tha", "thi", "and", "aur", "or", "but", "also", "bhi", "i", "is",
    "was", "here", "from", "se", "ji", "my", "mera", "meri", "mere", "me", "mein", "main", "mai", "the", "a", "an",
    "of", "to", "in", "at", "with", "for", "yeh", "ye", "woh", "wo", "ko", "ka", "ki", "ke", "ne", "nahi", "naam",
    "name", "hello", "hi", "sir", "madam", "please", "pls", "plz", "thanks", "uska", "uski", "unka", "hamara", "hum",
    "aap", "aapka", "number", "no", "id", "ok", "okay", "yes", "kya", "kaun", "not", "unknown", "na", "null", "none",
}
_P_I = re.compile(r"\bI,[ \t]*(" + _NAME + r")[ \t]*,")  # "I, Suresh Patil, residing at ..."
_P_TRAIL = re.compile(r"\b(" + _NAME + r")[ \t]+(?i:ne|ka|ki|ke)\b")  # Hinglish: "Rahul Sharma ne ..."

# "X and her/his husband/wife Y", "Full Name visited/lives/..."
_P_RELATION = re.compile(
    r"\b(?i:husband|wife|spouse|son|daughter|father|mother|brother|sister|friend|colleague|partner)[ \t]+"
    + r"(" + _NAME + r")"
)
_P_CAREOF = re.compile(
    r"\b(?:C/O|S/O|D/O|W/O|c/o|s/o|d/o|w/o)\.?\s+(" + _NAME + r")"
)
_P_COUPLE = re.compile(
    r"\b(" + _NAME_2 + r")[ \t]+(?i:and[ \t]+(?:her|his)[ \t]+(?:husband|wife|spouse))\b"
)
_P_VERB = re.compile(
    r"\b(" + _NAME_2 + r")[ \t]+(?i:visited|contacted|called|submitted|signed|applied|requested|deposited|withdrew|transferred|paid|lives|resides|resided|works)\b"
)

# The value never runs past a double quote (JSON), ';' or '|', or into the next "key=" / '"key":'.
_A_LABEL = re.compile(
    r"(?im)\b(?:permanent\s+|residential\s+|current\s+|correspondence\s+|delivery\s+|billing\s+|shipping\s+|"
    r"home\s+|office\s+)?(?:address|addr)(?:\s+is)?[\"']?[ \t]*[:=\-]?[ \t]*\"?"
    r"([^\"\n;|]+?)"
    r"(?=\"|\.\s+[A-Z]|\.?[ \t]*$|[ \t]*[;|]|,[ \t]*\"?[A-Za-z_][\w ]{0,20}\"?[ \t]*[:=])"
)
_A_CITY = re.compile(
    r"(?im)(?:^|[;,{|]|[ \t])[ \t]*[\"']?(?:city|town|village|location|district|state|pin\s*code|pincode)[\"']?"
    r"[ \t]*[:=\-][ \t]*\"?([^\"\n;|,]+)")
_A_LIVES = re.compile(
    r"(?i:lives?\s+(?:in|at)|reside[sd]?\s+(?:in|at)|residing\s+(?:in|at)|resident\s+of|staying\s+(?:in|at)|based\s+(?:in|at))\s+"
    r"((?:[0-9][\w/\-]*[ ,]+)?[A-Z][A-Za-z0-9\-]*(?:\.[A-Za-z0-9]+)*(?:[ ,]+[A-Z0-9][A-Za-z0-9\-]*(?:\.[A-Za-z0-9]+)*){0,5})"
)
# Lower-case English residence: "i live in nashik", "staying at kothrud, pune and ..."
_A_LIVES_LC = re.compile(
    r"(?i)\b(?:live|lives|living|reside|resides|residing|stay|stays|staying|based|resident)\s+(?:in|at|of)\s+"
    r"([a-z0-9][\w\-/]*(?:[ \t,]+[a-z0-9][\w\-/]*){0,4})")
# Hinglish residence, any case and common spellings: "pune me reheta hu", "Mumbai mein rehti hoon",
# "hum log delhi me rahte hain", "Sector 22, Noida mein rehte hain". Verb: reh/rah(e)ta/ti/te/na/ne.
_A_HINGLISH = re.compile(
    r"(?i)\b([a-z0-9][\w\-]*(?:[ \t,]+[a-z0-9][\w\-]*){0,3})[ \t]+(?:me|mein|main|mai|mei|mien|mai)[ \t]+"
    r"(?:hi[ \t]+)?r[ae]h?e?(?:t[aei]|n[ae])\b")
_PLACE_STOP = LC_STOP | {"log", "ham", "abhi", "filhal", "sab", "family", "parivar", "ghar", "yahan", "wahan", "idhar",
                         "udhar", "isi", "usi", "shahar", "sheher", "gaon", "city", "near", "since", "because", "so",
                         "we", "they", "he", "she", "it", "this", "that", "our", "on", "currently", "now", "still",
                         "together", "alone", "with", "rent", "hostel", "pg"}

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
    # Hinglish fillers that sit next to names ("Mera naam X hai", "Dhanyavaad X ji")
    "mera", "meri", "mere", "naam", "nam", "hai", "hain", "dhanyavaad", "dhanyawad", "shukriya", "namaste",
    "aap", "aapka", "aapki", "main", "hum", "pati", "patni", "beta", "beti", "bhaiya", "didi", "sahab", "saheb",
    "haan", "nahi", "aur", "bhi", "wala", "wali", "poora", "pura", "bataiye", "batao", "bataye", "kya", "kahan",
    # greetings and form-field words
    "hi", "hello", "regards", "thanks", "thank", "primary", "secondary", "joint", "business", "residential",
    "correspondence", "permanent", "current", "office", "registered",
}
# A "location" hit containing one of these is an organisation, not a place ("Canara Bank branch")
ORG_MARKERS = {"bank", "hospital", "traders", "mart", "enterprises", "foods", "ltd", "pvt", "limited", "nursing",
               "insurance", "finance", "industries", "services", "solutions", "technologies", "store", "stores"}
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
    while s < e and text[s] in " \t,.;:-\"'":
        s += 1
    while e > s and text[e - 1] in " \t,.;:-\"'":
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
    for m in _P_CAREOF.finditer(text):
        add(m, "PERSON", 0.85)
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

    # lower-case / chat-style rules: keep only the words between the stop words
    def add_words(m, typ, conf, stop, tail=False):
        """Keep one run of non-stop words: the first run (after a trigger: "aditya hai ..." -> "aditya"),
        or with tail=True the run right before the verb ("ramesh aur me pune me rehte" -> "pune")."""
        ws = list(re.finditer(r"[\w\-/]+", text[m.start(1):m.end(1)]))
        base = m.start(1)
        if tail:
            j = len(ws)
            i = j
            while i > 0 and ws[i - 1].group(0).lower() not in stop:
                i -= 1
        else:
            i = 0
            while i < len(ws) and ws[i].group(0).lower() in stop:
                i += 1
            j = i
            capitalised = i < len(ws) and ws[i].group(0)[:1].isupper()
            while j < len(ws) and ws[j].group(0).lower() not in stop:
                if capitalised and typ == "PERSON" and not ws[j].group(0)[:1].isupper():
                    break  # "Rahul Sharma submitted ..." -> "Rahul Sharma"
                j += 1
        if j <= i:
            return
        s, e = _strip(text, base + ws[i].start(), base + ws[j - 1].end())
        if e - s >= 2 and re.search(r"[A-Za-z]", text[s:e]) and not (typ == "PERSON" and _only_role_words(text[s:e])):
            out.append(Span(s, e, typ, conf, "heuristic"))

    for m in _P_TRIGGER_LC.finditer(text):
        add_words(m, "PERSON", 0.8, LC_STOP | ROLE_WORDS)
    for m in _P_LABEL_LC.finditer(text):
        add_words(m, "PERSON", 0.75, LC_STOP | ROLE_WORDS)
    for m in _A_HINGLISH.finditer(text):
        add_words(m, "ADDRESS", 0.75, _PLACE_STOP, tail=True)
    for m in _A_LIVES_LC.finditer(text):
        # "i live in a flat" is not a place: skip when the first word is a stop word
        if m.group(1).split()[0].lower().strip(",") in _PLACE_STOP | {"a", "an", "the"}:
            continue
        add_words(m, "ADDRESS", 0.7, _PLACE_STOP | {"a", "an", "the"})
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
    """True if the span holds no possible name: only role words, honorifics or function words
    ("me", "aur", "hai"), or a single token shorter than 3 letters."""
    toks = [t.lower().rstrip(".") for t in _WORD.findall(text)]
    if len(toks) == 1 and len(re.sub(r"[^a-z]", "", toks[0])) < 3:
        return True
    return not toks or all(t in ROLE_WORDS or t in HONORIFICS or t in LC_STOP for t in toks)


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
    LOCATION_MIN_SCORE = 0.6   # bare "location" hits are noisier; role words ("branch") are filtered separately
    CHUNK_WORDS = 250          # model max_len is 384 words; stay well under it
    CHUNK_OVERLAP = 30

    def __init__(self, model_id: Optional[str] = None, threshold: Optional[float] = None):
        from gliner import GLiNER  # lazy import; optional dependency
        self.model_id = model_id or os.getenv("GLINER_MODEL", "urchade/gliner_multi_pii-v1")
        try:  # offline-first: use the cached weights without touching the network (hackathon Wi-Fi)
            self.model = GLiNER.from_pretrained(self.model_id, local_files_only=True)
        except Exception:  # not cached yet -> download once
            self.model = GLiNER.from_pretrained(self.model_id)
        self.threshold = threshold if threshold is not None else float(os.getenv("GLINER_THRESHOLD", "0.35"))

    def _chunks(self, text: str, base: int = 0):
        """Word-window chunks with overlap, yielded as (char_offset, chunk_text)."""
        words = list(re.finditer(r"\S+", text))
        if len(words) <= self.CHUNK_WORDS:
            yield base, text
            return
        step = self.CHUNK_WORDS - self.CHUNK_OVERLAP
        for i in range(0, len(words), step):
            win = words[i:i + self.CHUNK_WORDS]
            a, b = win[0].start(), win[-1].end()
            yield base + a, text[a:b]
            if i + self.CHUNK_WORDS >= len(words):
                break

    def _lines(self, text: str):
        """One chunk per non-empty line. Short local context scores entities like a city at the end of
        "Hospital: X, Ahmedabad" much higher than whole-document context does."""
        for m in re.finditer(r"[^\n]+", text):
            if re.search(r"[A-Za-z]{2}", m.group(0)):
                yield from self._chunks(m.group(0), m.start())

    def _infer(self, chunks):
        texts = [c for _, c in chunks]
        if hasattr(self.model, "inference"):  # batched (gliner >= 0.2.2x)
            return self.model.inference(texts, list(self.LABELS), threshold=self.threshold, batch_size=16)
        return [self.model.predict_entities(t, list(self.LABELS), threshold=self.threshold) for t in texts]

    def predict(self, text: str, per_line: bool = False, location_min: Optional[float] = None) -> List[Span]:
        chunks = list(self._lines(text) if per_line else self._chunks(text))
        if not chunks:
            return []
        loc_min = self.LOCATION_MIN_SCORE if location_min is None else location_min
        best = {}
        for (off, _), ents in zip(chunks, self._infer(chunks)):
            for ent in ents:
                label = ent["label"]
                typ = self.LABELS.get(label)
                score = float(ent.get("score", 0.5))
                if not typ or (label == "location" and score < loc_min):
                    continue
                for s, e in _minus_placeholders(text, off + ent["start"], off + ent["end"]):
                    if typ == "PERSON":
                        se = _trim_person(text, s, e)
                        if se is None:
                            continue
                        s, e = se
                    if e - s < 2 or _only_role_words(text[s:e]) or not re.search(r"[A-Za-z]", text[s:e]):
                        continue
                    if label == "location" and (not text[s].isupper() or
                                                {t.lower() for t in _WORD.findall(text[s:e])} & ORG_MARKERS):
                        continue
                    key = (s, e, typ)
                    if score > best.get(key, -1):
                        best[key] = score
        return [Span(s, e, t, sc, "gliner") for (s, e, t), sc in sorted(best.items())]


_gliner_singleton: Optional[GlinerNER] = None
_gliner_failed = False
_gliner_error: Optional[str] = None
_gliner_lock = threading.Lock()


def get_gliner() -> Optional[GlinerNER]:
    """Returns GLiNER or None (never raises). Loaded once per process.
    A load failure is logged loudly and reported by engine_status(), never hidden."""
    global _gliner_singleton, _gliner_failed, _gliner_error
    mode = os.getenv("PRIVACY_NER", "heuristic").lower()
    if mode not in ("gliner", "both") or _gliner_failed:
        return None
    if _gliner_singleton is None:
        with _gliner_lock:  # two first requests at once must not load the 1 GB model twice
            if _gliner_singleton is None and not _gliner_failed:
                try:
                    _gliner_singleton = GlinerNER()
                    log.info("GLiNER loaded: %s (threshold %.2f)", _gliner_singleton.model_id,
                             _gliner_singleton.threshold)
                except Exception as e:  # missing package / weights: degrade to heuristics, but say so
                    _gliner_failed = True
                    _gliner_error = f"{type(e).__name__}: {str(e)[:200]}"
                    log.error("GLiNER failed to load; names/addresses fall back to regex heuristics only. %s",
                              _gliner_error)
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
