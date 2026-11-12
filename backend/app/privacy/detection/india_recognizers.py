"""India-specific structured-ID recognizers (pure Python, no external deps).

Design rule: checksums only change CONFIDENCE, they never cause a hard reject
for formatted IDs, because synthetic/demo IDs (e.g. 1234-5678-9012) fail real
checksums but must still be masked. Zero leakage > precision.
"""
import re
from typing import List

from ..schemas import Span

# ---------- Verhoeff (Aadhaar checksum) ----------
_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6], [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4], [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2], [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]
_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def verhoeff_valid(num: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def verhoeff_check_digit(num: str) -> str:
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = _D[c][_P[(i + 1) % 8][int(ch)]]
    return str(_INV[c])


# ---------- GSTIN checksum (base-36, mod 36) ----------
_G36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_check_char(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14.upper()):
        v = _G36.index(ch) * (1 if i % 2 == 0 else 2)
        total += v // 36 + v % 36
    return _G36[(36 - total % 36) % 36]


def gstin_valid(g: str) -> bool:
    g = g.upper()
    return len(g) == 15 and all(c in _G36 for c in g) and gstin_check_char(g[:14]) == g[14]


# ---------- regexes ----------
# Separators people actually type inside IDs: space, dash, dot, slash ("1111.2222.8888", "1234/5678/9012")
_SEP = r"[ \-./]"
_AADHAAR = re.compile(r"(?<![0-9A-Za-z])(?<![0-9][.\-/])(\d{4}" + _SEP + r"?\d{4}" + _SEP + r"?\d{4})(?![0-9A-Za-z]|[.\-/]\d)")
_GSTIN = re.compile(r"(?<![0-9A-Za-z])(\d{2}[A-Za-z]{5}\d{4}[A-Za-z][1-9A-Za-z][Zz][0-9A-Za-z])(?![0-9A-Za-z])")
_PAN = re.compile(r"(?<![0-9A-Za-z])([A-Za-z]{5}\d{4}[A-Za-z])(?![0-9A-Za-z])")
_VOTER = re.compile(r"(?<![0-9A-Za-z])([A-Za-z]{3}\d{7})(?![0-9A-Za-z])")
_PASSPORT = re.compile(r"(?<![0-9A-Za-z])([A-PR-WYa-pr-wy]\d{7})(?![0-9A-Za-z])")
# Spaced / dashed forms ("ABCDE 1234 F", "XYZ 1234567", "K 1234567"). Only accepted with the ID's
# keyword just before them, because spaced letter+digit groups are too common in ordinary text.
_PAN_SPACED = re.compile(r"(?<![0-9A-Za-z])([A-Za-z]{5}[ \-]?\d{4}[ \-]?[A-Za-z])(?![0-9A-Za-z])")
_VOTER_SPACED = re.compile(r"(?<![0-9A-Za-z])([A-Za-z]{3}[ \-]\d{7}|[A-Za-z]{3}[ \-]\d{3}[ \-]?\d{4})(?![0-9A-Za-z])")
_PASSPORT_SPACED = re.compile(r"(?<![0-9A-Za-z])([A-PR-WYa-pr-wy][ \-]\d{7}|[A-PR-WYa-pr-wy][ \-]?\d{3}[ \-]\d{4})(?![0-9A-Za-z])")

_AADHAAR_CTX = re.compile(
    r"(aadhaar|aadhar|adhar|adhaar|aadhhar|uidai|\buid\b|\bu\.\s?id\b|\ba\.\s?id\b|unique\s*id|e-?\s?kyc|आधार)", re.I)
_PASSPORT_CTX = re.compile(r"(passport|पासपोर्ट)", re.I)
_VOTER_CTX = re.compile(r"(voter|epic|election\s*card|मतदाता)", re.I)
_PAN_CTX = re.compile(r"(\bpan\b|permanent\s+account|पैन)", re.I)
_PAN_4TH = set("ABCFGHLJPT")  # valid PAN holder-type letters
_CTX_WINDOW = 60


def _ctx(text: str, start: int, rx: re.Pattern, window: int = _CTX_WINDOW) -> bool:
    return bool(rx.search(text[max(0, start - window):start]))


def _near(text: str, start: int, rx: re.Pattern, window: int = 30) -> bool:
    """Keyword close before the value (tighter than _ctx; used for the spaced forms)."""
    return bool(rx.search(text[max(0, start - window):start]))


def find_gstin(text: str) -> List[Span]:
    out = []
    for m in _GSTIN.finditer(text):
        conf = 0.99 if gstin_valid(m.group(1)) else 0.9
        out.append(Span(m.start(1), m.end(1), "GSTIN", conf, "regex"))
    return out


def find_aadhaar(text: str) -> List[Span]:
    out = []
    for m in _AADHAAR.finditer(text):
        raw = m.group(1)
        digits = re.sub(r"\D", "", raw)
        grouped = bool(re.search(_SEP, raw))
        ctx = _ctx(text, m.start(1), _AADHAAR_CTX)
        valid = verhoeff_valid(digits) and digits[0] in "23456789"
        # accept: checksum-valid, OR grouped 4-4-4 format, OR aadhaar keyword nearby
        if not (valid or grouped or ctx):
            continue  # bare 12-digit number with no hint: probably an account no.
        conf = 0.99 if valid else (0.9 if ctx else 0.8)
        out.append(Span(m.start(1), m.end(1), "AADHAAR", conf, "regex"))
    return out


def _spaced(text: str, rx: re.Pattern, ctx: re.Pattern, typ: str, taken: List[Span]) -> List[Span]:
    out = []
    for m in rx.finditer(text):
        if any(s.start < m.end(1) and m.start(1) < s.end for s in taken):
            continue  # the compact form already covers it
        if _near(text, m.start(1), ctx):
            out.append(Span(m.start(1), m.end(1), typ, 0.9, "regex"))
    return out


def find_pan(text: str) -> List[Span]:
    out = []
    for m in _PAN.finditer(text):
        s = m.group(1)
        conf = 0.98 if (s[3].upper() in _PAN_4TH and s.isupper()) else 0.85
        out.append(Span(m.start(1), m.end(1), "PAN", conf, "regex"))
    return out + _spaced(text, _PAN_SPACED, _PAN_CTX, "PAN", out)


def find_voter_id(text: str) -> List[Span]:
    out = []
    for m in _VOTER.finditer(text):
        conf = 0.95 if _ctx(text, m.start(1), _VOTER_CTX) else 0.85
        out.append(Span(m.start(1), m.end(1), "VOTER_ID", conf, "regex"))
    return out + _spaced(text, _VOTER_SPACED, _VOTER_CTX, "VOTER_ID", out)


def find_passport(text: str) -> List[Span]:
    out = []
    for m in _PASSPORT.finditer(text):
        conf = 0.95 if _ctx(text, m.start(1), _PASSPORT_CTX) else 0.6
        out.append(Span(m.start(1), m.end(1), "PASSPORT", conf, "regex"))
    return out + _spaced(text, _PASSPORT_SPACED, _PASSPORT_CTX, "PASSPORT", out)


ALL_FINDERS = {
    "GSTIN": find_gstin, "AADHAAR": find_aadhaar, "PAN": find_pan,
    "VOTER_ID": find_voter_id, "PASSPORT": find_passport,
}


def find_all_structured(text: str) -> List[Span]:
    spans: List[Span] = []
    for fn in ALL_FINDERS.values():
        spans.extend(fn(text))
    return spans
