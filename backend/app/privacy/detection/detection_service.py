"""Combine all detectors and resolve overlaps deterministically."""
import re
from typing import List

from ..schemas import Span, TYPE_PRIORITY
from . import india_recognizers as ir
from .ner_engine import detect_names_addresses
from .presidio_engine import detect_with_presidio, presidio_enabled

_STRUCTURED = {"GSTIN", "AADHAAR", "PAN", "VOTER_ID", "PASSPORT"}


def _overlaps(a: Span, b: Span) -> bool:
    return a.start < b.end and b.start < a.end


def _subtract(span: Span, blockers: List[Span], text: str) -> List[Span]:
    """Remove the parts of `span` covered by blockers; keep leftovers >= 2 chars."""
    pieces = [(span.start, span.end)]
    for b in blockers:
        nxt = []
        for s, e in pieces:
            if b.end <= s or b.start >= e:
                nxt.append((s, e))
                continue
            if s < b.start:
                nxt.append((s, b.start))
            if b.end < e:
                nxt.append((b.end, e))
        pieces = nxt
    out = []
    for s, e in pieces:
        while s < e and text[s] in " \t,.;:-":
            s += 1
        while e > s and text[e - 1] in " \t,.;:-":
            e -= 1
        if e - s >= 2:
            out.append(Span(s, e, span.type, span.confidence, span.source))
    return out


def resolve_overlaps(spans: List[Span], text: str) -> List[Span]:
    """Deterministic: structured IDs win over NER; then longer span, our exact-format regex over Presidio
    (its PAN pattern also matches Voter IDs), type priority, confidence, earlier start.
    NER spans that overlap a chosen structured span are trimmed, not dropped (so address text is still masked)."""
    structured = sorted((s for s in spans if s.type in _STRUCTURED),
                        key=lambda s: (-s.length, s.source != "regex", TYPE_PRIORITY[s.type], -s.confidence, s.start))
    chosen: List[Span] = []
    for s in structured:
        if not any(_overlaps(s, c) for c in chosen):
            chosen.append(s)
    ner: List[Span] = []
    for s in (x for x in spans if x.type not in _STRUCTURED):
        ner.extend(_subtract(s, chosen, text))
    ner.sort(key=lambda s: (-s.length, TYPE_PRIORITY[s.type], -s.confidence, s.start))
    for s in ner:
        if not any(_overlaps(s, c) for c in chosen):
            chosen.append(s)
    return sorted(chosen, key=lambda s: s.start)


# ", PIN 682331" / " - 411005" / " Pincode: 560 004" right after an address belongs to it
_PIN_TAIL = re.compile(r"[ \t]*[,\-]?[ \t]*(?:PIN|Pin|pin|Pincode|PINCODE|pincode)?(?:[ \t]*code)?[ \t]*[:\-]?[ \t]*"
                       r"\d{3}[ \t]?\d{3}(?!\d)")


def extend_address_pins(spans: List[Span], text: str) -> List[Span]:
    out = []
    for i, s in enumerate(spans):
        if s.type == "ADDRESS":
            m = _PIN_TAIL.match(text, s.end)
            nxt = spans[i + 1].start if i + 1 < len(spans) else len(text)
            if m and m.end() <= nxt:
                s = Span(s.start, m.end(), s.type, s.confidence, s.source)
        out.append(s)
    return out


def detect(text: str) -> List[Span]:
    spans = ir.find_all_structured(text)
    spans.extend(detect_names_addresses(text))
    if presidio_enabled():
        spans.extend(detect_with_presidio(text))
    return extend_address_pins(resolve_overlaps(spans, text), text)


def engine_status() -> dict:
    """Which detection layers are actually active. Lets the UI/judges see a silent fallback."""
    from .ner_engine import gliner_status
    from .presidio_engine import presidio_status
    return {"structured_ids": {"status": "loaded"}, "heuristics": {"status": "loaded"},
            "gliner": gliner_status(), "presidio": presidio_status()}


def preload() -> dict:
    """Load the optional models now (server start) instead of on the first request."""
    from .ner_engine import get_gliner
    from .presidio_engine import get_analyzer, presidio_enabled
    get_gliner()
    if presidio_enabled():
        get_analyzer()
    return engine_status()
