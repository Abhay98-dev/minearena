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
    """Deterministic: structured IDs win over NER; then longer span, type priority, confidence, earlier start.
    NER spans that overlap a chosen structured span are trimmed, not dropped (so address text is still masked)."""
    structured = sorted((s for s in spans if s.type in _STRUCTURED),
                        key=lambda s: (-s.length, TYPE_PRIORITY[s.type], -s.confidence, s.start))
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


def detect(text: str) -> List[Span]:
    spans = ir.find_all_structured(text)
    spans.extend(detect_names_addresses(text))
    if presidio_enabled():
        spans.extend(detect_with_presidio(text))
    return resolve_overlaps(spans, text)
