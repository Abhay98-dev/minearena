
import json
import os
import subprocess
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()
BASE = "http://127.0.0.1:8000/api/v1"
PROVIDER = "gemini" if os.getenv("GEMINI_API_KEY") else "mock"


def show(title: str, data: dict) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")
    print(json.dumps(data, indent=2, ensure_ascii=False))


def main() -> None:
    print(f"Using provider='{PROVIDER}' (set GEMINI_API_KEY in .env to use live Gemini)")
    h = httpx.get(f"{BASE}/health", timeout=5.0)
    h.raise_for_status()
    show("0. HEALTH CHECK", h.json())

    # D1: Judge example
    d1 = httpx.post(
        f"{BASE}/gateway/process",
        json={
            "text": "My name is Rahul Sharma. My Aadhaar number is 1234-5678-9012 and my PAN is ABCDE1234F.",
            "task": "summarize",
            "provider": PROVIDER,
        },
        timeout=60.0,
    ).json()
    show("1. D1 BASIC (Judge Example)", {
        "sanitized_text": d1["sanitized_text"],
        "outbound_payload": d1["outbound_payload"],
        "final_response": d1["final_response"],
        "provider": d1["provider"],
        "model": d1["model"],
        "leakage_count": d1["leakage_count"],
        "gateway_overhead_ms": d1["gateway_overhead_ms"],
    })

    # D2: Hinglish
    d2 = httpx.post(
        f"{BASE}/gateway/process",
        json={
            "text": "Mera naam Rahul Sharma hai. Main Pune mein rehta hoon. Mera PAN ABCDE1234F hai.",
            "task": "extract",
            "provider": PROVIDER,
        },
        timeout=60.0,
    ).json()
    show("2. D2 HINGLISH (Code-Mixed)", {
        "sanitized_text": d2["sanitized_text"],
        "final_response": d2["final_response"],
        "leakage_count": d2["leakage_count"],
        "gateway_overhead_ms": d2["gateway_overhead_ms"],
    })

    # D3: Repeated entity consistency
    d3 = httpx.post(
        f"{BASE}/gateway/process",
        json={
            "text": "Rahul Sharma applied for a loan. Rahul Sharma lives in Pune. Rahul Sharma submitted his PAN ABCDE1234F.",
            "task": "summarize",
            "provider": "mock",
        },
        timeout=30.0,
    ).json()
    show("3. D3 REPEATED ENTITY CONSISTENCY", {
        "sanitized_text": d3["sanitized_text"],
        "entities": d3["entities"],
        "leakage_count": d3["leakage_count"],
    })

    # D5: Audit & Metrics
    audit = httpx.get(f"{BASE}/audit?limit=3", timeout=5.0).json()
    metrics = httpx.get(f"{BASE}/metrics", timeout=5.0).json()
    show("4. D5 AUDIT LOG (Latest Record — Zero Raw PII)", audit["records"][0])
    show("5. D5 METRICS", metrics)

    # D4 + Blocked-leak proof via pytest
    print(f"\n{'=' * 60}\n6. PROOFS: DROPPED/REORDERED PLACEHOLDERS & BLOCKED LEAK (HTTP 409)\n{'=' * 60}")
    subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "tests/backend/test_gateway.py::test_llm_modifications",
            "tests/backend/test_gateway.py::test_leak_blocks_llm_call",
            "-v",
        ],
        check=True,
    )


if __name__ == "__main__":
    main()

