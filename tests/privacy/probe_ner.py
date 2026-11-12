"""P2-1: Probe NER on 15 Indian-English and Hinglish sentences.
Run: PRIVACY_NER=both python tests/privacy/probe_ner.py  (with PYTHONPATH=backend)
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
os.environ.setdefault("PRIVACY_NER", "both")

from app.privacy import sanitize_document, destroy_mapping

SENTENCES = [
    # 1. Judge example
    "My name is Rahul Sharma. My Aadhaar number is 1234-5678-9012 and my PAN is ABCDE1234F.",
    # 2. Hinglish name + address
    "Mera naam Priya Nair hai. Main Pune mein rehta hoon.",
    # 3. Honorific
    "Mr. Suresh Kumar Patil applied for a personal loan.",
    # 4. Female honorific
    "Smt. Lakshmi Devi is the nominee of the policy.",
    # 5. Label-based
    "Applicant: Asha Verma\nCo-applicant: Vikram Singh",
    # 6. I, Name, pattern
    "Dear Sir, I, Suresh Kumar Patil, hereby apply for the scheme.",
    # 7. Address with pincode
    "Address: 45/B, MG Road, Hadapsar, Pune, Maharashtra 411028",
    # 8. Hinglish address
    "Rahul Sharma Pune mein rehta hai aur uska PAN ABCPE1234F hai.",
    # 9. Couple with repeated names
    "Applicant: Rahul Sharma. Spouse: Meena Sharma. Rahul Sharma signed the form.",
    # 10. Free-text names (hardest)
    "Priya Nair and her husband Arjun Nair visited the branch yesterday.",
    # 11. Multiple IDs
    "Aadhaar: 2341 2341 2346, Voter ID: XYZ1234567, Passport: K1234567",
    # 12. GSTIN
    "The company GSTIN is 27ABCPE1234F1Z5 registered in Maharashtra.",
    # 13. Lives-in pattern
    "Kabir Ahmed lives in Hyderabad and works at a software company.",
    # 14. City label
    "City: Bengaluru\nState: Karnataka",
    # 15. Hinglish trail pattern
    "Rahul Sharma ne loan ke liye apply kiya hai.",
]

if __name__ == "__main__":
    for i, sent in enumerate(SENTENCES, 1):
        rid = f"probe_{i}"
        try:
            r = sanitize_document(sent, rid)
            types_found = [e["type"] for e in r["entities"]]
            print(f"\n--- Sentence {i} ---")
            print(f"  IN:  {sent[:100]}")
            print(f"  OUT: {r['sanitized_text'][:100]}")
            print(f"  Types: {types_found}")
            # Check for unmasked names/addresses
            for word in ["Rahul", "Sharma", "Priya", "Nair", "Suresh", "Patil", "Asha", "Verma",
                          "Vikram", "Singh", "Lakshmi", "Devi", "Meena", "Arjun", "Kabir", "Ahmed",
                          "Pune", "Hadapsar", "MG Road", "Hyderabad", "Bengaluru"]:
                if word in r["sanitized_text"]:
                    print(f"  *** UNMASKED: {word}")
            destroy_mapping(r["mapping_handle"])
        except Exception as e:
            print(f"\n--- Sentence {i} --- ERROR: {e}")

