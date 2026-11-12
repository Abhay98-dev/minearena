"""India-specific structured-ID recognizers (pure Python, no external deps).

Design rule: checksums only change CONFIDENCE, they never cause a hard reject
for formatted IDs, because synthetic/demo IDs (e.g. 1234-5678-9012) fail real
checksums but must still be masked. Zero leakage > precision.
"""
import re
import os
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


# ---------- Luhn algorithm (Credit/Debit Card checksum) ----------
def luhn_valid(card_num: str) -> bool:
    digits = [int(c) for c in card_num if c.isdigit()]
    if len(digits) not in (13, 14, 15, 16, 19):
        return False
    checksum = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        if i % 2 == 1:
            d = d * 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


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

# Indian mobile numbers: strict ten-digit subscriber part, with optional India/leading-zero
# prefix and common separators. Conflicting transaction/OTP labels suppress a bare-number hit.
_PHONE = re.compile(r"(?<!\d)(?:(?:\+?91|0)[ \-]?)?([6-9]\d{4}[ \-]?\d{5})(?!\d)")
_PHONE_CONTEXT = re.compile(
    r"(?i)(?:mobile|phone|contact|call|telephone|emergency\s+contact|mera\s+(?:number|mobile)|"
    r"मेरा\s+मोबाइल|मोबाइल\s+नंबर)"
)
_PHONE_NON_CONTEXT = re.compile(r"(?i)(?:transaction|txn|reference|ref(?:erence)?\s*(?:no|number|id)|"
                                r"order\s*(?:no|number|id)|otp|one.time.password|account|invoice|ticket)")

# India Post PINs have six digits and cannot begin with zero. Context gates the candidate so
# OTPs and unrelated transaction counters are not treated as postal codes.
_PINCODE = re.compile(r"(?<!\d)([1-9]\d{5})(?!\d)")
_PIN_CONTEXT = re.compile(r"(?i)\b(?:pin(?:\s*code)?|postal\s*code|post\s*code|postcode|address)\b")
_PIN_NON_CONTEXT = re.compile(r"(?i)\b(?:otp|transaction|txn|reference|order|account|invoice)\b")

# UPI/VPA suffixes are configurable with comma-separated UPI_HANDLES. Known handles are
# accepted without context; an unfamiliar handle is accepted only near an explicit UPI cue.
_DEFAULT_UPI_HANDLES = {
    "okaxis", "ybl", "paytm", "oksbi", "okhdfcbank", "okicici", "okbizaxis", "apl",
    "axl", "ibl", "sbi", "icici", "hdfcbank", "upi", "barodampay", "yesbank",
}
_UPI = re.compile(r"(?<![A-Za-z0-9._%+-])([A-Za-z0-9][A-Za-z0-9._%+-]{1,254}@[A-Za-z][A-Za-z0-9-]{1,63})(?![A-Za-z0-9-])")
_UPI_PARTS = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._%+-]{1,254})@([A-Za-z][A-Za-z0-9-]{1,63})$")
_UPI_CONTEXT = re.compile(r"(?i)\b(?:upi|vpa|upi\s*id|payment\s*id|send\s+money|receive\s+payment|pay\s+to)\b")


def find_phone(text: str) -> List[Span]:
    out = []
    for match in _PHONE.finditer(text):
        before = text[max(0, match.start() - 55):match.start()]
        after = text[match.end():min(len(text), match.end() + 40)]
        if _PHONE_NON_CONTEXT.search(before) or _PHONE_NON_CONTEXT.search(after):
            continue
        confidence = 0.98 if _PHONE_CONTEXT.search(before + after) else 0.84
        out.append(Span(match.start(), match.end(), "PHONE", confidence, "regex"))
    return out


def _nearby_location(text: str, start: int, end: int) -> bool:
    from .india_gazetteer import has_city_or_state_context
    return has_city_or_state_context(text, start, end)


def find_pincode(text: str) -> List[Span]:
    out = []
    for match in _PINCODE.finditer(text):
        before = text[max(0, match.start() - 100):match.start()]
        after = text[match.end():min(len(text), match.end() + 45)]
        if _PIN_NON_CONTEXT.search(before) or _PIN_NON_CONTEXT.search(after):
            continue
        if _PIN_CONTEXT.search(before) or _PIN_CONTEXT.search(after) or _nearby_location(text, match.start(), match.end()):
            out.append(Span(match.start(1), match.end(1), "PINCODE", 0.94, "regex"))
    return out


def _upi_handles():
    configured = {h.strip().casefold().lstrip("@") for h in os.getenv("UPI_HANDLES", "").split(",") if h.strip()}
    return _DEFAULT_UPI_HANDLES | configured


def find_upi_id(text: str) -> List[Span]:
    handles = _upi_handles()
    out = []
    for match in _UPI.finditer(text):
        parts = _UPI_PARTS.fullmatch(match.group(1))
        if not parts:
            continue
        # A domain suffix such as .com/.in means this is an email address, even if its
        # first domain label happens to match a configured UPI app handle.
        if re.match(r"\.[A-Za-z]{2,}(?:\.|\b)", text[match.end(1):]):
            continue
        handle = parts.group(2).casefold()
        before = text[max(0, match.start() - 65):match.start()]
        after = text[match.end():min(len(text), match.end() + 35)]
        if handle in handles or _UPI_CONTEXT.search(before) or _UPI_CONTEXT.search(after):
            out.append(Span(match.start(1), match.end(1), "UPI_ID", 0.96, "regex"))
    return out

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
        before = text[max(0, m.start(1) - 45):m.start(1)]
        if not ctx and (_BANK_CTX.search(before) or _PRAN_CTX.search(before) or _APAAR_CTX.search(before)):
            continue
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


# ---------- Email ----------
_EMAIL = re.compile(r"(?<![A-Za-z0-9_.+-])([A-Za-z0-9_.+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9-.]+)(?![A-Za-z0-9_.+-])")


def find_email(text: str) -> List[Span]:
    out = []
    for m in _EMAIL.finditer(text):
        out.append(Span(m.start(1), m.end(1), "EMAIL", 0.99, "regex"))
    return out


# ---------- Driving Licence (DL) ----------
# Standard DL: 2-letter state code + 2-digit RTO + optional space/dash + 4-digit year + 7 digits
_DL = re.compile(r"(?<![0-9A-Za-z])([A-Za-z]{2}[ \-]?[0-9]{2}[ \-]?(?:19|20)\d{2}[ \-]?[0-9]{7})(?![0-9A-Za-z])")
_DL_CTX = re.compile(r"(?i)\b(?:d[\./\-]?l(?:\s*no)?|driving\s*licen[sc]e|driver'?s\s*licen[sc]e|licence\s*no|license\s*no|लाइसेंस)\b")
_DL_GENERIC = re.compile(r"(?<![0-9A-Za-z])([A-Za-z]{2}[0-9]{13})(?![0-9A-Za-z])")


def find_dl(text: str) -> List[Span]:
    out = []
    for m in _DL.finditer(text):
        conf = 0.99 if _ctx(text, m.start(1), _DL_CTX) else 0.92
        out.append(Span(m.start(1), m.end(1), "DL", conf, "regex"))
    for m in _DL_GENERIC.finditer(text):
        if any(s.start <= m.start(1) and m.end(1) <= s.end for s in out):
            continue
        if _ctx(text, m.start(1), _DL_CTX):
            out.append(Span(m.start(1), m.end(1), "DL", 0.95, "regex"))
    return out


# ---------- IFSC Code ----------
_IFSC = re.compile(r"(?<![0-9A-Za-z])([A-Za-z]{4}0[A-Za-z0-9]{6})(?![0-9A-Za-z])")
_IFSC_CTX = re.compile(r"(?i)\b(?:ifsc|ifsc\s*code|rtgs|neft|branch\s*code|bank\s*code|आईएफएससी)\b")


def find_ifsc(text: str) -> List[Span]:
    out = []
    for m in _IFSC.finditer(text):
        conf = 0.99 if _ctx(text, m.start(1), _IFSC_CTX) else 0.88
        out.append(Span(m.start(1), m.end(1), "IFSC", conf, "regex"))
    return out


# ---------- Bank Account Number ----------
_BANK_ACC = re.compile(r"(?<!\d)(\d{9,18})(?!\d)")
_BANK_CTX = re.compile(r"(?i)\b(?:account\s*(?:no|num|number|#)?|a/c(?:\s*no)?|saving(?:s)?\s*a/c|current\s*a/c|bank\s*a/c|beneficiary\s*a/c|खाता\s*(?:संख्या|नंबर)?)\b")
_BANK_NON_CTX = re.compile(r"(?i)\b(?:aadhaar|pan|phone|mobile|order|tracking|ticket|invoice|pin(?:\s*code)?)\b")


def find_bank_account(text: str) -> List[Span]:
    out = []
    for m in _BANK_ACC.finditer(text):
        before = text[max(0, m.start(1) - 60):m.start(1)]
        after = text[m.end(1):min(len(text), m.end(1) + 40)]
        if _BANK_NON_CTX.search(before) or _BANK_NON_CTX.search(after):
            continue
        if _BANK_CTX.search(before) or _BANK_CTX.search(after):
            out.append(Span(m.start(1), m.end(1), "BANK_ACCOUNT", 0.95, "regex"))
    return out


# ---------- Credit / Debit Card Number ----------
_CARD = re.compile(r"(?<!\d)((?:4\d{3}|5[1-5]\d{2}|6[0-9]\d{2}|3[47]\d{2})[ \-]?(?:\d{4}[ \-]?\d{4}[ \-]?\d{4}|\d{4}[ \-]?\d{4}[ \-]?\d{3})|\d{4}[ \-]\d{4}[ \-]\d{4}[ \-]\d{4})(?!\d)")
_CARD_CTX = re.compile(r"(?i)\b(?:card|credit|debit|rupay|visa|mastercard|amex|card\s*no|cvv|expiry|कार्ड)\b")


def find_card(text: str) -> List[Span]:
    out = []
    for m in _CARD.finditer(text):
        raw = m.group(1)
        valid = luhn_valid(raw)
        ctx = _ctx(text, m.start(1), _CARD_CTX)
        if valid or ctx:
            conf = 0.99 if valid else 0.90
            out.append(Span(m.start(1), m.end(1), "CREDIT_DEBIT_CARD", conf, "regex"))
    return out


# ---------- Date of Birth (DOB) ----------
_DOB = re.compile(r"\b((?:0[1-9]|[12][0-9]|3[01])[/\-.](?:0[1-9]|1[0-2])[/\-.](?:19\d\d|20[0-2]\d)|(?:19\d\d|20[0-2]\d)[/\-.](?:0[1-9]|1[0-2])[/\-.](?:0[1-9]|[12][0-9]|3[01]))\b")
_DOB_CTX = re.compile(r"(?i)\b(?:d[\./\-]?o[\./\-]?b|date\s*of\s*birth|born\s*(?:on)?|birth\s*date|जन्म\s*तिथि)\b")


def find_dob(text: str) -> List[Span]:
    out = []
    for m in _DOB.finditer(text):
        before = text[max(0, m.start(1) - 50):m.start(1)]
        after = text[m.end(1):min(len(text), m.end(1) + 30)]
        if _DOB_CTX.search(before) or _DOB_CTX.search(after):
            out.append(Span(m.start(1), m.end(1), "DOB", 0.98, "regex"))
    return out


# ---------- Ration Card Number ----------
_RATION = re.compile(r"(?<![0-9A-Za-z])([A-Za-z0-9/\-]{8,16})(?![0-9A-Za-z])")
_RATION_CTX = re.compile(r"(?i)\b(?:ration\s*(?:card|no|number)|nfsa|bpl\s*card|apl\s*card|राशन\s*कार्ड)\b")


def find_ration_card(text: str) -> List[Span]:
    out = []
    for m in _RATION.finditer(text):
        if _ctx(text, m.start(1), _RATION_CTX):
            out.append(Span(m.start(1), m.end(1), "RATION_CARD", 0.95, "regex"))
    return out


# ---------- UAN (Universal Account Number - EPFO) ----------
_UAN = re.compile(r"(?<!\d)(10\d{10})(?!\d)")
_UAN_BARE_12 = re.compile(r"(?<!\d)(\d{12})(?!\d)")
_UAN_CTX = re.compile(r"(?i)\b(?:uan|epf|epfo|universal\s*account\s*number|pf\s*number)\b")


def find_uan(text: str) -> List[Span]:
    out = []
    for m in _UAN.finditer(text):
        before = text[max(0, m.start(1) - 30):m.start(1)]
        if not _ctx(text, m.start(1), _UAN_CTX) and (_PRAN_CTX.search(before) or _BANK_CTX.search(before)):
            continue
        conf = 0.99 if _ctx(text, m.start(1), _UAN_CTX) else 0.88
        out.append(Span(m.start(1), m.end(1), "UAN", conf, "regex"))
    for m in _UAN_BARE_12.finditer(text):
        if any(s.start <= m.start(1) and m.end(1) <= s.end for s in out):
            continue
        if _ctx(text, m.start(1), _UAN_CTX):
            out.append(Span(m.start(1), m.end(1), "UAN", 0.96, "regex"))
    return out


# ---------- APAAR ID (One Nation One Student) ----------
_APAAR = re.compile(r"(?<!\d)(\d{4}[ \-]?\d{4}[ \-]?\d{4}|\d{12})(?!\d)")
_APAAR_CTX = re.compile(r"(?i)\b(?:apaar|apaar\s*id|one\s*nation\s*one\s*student|abc\s*id|academic\s*bank\s*of\s*credits)\b")


def find_apaar(text: str) -> List[Span]:
    out = []
    for m in _APAAR.finditer(text):
        if _ctx(text, m.start(1), _APAAR_CTX):
            out.append(Span(m.start(1), m.end(1), "APAAR", 0.98, "regex"))
    return out


# ---------- ABHA (Ayushman Bharat Health Account) ----------
_ABHA = re.compile(r"(?<!\d)(\d{2}[ \-]?\d{4}[ \-]?\d{4}[ \-]?\d{4}|\d{14})(?!\d)")
_ABHA_CTX = re.compile(r"(?i)\b(?:abha|abha\s*id|abha\s*number|ayushman\s*bharat|health\s*id)\b")


def find_abha(text: str) -> List[Span]:
    out = []
    for m in _ABHA.finditer(text):
        digits = re.sub(r"\D", "", m.group(1))
        if len(digits) == 14 and (_ctx(text, m.start(1), _ABHA_CTX) or "-" in m.group(1)):
            out.append(Span(m.start(1), m.end(1), "ABHA", 0.98, "regex"))
    return out


# ---------- PRAN (Permanent Retirement Account Number - NPS) ----------
_PRAN = re.compile(r"(?<!\d)(110\d{9})(?!\d)")
_PRAN_BARE_12 = re.compile(r"(?<!\d)(\d{12})(?!\d)")
_PRAN_CTX = re.compile(r"(?i)\b(?:pran|pran\s*no|nps|permanent\s*retirement\s*account)\b")


def find_pran(text: str) -> List[Span]:
    out = []
    for m in _PRAN.finditer(text):
        conf = 0.99 if _ctx(text, m.start(1), _PRAN_CTX) else 0.88
        out.append(Span(m.start(1), m.end(1), "PRAN", conf, "regex"))
    for m in _PRAN_BARE_12.finditer(text):
        if any(s.start <= m.start(1) and m.end(1) <= s.end for s in out):
            continue
        if _ctx(text, m.start(1), _PRAN_CTX):
            out.append(Span(m.start(1), m.end(1), "PRAN", 0.96, "regex"))
    return out


# ---------- Device Identifiers (IP Address, MAC, IMEI) ----------
_IPV4 = re.compile(r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b")
_MAC = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}(?:[0-9A-Fa-f]{2})\b")
_IMEI = re.compile(r"(?<!\d)(\d{15})(?!\d)")
_DEV_CTX = re.compile(r"(?i)\b(?:imei|device\s*id|device\s*identifier|ip\s*address|mac\s*address)\b")


def find_device_id(text: str) -> List[Span]:
    out = []
    for m in _IPV4.finditer(text):
        out.append(Span(m.start(0), m.end(0), "DEVICE_ID", 0.95, "regex"))
    for m in _MAC.finditer(text):
        out.append(Span(m.start(0), m.end(0), "DEVICE_ID", 0.95, "regex"))
    for m in _IMEI.finditer(text):
        if _ctx(text, m.start(1), _DEV_CTX):
            out.append(Span(m.start(1), m.end(1), "DEVICE_ID", 0.96, "regex"))
    return out


ALL_FINDERS = {
    "GSTIN": find_gstin, "AADHAAR": find_aadhaar, "PAN": find_pan,
    "VOTER_ID": find_voter_id, "PASSPORT": find_passport,
    "PHONE": find_phone, "PINCODE": find_pincode, "UPI_ID": find_upi_id,
    "EMAIL": find_email, "DL": find_dl, "IFSC": find_ifsc,
    "BANK_ACCOUNT": find_bank_account, "CREDIT_DEBIT_CARD": find_card,
    "DOB": find_dob, "RATION_CARD": find_ration_card, "UAN": find_uan,
    "APAAR": find_apaar, "ABHA": find_abha, "PRAN": find_pran,
    "DEVICE_ID": find_device_id,
}


def find_all_structured(text: str) -> List[Span]:
    spans: List[Span] = []
    for fn in ALL_FINDERS.values():
        spans.extend(fn(text))
    return spans
