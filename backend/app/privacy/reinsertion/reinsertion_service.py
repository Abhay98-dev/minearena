"""Local, single-pass placeholder reinsertion. Only placeholders that exist in THIS request's mapping
are restored. Missing ones are reported, never guessed. Restored values are never re-scanned."""
import re

from ..mapping import mapping_store
from ..schemas import ENTITY_TYPES, PLACEHOLDER_RE

_TYPES = "|".join(sorted(ENTITY_TYPES, key=len, reverse=True))
# bracketed (tolerates case/space: "< person_1 >", "[PAN_2]")  OR  bare uppercase "PERSON_1"
_KNOWN_RE = re.compile(
    r"[<\[]\s*(?P<t1>" + _TYPES + r")[_\s]\s*(?P<n1>\d+)\s*[>\]]"
    r"|(?<![A-Za-z0-9_])(?P<t2>" + _TYPES + r")_(?P<n2>\d+)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)


def reinsert(llm_response: str, mapping_handle: str) -> dict:
    entry = mapping_store.get(mapping_handle)
    restored, unknown = [], []

    def repl(m: re.Match) -> str:
        t = (m.group("t1") or m.group("t2")).upper()
        n = int(m.group("n1") or m.group("n2"))
        if m.group("t2") and not m.group("t2").isupper():  # bare form must be exact uppercase
            return m.group(0)
        key = f"<{t}_{n}>"
        if key in entry.original:
            if key not in restored:
                restored.append(key)
            return entry.original[key]
        if key not in unknown:
            unknown.append(key)
        return m.group(0)

    text = _KNOWN_RE.sub(repl, llm_response)

    # other bracketed placeholders with unrecognised types, e.g. <EMAIL_1>
    for m in PLACEHOLDER_RE.finditer(text):
        key = f"<{m.group(1).upper()}_{int(m.group(2))}>"
        if key not in unknown and key not in entry.original:
            unknown.append(key)

    missing = [ph for ph in entry.original if ph not in restored]
    return {"restored_text": text, "restored_placeholders": restored,
            "missing_placeholders": missing, "unknown_placeholders": unknown}
