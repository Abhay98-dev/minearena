"""Held-out synthetic set: NEW phrasings that the detector was never tuned on.

    python dataset/generate_heldout.py      # writes dataset/heldout/*.txt + dataset/heldout_ground_truth.json

The main set (generate_dataset.py) was used to find and fix detector errors, so its scores are
optimistic. These 20 documents use different templates (emails, WhatsApp/SMS style, "near"/"opp."
addresses, more Hinglish, three-person documents) and a different seed. Rule: report these numbers
as they come out - do NOT tune the detector against this set, or it stops being held out.
"""
import json
import shutil
from pathlib import Path

from generate_dataset import Gen, fillers, make_values, render

SEED = 7
ROOT = Path(__file__).resolve().parent

TEMPLATES = [
    ({"p1": "F"}, "From: [[PERSON:p1]]\nTo: grievance cell\n\nRespected Sir/Madam,\nI am writing to report that my "
     "savings account was frozen without notice. My PAN [[PAN:pan1]] and Aadhaar [[AADHAAR:aad1]] are already "
     "linked. Kindly restore access at the earliest.\n\nThanking you,\n[[PERSON:p1]]\n[[ADDRESS:a1]]"),
    ({"p1": "M", "p2": "M"}, "[10:42] [[PERSON:p1f]]: bhai mera passport [[PASSPORT:pass1]] wala form kab tak verify "
     "hoga?\n[10:44] Agent [[PERSON:p2f]]: sir 2 din lagenge, aapka address [[ADDRESS:c1]] hi hai na?\n"
     "[10:45] [[PERSON:p1f]]: haan wahi"),
    ({"p1": "F", "p2": "M", "p3": "F"}, "Family floater policy {policy} covers [[PERSON:p1]], her husband "
     "[[PERSON:p2]] and their daughter [[PERSON:p3]]. Premium is paid from the account of [[PERSON:p2f]]. All three "
     "live at [[ADDRESS:a1]]. Proposer PAN: [[PAN:pan1]]."),
    ({"p1": "M"}, "SMS: Dear [[PERSON:p1f]], your loan {acct} EMI of Rs {salary} is due on {date}. Ignore if paid."),
    ({"p1": "M", "p2": "F"}, "Field verification report: Visited the residence of [[PERSON:p1]] near [[ADDRESS:c1]]. "
     "His wife [[PERSON:p2]] confirmed that the family has stayed there for 6 years. Voter ID [[VOTER_ID:voter1]] "
     "sighted. Recommend approval."),
    ({"p1": "F"}, "Customer [[PERSON:p1]] (GSTIN [[GSTIN:gst1]]) disputes invoice {ref}. She says the goods were "
     "never delivered to [[ADDRESS:a1]]."),
    ({"p1": "M", "p2": "M", "shared": [("p1", "p2")]}, "Succession claim: [[PERSON:p1]] has passed away. His son "
     "[[PERSON:p2]] (Aadhaar [[AADHAAR:aad2]]) has applied for transfer of the fixed deposit. [[PERSON:p2f]] will "
     "visit the branch with the death certificate."),
    ({"p1": "F"}, "naam: [[PERSON:p1l]]\npata: [[ADDRESS:a1]]\npan: [[PAN:pan1]]\nloan chahiye Rs {amount}"),
    ({"p1": "M", "p2": "F"}, "Minutes of the hearing: Complainant [[PERSON:p1]] stated that the agent [[PERSON:p2]] "
     "collected his passport [[PASSPORT:pass1]] and did not return it. The complainant resides at [[ADDRESS:a1]]."),
    ({"p1": "F"}, "Hello team, I moved from [[ADDRESS:c1]] last month. Please update my communication address to "
     "[[ADDRESS:a1]]. - [[PERSON:p1]], customer since 2015"),
]


def main() -> None:
    g = Gen(SEED)
    docs = []
    for i in range(20):
        meta, tpl = TEMPLATES[i % len(TEMPLATES)]
        text, ents = render(tpl, make_values(g, meta), fillers(g))
        docs.append({"document_id": f"heldout_{i + 1:02d}", "category": "heldout", "text": text, "entities": ents,
                     "hinglish": i % len(TEMPLATES) in (1, 7)})
    shutil.rmtree(ROOT / "heldout", ignore_errors=True)
    (ROOT / "heldout").mkdir()
    for d in docs:
        (ROOT / "heldout" / f"{d['document_id']}.txt").write_text(d["text"], encoding="utf-8", newline="\n")
    (ROOT / "heldout_ground_truth.json").write_text(
        json.dumps({"seed": SEED, "documents": docs}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(docs)} held-out documents, {sum(len(d['entities']) for d in docs)} labelled entities")


if __name__ == "__main__":
    main()
