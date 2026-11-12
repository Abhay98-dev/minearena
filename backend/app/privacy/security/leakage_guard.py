"""Outbound leakage guard. Fail-closed. Findings never contain raw values.

Two independent checks on the EXACT payload that would be sent:
  1. mapped-value check : any original value of THIS request still present?
  2. residual rescan    : structured Indian IDs still present (catches IDs the detector missed;
                          a mapping-only check cannot).
Limit: names/addresses the detector missed entirely cannot be caught here; measure via evaluation.
"""
import re
from typing import List

from ..detection import india_recognizers as ir
from ..mapping import mapping_store

_ID_TYPES = {"AADHAAR", "PAN", "GSTIN", "VOTER_ID", "PASSPORT"}


def validate(sanitized_text: str, mapping_handle: str) -> dict:
    try:
        entry = mapping_store.get(mapping_handle)
    except mapping_store.MappingNotFound:
        return {"safe": False, "leakage_count": 0, "findings": [{"kind": "mapping_missing"}]}

    findings: List[dict] = []
    folded = sanitized_text.casefold()
    digits_only = re.sub(r"\D", "", sanitized_text)
    seen = set()
    for ph, typ, value in entry.surfaces:
        if (ph, value) in seen:
            continue
        seen.add((ph, value))
        norm = mapping_store.normalize(typ, value)
        if typ == "AADHAAR":
            hit = len(norm) >= 12 and norm in digits_only
        elif typ in _ID_TYPES:
            hit = norm.casefold() in re.sub(r"\s+", "", folded)
        else:
            v = " ".join(value.split()).casefold()
            hit = bool(v) and re.search(r"(?<![a-z0-9])" + re.escape(v) + r"(?![a-z0-9])", " ".join(folded.split())) is not None
        if hit:
            findings.append({"kind": "mapped_value_present", "type": typ, "placeholder": ph})

    for s in ir.find_all_structured(sanitized_text):
        if s.type == "PASSPORT" and s.confidence < 0.9:
            continue  # ambiguous 1-letter+7-digit codes w/o context: don't block on these
        findings.append({"kind": "residual_pattern", "type": s.type, "start": s.start, "end": s.end})

    return {"safe": not findings, "leakage_count": len(findings), "findings": findings}
