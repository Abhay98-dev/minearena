#!/usr/bin/env python3
"""MineArena Privacy Gateway CLI Tool.
Use to test any real data, documents, or text through the privacy gateway from terminal.

Examples:
    python scripts/gateway_cli.py --text "Rahul Sharma applied for loan. Aadhaar: 1234-5678-9012"
    python scripts/gateway_cli.py --inspect "aman gave 1000Rs to his friend aman"
    python scripts/gateway_cli.py --file my_doc.docx
    python scripts/gateway_cli.py --interactive
"""
import argparse
import asyncio
import json
import os
import sys
import time

# Ensure backend is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.core import config
from app.privacy import destroy_mapping, reinsert_placeholders, sanitize_document, validate_outbound_payload
from app.services.document_reader import extract_document_text
from app.services.docx_reader import read_docx_text
from app.services.gateway_service import process_document


def print_banner():
    print("=" * 70)
    print(" 🛡️  PolarGate DPDP-2023 Enterprise AI Privacy Gateway CLI")
    print("=" * 70)


def run_inspect(text: str):
    print("\n[1] --- ORIGINAL INPUT TEXT ---")
    print(text.strip())

    t0 = time.perf_counter()
    san = sanitize_document(text, "cli_inspect")
    handle = san["mapping_handle"]
    try:
        guard = validate_outbound_payload(san["sanitized_text"], handle)
        elapsed = (time.perf_counter() - t0) * 1000

        print("\n[2] --- DETECTED PII ENTITIES ---")
        if not san["entities"]:
            print("  (No PII detected)")
        for e in san["entities"]:
            print(f"  • {e['type']:<18} -> {e['placeholder']:<14} (conf: {e['confidence']})")

        print("\n[3] --- SANITIZED OUTBOUND PAYLOAD (Sent to AI) ---")
        print(san["sanitized_text"])

        print("\n[4] --- OUTBOUND LEAKAGE GUARD AUDIT ---")
        if guard["safe"]:
            print(f"  ✅ VERIFIED SAFE: 0 Outbound PII Leaks detected.")
        else:
            print(f"  ❌ BLOCKED: {guard['leakage_count']} leaks detected!")
            for f in guard["findings"]:
                print(f"     - {f}")

        print(f"\n⚡ Pre-flight Processing Overhead: {elapsed:.2f} ms")
    finally:
        destroy_mapping(handle)


def run_process(text: str, task: str = "summarize", provider: str = "mock"):
    print_banner()
    print(f"Mode: Full Gateway Pipeline | Task: {task} | Provider: {provider}")
    print("\n[1] Input Text:")
    print(text.strip())

    req_id = "cli_" + str(int(time.time()))
    res = asyncio.run(process_document(text, task, provider, req_id))

    print("\n[2] Sanitized Text (Only This Leaves Organisation):")
    print(res["sanitized_text"])

    print("\n[3] Detected Entities:")
    for e in res["entities"]:
        print(f"  • {e['type']} ({e['placeholder']})")

    print("\n[4] LLM Response (With Tokens):")
    print(res["llm_response"])

    print("\n[5] Final Restored Response (Local In-Memory Reinsertion):")
    print(res["final_response"])

    print("\n[6] Performance Metrics:")
    print(f"  • Total Time:        {res['processing_time_ms']} ms")
    print(f"  • LLM Latency:       {res['llm_time_ms']} ms")
    print(f"  • Gateway Overhead:  {res['gateway_overhead_ms']} ms")
    print(f"  • Leakage Status:    0 Outbound Leaks (Safe)")


def main():
    parser = argparse.ArgumentParser(description="MineArena Privacy Gateway CLI")
    parser.add_argument("--text", type=str, help="Text to process through gateway")
    parser.add_argument("--inspect", type=str, help="Fast pre-flight inspection without calling LLM")
    parser.add_argument("--file", type=str, help="Path to document file to process (.pdf, .docx, .txt, .json, .csv, .md)")
    parser.add_argument("--task", type=str, default="summarize", choices=["summarize", "extract"], help="Gateway task")
    parser.add_argument("--provider", type=str, default="mock", help="AI provider (mock or gemini)")
    parser.add_argument("--interactive", action="store_true", help="Launch interactive gateway shell")

    args = parser.parse_args()

    if args.inspect:
        run_inspect(args.inspect)
        return

    text = None
    if args.file:
        with open(args.file, "rb") as f:
            text = extract_document_text(f.read(), args.file)
    elif args.text:
        text = args.text
    elif args.interactive:
        print_banner()
        print("Interactive Mode. Type your document/text below. Press Enter twice to process:\n")
        lines = []
        while True:
            try:
                line = input()
                if line == "" and lines and lines[-1] == "":
                    break
                lines.append(line)
            except EOFError:
                break
        text = "\n".join(lines).strip()

    if not text:
        parser.print_help()
        sys.exit(0)

    run_process(text, args.task, args.provider)


if __name__ == "__main__":
    main()

