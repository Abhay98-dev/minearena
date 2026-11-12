"""Shared constants/types for the privacy engine (Member 2)."""
import re
from dataclasses import dataclass

# Canonical entity names. Never use any other spelling in output.
ENTITY_TYPES = (
    "PERSON", "AADHAAR", "PAN", "GSTIN", "VOTER_ID", "PASSPORT", "ADDRESS",
    "PHONE", "PINCODE", "CITY", "STATE", "UPI_ID", "EMAIL", "DL",
    "BANK_ACCOUNT", "IFSC", "CREDIT_DEBIT_CARD", "DOB", "RATION_CARD",
    "UAN", "APAAR", "ABHA", "PRAN", "DEVICE_ID",
)

# Tie-break priority when two spans overlap with equal length (lower = wins).
TYPE_PRIORITY = {
    "BANK_ACCOUNT": 0, "PRAN": 1, "APAAR": 2, "ABHA": 3, "UAN": 4,
    "GSTIN": 5, "PAN": 6, "VOTER_ID": 7, "PASSPORT": 8, "DL": 9,
    "CREDIT_DEBIT_CARD": 10, "IFSC": 11, "UPI_ID": 12, "EMAIL": 13,
    "AADHAAR": 14, "DOB": 15, "RATION_CARD": 16, "PHONE": 17,
    "PERSON": 18, "ADDRESS": 19,
    "PINCODE": 20, "CITY": 21, "STATE": 22, "DEVICE_ID": 23,
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
