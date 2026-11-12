"""Mask detected spans with consistent typed placeholders (right-to-left, span based).

Pipeline (all local):
  1. detect()            - structured IDs + heuristics + GLiNER + Presidio, overlaps resolved
  2. _propagate()        - every other mention of a detected value is masked too:
                             * full value repeated              -> same placeholder
                             * name token owned by ONE person   -> that person's placeholder ("Priya" -> <PERSON_1>)
                             * name token shared by 2+ people   -> its own placeholder (never left in clear text,
                                                                   never restored as the wrong person)
  3. _second_pass()      - GLiNER re-reads the masked draft and any name/address it still finds is masked
  4. placeholders assigned left-to-right so numbering follows first appearance
"""
import re
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from ..detection.detection_service import detect, resolve_overlaps
from ..detection.ner_engine import HONORIFICS, ROLE_WORDS, get_gliner
from ..mapping import mapping_store
from ..schemas import Span

_STRUCTURED = ("AADHAAR", "PAN", "GSTIN", "VOTER_ID", "PASSPORT")
_NAME_TOKEN = re.compile(r"[A-Za-z][A-Za-z'\-]+")
ALIAS = "alias"  # Span.source for a single-owner name token; masked with its owner's placeholder


def _name_tokens(surface: str) -> List[str]:
    out = []
    for tok in _NAME_TOKEN.findall(surface):
        low = tok.lower()
        if len(tok) >= 3 and low not in ROLE_WORDS and low.rstrip(".") not in HONORIFICS:
            out.append(tok)
    return out


def _find_all(text: str, needle: str):
    rx = re.compile(r"(?<![A-Za-z0-9])" + re.escape(needle) + r"(?![A-Za-z0-9])", re.I)
    return rx.finditer(text)


def _propagate(text: str, spans: List[Span]) -> Tuple[List[Span], Dict[str, str]]:
    """Extra spans for other mentions of detected values, plus alias map {token.casefold(): owner surface}."""
    extra: List[Span] = []
    owners_surface: Dict[str, str] = {}             # normalized person value -> first surface
    needles: Dict[str, str] = {}                     # full surface -> type
    for s in spans:
        if s.type in _STRUCTURED:
            continue  # structured IDs are format-detected everywhere already
        surface = text[s.start:s.end]
        needles.setdefault(surface, s.type)
        if s.type == "PERSON":
            owners_surface.setdefault(mapping_store.normalize("PERSON", surface), surface)

    # A detected partial name ("Arjun" from "Arjun ka ...") whose tokens all belong to exactly one longer
    # detected person is the same person -> alias, so one person never gets two placeholders.
    alias: Dict[str, str] = {}
    for norm, surface in owners_surface.items():
        toks = {t.casefold() for t in _name_tokens(surface)}
        if not toks:
            continue
        supersets = [o for o, os_ in owners_surface.items()
                     if o != norm and toks < {t.casefold() for t in _name_tokens(os_)}]
        if len(supersets) == 1:
            alias[norm] = owners_surface[supersets[0]]
    for norm in alias:
        owners_surface.pop(norm, None)  # partial names are not separate owners
    tok_owner = defaultdict(set)
    for norm, surface in owners_surface.items():
        for tok in _name_tokens(surface):
            tok_owner[tok.casefold()].add(norm)

    for surface, typ in needles.items():
        for m in _find_all(text, surface):
            extra.append(Span(m.start(), m.end(), typ, 0.7, "propagated"))
    for tok, owners in tok_owner.items():
        if tok in (k.casefold() for k in needles):
            continue  # the token is itself a detected full value (e.g. a one-word name)
        owner = owners_surface[next(iter(owners))] if len(owners) == 1 else None
        owner_toks = {t.casefold() for t in _name_tokens(owner)} if owner else set()
        for m in _find_all(text, tok):
            if owner and not _foreign_neighbour(text, m.start(), m.end(), owner_toks):
                alias.setdefault(tok, owner)
                source = ALIAS
            else:
                # shared by 2+ people, or next to an initial / another name ("K. Ramesh"): could be a
                # different person -> its own placeholder; never left in clear text, never the wrong person
                source = "shared_token"
            extra.append(Span(m.start(), m.end(), "PERSON", 0.65, source))
    return extra, alias


_PREV_NAMEISH = re.compile(r"(?:\b[A-Z]\.?|\b[A-Z][a-z]+)[ \t]+$")
_NEXT_NAMEISH = re.compile(r"^[ \t]+([A-Z][a-z]+)")


def _foreign_neighbour(text: str, s: int, e: int, owner_toks: set) -> bool:
    """True if the token sits next to an initial or a capitalised word that is not part of the owner's name."""
    prev = _PREV_NAMEISH.search(text[max(0, s - 25):s])
    if prev:
        word = prev.group(0).strip().rstrip(".")
        if word.casefold() not in owner_toks and word.lower() not in ROLE_WORDS and word.lower() not in HONORIFICS \
                and not _is_sentence_start(text, s - len(prev.group(0))):
            return True
    nxt = _NEXT_NAMEISH.match(text[e:e + 25])
    if nxt and nxt.group(1).casefold() not in owner_toks and nxt.group(1).lower() not in ROLE_WORDS:
        return True
    return False


def _is_sentence_start(text: str, i: int) -> bool:
    j = i - 1
    while j >= 0 and text[j] in " \t":
        j -= 1
    return j < 0 or text[j] in ".!?\n:;"


def _draft(text: str, spans: List[Span]) -> str:
    """Masked text with throwaway placeholders, used only as input for the second pass."""
    counters: Dict[str, int] = defaultdict(int)
    out = text
    for s in sorted(spans, key=lambda x: x.start, reverse=True):
        counters[s.type] += 1
        out = out[:s.start] + f"<{s.type}_{counters[s.type]}>" + out[s.end:]
    return out


def _second_pass(text: str, spans: List[Span]) -> List[Span]:
    """Run GLiNER on the masked draft; map any surviving name/address back to the original text."""
    g = get_gliner()
    if g is None:
        return []
    draft = _draft(text, spans)
    # line-by-line: short context finds what whole-document context scored too low (e.g. a lone city)
    found = {draft[s.start:s.end]: s for s in g.predict(draft, per_line=True, location_min=0.45)}
    covered = [(s.start, s.end) for s in spans]
    extra: List[Span] = []
    for value, s in found.items():
        for m in _find_all(text, value):
            if not any(a < m.end() and m.start() < b for a, b in covered):
                extra.append(Span(m.start(), m.end(), s.type, s.confidence, "second_pass"))
    return extra


def _resolve(text: str, spans: List[Span]) -> Tuple[List[Span], Dict[str, str]]:
    extra, alias = _propagate(text, spans)
    return resolve_overlaps(spans + extra, text), alias


def sanitize(text: str, request_id: str) -> dict:
    base = detect(text)
    spans, alias = _resolve(text, base)
    late = _second_pass(text, spans)
    if late:
        spans, alias = _resolve(text, resolve_overlaps(base + late, text))

    handle = mapping_store.create(request_id)
    entry = mapping_store.get(handle)

    entities = []
    assigned = []
    for s in spans:  # left-to-right so numbering follows first appearance
        value = text[s.start:s.end]
        owner: Optional[str] = None
        if s.type == "PERSON" and s.source != "shared_token":
            owner = alias.get(mapping_store.normalize("PERSON", value))
        if owner is not None:
            ph = entry.placeholder_for(s.type, owner)
            entry.add_surface(ph, s.type, value)  # guard also checks the alias text never leaves
        else:
            ph = entry.placeholder_for(s.type, value)
        assigned.append((s, ph))
        entities.append({"type": s.type, "placeholder": ph, "start": s.start, "end": s.end,
                         "confidence": round(s.confidence, 3)})

    out = text
    for s, ph in sorted(assigned, key=lambda x: x[0].start, reverse=True):  # right-to-left keeps offsets valid
        out = out[:s.start] + ph + out[s.end:]
    return {"sanitized_text": out, "entities": entities, "mapping_handle": handle}
