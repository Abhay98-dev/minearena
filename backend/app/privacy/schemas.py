"""Shared constants/types for the privacy engine (Member 2)."""
import re
from dataclasses import dataclass

# Canonical entity names. Never use any other spelling in output.
ENTITY_TYPES = ("PERSON", "AADHAAR", "PAN", "GSTIN", "VOTER_ID", "PASSPORT", "ADDRESS",
                "PHONE", "PINCODE", "CITY", "STATE", "UPI_ID")

# Tie-break priority when two spans overlap with equal length (lower = wins).
TYPE_PRIORITY = {
    "GSTIN": 0, "AADHAAR": 1, "PAN": 2, "VOTER_ID": 3, "PASSPORT": 4,
    "PERSON": 5, "ADDRESS": 6,
    "PHONE": 7, "UPI_ID": 8, "PINCODE": 9, "CITY": 10, "STATE": 11,
}

# Tolerant placeholder matcher: <PERSON_1>, < person_1 >, <VOTER_ID_2>
PLACEHOLDER_RE = re.compile(r"<\s*([A-Za-z][A-Za-z_]*?)_(\d+)\s*>")


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    type: str
    confidence: float = 0.9
    source: str = "regex"

    @property
    def length(self) -> int:
        return self.end - self.start
