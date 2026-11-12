"""Offline evaluation of the privacy gateway on the seeded synthetic dataset (PS-02 section 3.8).

    python dataset/generate_dataset.py
    python evaluation/run_eval.py                 # full engine (GLiNER + Presidio + rules), mock LLM
    python evaluation/run_eval.py --gemini 10     # also send 10 docs through live Gemini (needs GEMINI_API_KEY)

Runs the REAL gateway pipeline in-process (process_document: detect -> mask -> guard -> LLM -> reinsert ->
audit) against a throwaway audit DB. The mock LLM is driven through its modes to exercise reinsertion
when the model echoes, reorders, paraphrases or drops placeholders.

Writes evaluation/results.json (served by GET /api/v1/evaluation) and evaluation/results.md.
Reports only document ids, types and counts - never PII values (all values are synthetic anyway).
"""
import argparse
import asyncio
import json
import os
import re
import statistics
import sys
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent

# configure BEFORE importing the app (config reads env at import; .env never overrides these)
os.environ["AUDIT_DB_PATH"] = str(Path(tempfile.mkdtemp()) / "eval_audit.db")
os.environ["LLM_FALLBACK"] = ""
os.environ.setdefault("PRIVACY_NER", "both")
os.environ.setdefault("PRIVACY_USE_PRESIDIO", "1")
sys.path.insert(0, str(ROOT / "backend"))

from app.core.errors import GatewayError  # noqa: E402
from app.database import db  # noqa: E402
from app.privacy.detection.detection_service import engine_status, preload  # noqa: E402
from app.services.gateway_service import process_document  # noqa: E402

TYPES = ("PERSON", "AADHAAR", "PAN", "GSTIN", "VOTER_ID", "PASSPORT", "ADDRESS")
MOCK_MODES = ("echo", "reorder", "paraphrase", "drop", "unknown")
PH_RE = re.compile(r"<([A-Z_]+_\d+)>")
ENGINES = {
    "full": {"PRIVACY_NER": "both", "PRIVACY_USE_PRESIDIO": "1"},
    "rules_only": {"PRIVACY_NER": "heuristic", "PRIVACY_USE_PRESIDIO": "0"},
}


# ------------------------------------------------------------------ helpers
def run(text, mode, provider="mock", task="extract", rid="eval"):
    os.environ["MOCK_MODE"] = mode
    try:
        return asyncio.run(process_document(text, task, provider, rid)), None
    except GatewayError as e:
        return None, e.code


def iou(a, b):
    inter = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return inter / union if union else 0.0


def match(gold, pred, relaxed):
    """Greedy one-to-one matching of same-type spans. Returns (tp, fp, fn) per type."""
    counts = {t: [0, 0, 0] for t in TYPES}
    used = set()
    for g in gold:
        best, best_j = 0.0, None
        for j, p in enumerate(pred):
            if j in used or p["type"] != g["type"]:
                continue
            score = iou((g["start"], g["end"]), (p["start"], p["end"]))
            ok = score >= 0.5 if relaxed else (p["start"], p["end"]) == (g["start"], g["end"])
            if ok and score > best:
                best, best_j = score, j
        if best_j is None:
            counts[g["type"]][2] += 1
        else:
            used.add(best_j)
            counts[g["type"]][0] += 1
    for j, p in enumerate(pred):
        if j not in used and p["type"] in counts:
            counts[p["type"]][1] += 1
    return counts


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3), "tp": tp, "fp": fp, "fn": fn}


def detection_report(per_doc):
    out = {}
    for mode in ("strict", "relaxed"):
        tot = {t: [0, 0, 0] for t in TYPES}
        for gold, pred in per_doc:
            for t, c in match(gold, pred, mode == "relaxed").items():
                for i in range(3):
                    tot[t][i] += c[i]
        per_type = {t: prf(*tot[t]) for t in TYPES}
        overall = prf(*(sum(tot[t][i] for t in TYPES) for i in range(3)))
        out[mode] = {"per_type": per_type, "overall": overall}
    return out


def leaked_values(doc, payload):
    """Ground-truth values still present in the exact outbound payload.
    full_value: the whole value (Aadhaar compared digits-only, IDs ignoring spaces/case).
    token: any name token (>= 3 letters) or 6-digit PIN code of the value - stricter residue check."""
    fold = payload.casefold()
    digits = re.sub(r"\D", "", payload)
    nospace = re.sub(r"\s+", "", fold)
    full, tokens = [], []
    for e in doc["entities"]:
        v = e["text"]
        if e["type"] == "AADHAAR":
            hit = re.sub(r"\D", "", v) in digits
        elif e["type"] in ("PAN", "GSTIN", "VOTER_ID", "PASSPORT"):
            hit = re.sub(r"\s+", "", v).casefold() in nospace
        else:
            hit = re.search(r"(?<![a-z0-9])" + re.escape(" ".join(v.split()).casefold()) + r"(?![a-z0-9])",
                            " ".join(fold.split())) is not None
        if hit:
            full.append({"doc": doc["document_id"], "type": e["type"]})
        if e["type"] in ("PERSON", "ADDRESS"):
            parts = re.findall(r"[A-Za-z]{3,}", v) if e["type"] == "PERSON" else re.findall(r"\b\d{6}\b", v)
            for tok in parts:
                if re.search(r"(?<![a-z0-9])" + re.escape(tok.casefold()) + r"(?![a-z0-9])", fold):
                    tokens.append({"doc": doc["document_id"], "type": e["type"]})
                    break
    return full, tokens


def placeholder_identities(doc, entities):
    """placeholder -> set of ground-truth identities (refs) its masked spans cover."""
    ids = defaultdict(set)
    for p in entities:
        for g in doc["entities"]:
            if g["type"] == p["type"] and min(g["end"], p["end"]) > max(g["start"], p["start"]):
                ids[p["placeholder"]].add(g["ref"])
    return ids


def reinsertion_check(doc, res):
    """Per placeholder occurrence in the LLM reply: restored to the right original value?"""
    text = doc["text"]
    first = {}
    for e in res["entities"]:
        first.setdefault(e["placeholder"], text[e["start"]:e["end"]])
    ids = placeholder_identities(doc, res["entities"])
    expected = correct = wrong_person = 0
    for m in PH_RE.finditer(res["llm_response"]):
        ph = f"<{m.group(1)}>"
        if ph not in first:
            continue  # unknown placeholder: must NOT be restored (checked separately)
        expected += 1
        if ph not in res["final_response"] and first[ph] in res["final_response"]:
            correct += 1
        if len(ids.get(ph, ())) > 1:
            wrong_person += 1  # this placeholder covers two different people/IDs
    unknown_restored = sum(1 for u in res["unknown_placeholders"] if u in res["final_response"])  # left as-is, not guessed
    return expected, correct, wrong_person, len(res["missing_placeholders"]), \
        len(res["unknown_placeholders"]), unknown_restored


def pct(values, q):
    s = sorted(values)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))] if s else 0


# ------------------------------------------------------------------ main
def evaluate(docs, gemini_n):
    report = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "dataset": {"documents": len(docs), "entities": sum(len(d["entities"]) for d in docs),
                          "hinglish_documents": sum(d.get("hinglish", False) for d in docs),
                          "negative_documents": sum(not d["entities"] for d in docs),
                          "per_type": {t: sum(e["type"] == t for d in docs for e in d["entities"]) for t in TYPES}}}
    db.init_db()

    # warm models first so latency numbers are steady-state, and report the cold start separately
    os.environ.update(ENGINES["full"])
    t0 = time.perf_counter()
    report["engines"] = preload()
    report["model_load_ms"] = int((time.perf_counter() - t0) * 1000)

    report["detection"] = {}
    full_results = {}
    for engine, env in ENGINES.items():
        os.environ.update(env)
        per_doc, overhead, blocked = [], [], []
        for i, d in enumerate(docs):
            res, err = run(d["text"], "echo", rid=f"eval_{engine}_{i}")
            if err:
                blocked.append({"doc": d["document_id"], "error": err})
                per_doc.append((d["entities"], []))
                continue
            per_doc.append((d["entities"], res["entities"]))
            overhead.append(res["gateway_overhead_ms"])
            if engine == "full":
                full_results[d["document_id"]] = res
        report["detection"][engine] = detection_report(per_doc)
        report["detection"][engine]["blocked_requests"] = blocked
        report["detection"][engine]["latency_overhead_ms"] = {
            "n": len(overhead), "mean": round(statistics.mean(overhead), 1) if overhead else 0,
            "median": statistics.median(overhead) if overhead else 0, "p95": pct(overhead, 0.95),
            "max": max(overhead, default=0)}
    report["detection"]["headline"] = "relaxed"

    # leakage on the exact audited outbound payload (full engine)
    os.environ.update(ENGINES["full"])
    full_leaks, token_leaks = [], []
    for d in docs:
        res = full_results.get(d["document_id"])
        if res is None:
            continue
        audited = db.get_audit(res["request_id"])["sanitized_payload"]
        f, t = leaked_values(d, audited)
        full_leaks += f
        token_leaks += t
    report["leakage"] = {"full_value_count": len(full_leaks), "full_value": full_leaks,
                         "token_residue_count": len(token_leaks), "token_residue": token_leaks,
                         "checked_payloads": len(full_results), "source": "audit_logs.sanitized_payload"}

    # reinsertion under each mock LLM behaviour
    rein = {}
    for mode in MOCK_MODES:
        agg = defaultdict(int)
        for i, d in enumerate(docs):
            if not d["entities"]:
                continue
            res, err = run(d["text"], mode, rid=f"eval_rein_{mode}_{i}")
            if err:
                agg["errors"] += 1
                continue
            e, c, w, miss, unk, unk_ok = reinsertion_check(d, res)
            agg["expected"] += e
            agg["correct"] += c
            agg["wrong_person"] += w
            agg["dropped_reported"] += miss
            agg["unknown_seen"] += unk
            agg["unknown_left_unrestored"] += unk_ok
            agg["documents"] += 1
        agg["accuracy"] = round(agg["correct"] / agg["expected"], 4) if agg["expected"] else None
        rein[mode] = dict(agg)
    report["reinsertion"] = rein

    if gemini_n:
        report["gemini"] = gemini_run(docs, gemini_n)
    return report


def gemini_run(docs, n):
    picked = [d for d in docs if d["entities"]][:: max(1, len([d for d in docs if d["entities"]]) // n)][:n]
    rows, agg = [], defaultdict(int)
    for i, d in enumerate(picked):
        res, err = run(d["text"], "echo", provider="gemini", task="summarize" if i % 2 else "extract",
                       rid=f"eval_gemini_{i}")
        if err:
            rows.append({"doc": d["document_id"], "error": err})
            continue
        e, c, w, miss, unk, _ = reinsertion_check(d, res)
        f, t = leaked_values(d, db.get_audit(res["request_id"])["sanitized_payload"])
        for k, v in (("expected", e), ("correct", c), ("wrong_person", w), ("dropped", miss), ("unknown", unk),
                     ("leaks", len(f) + len(t))):
            agg[k] += v
        rows.append({"doc": d["document_id"], "model": res["model"], "fallback": res["fallback_used"],
                     "llm_ms": res["llm_time_ms"], "overhead_ms": res["gateway_overhead_ms"],
                     "placeholders_in_reply": e, "restored": c, "dropped": miss})
    ok = [r for r in rows if "error" not in r]
    agg["accuracy"] = round(agg["correct"] / agg["expected"], 4) if agg["expected"] else None
    agg["mean_llm_ms"] = round(statistics.mean(r["llm_ms"] for r in ok), 1) if ok else None
    agg["mean_overhead_ms"] = round(statistics.mean(r["overhead_ms"] for r in ok), 1) if ok else None
    return {"requests": len(picked), "succeeded": len(ok), "summary": dict(agg), "rows": rows}


def to_markdown(r):
    L = [f"# Evaluation report - {r['dataset'].get('name', 'main')}", "", f"Generated {r['generated_at']} on {r['dataset']['documents']} synthetic documents "
         f"({r['dataset']['entities']} labelled entities, {r['dataset']['hinglish_documents']} Hinglish, "
         f"{r['dataset']['negative_documents']} with no PII). Mock LLM unless stated. "
         "Measured on our own seeded synthetic set; not a claim about real-world data.", ""]
    lk = r["leakage"]
    L += ["## Leakage in outbound payloads (target 0)", "",
          f"- Whole PII values found in the audited outbound payload: **{lk['full_value_count']}** "
          f"(of {lk['checked_payloads']} payloads)",
          f"- Stricter residue check (any name token or PIN code left): **{lk['token_residue_count']}**", ""]
    for engine in ENGINES:
        det = r["detection"][engine]
        L += [f"## Detection - {engine.replace('_', ' ')} (relaxed: same type, IoU >= 0.5 / strict: exact span)", "",
              "| Type | Precision | Recall | F1 | Strict F1 | TP | FP | FN |", "|---|---|---|---|---|---|---|---|"]
        for t in TYPES + ("overall",):
            rel = det["relaxed"]["overall"] if t == "overall" else det["relaxed"]["per_type"][t]
            st = det["strict"]["overall"] if t == "overall" else det["strict"]["per_type"][t]
            name = f"**{t}**" if t == "overall" else t
            L.append(f"| {name} | {rel['precision']:.3f} | {rel['recall']:.3f} | {rel['f1']:.3f} | {st['f1']:.3f} | "
                     f"{rel['tp']} | {rel['fp']} | {rel['fn']} |")
        lat = det["latency_overhead_ms"]
        L += ["", f"Gateway overhead per request: mean {lat['mean']} ms, median {lat['median']} ms, "
              f"p95 {lat['p95']} ms (n={lat['n']}). Blocked requests: {len(det['blocked_requests'])}.", ""]
    L += ["## Placeholder reinsertion (mock LLM behaviours)", "",
          "| LLM behaviour | Placeholders in reply | Restored correctly | Accuracy | Wrong person | Dropped (reported) | Unknown (left as-is) |",
          "|---|---|---|---|---|---|---|"]
    for mode, a in r["reinsertion"].items():
        acc = f"{a['accuracy'] * 100:.1f}%" if a.get("accuracy") is not None else "n/a"
        L.append(f"| {mode} | {a.get('expected', 0)} | {a.get('correct', 0)} | {acc} | {a.get('wrong_person', 0)} | "
                 f"{a.get('dropped_reported', 0)} | {a.get('unknown_left_unrestored', 0)}/{a.get('unknown_seen', 0)} |")
    if "gemini" in r:
        g = r["gemini"]["summary"]
        acc = f"{g['accuracy'] * 100:.1f}%" if g.get("accuracy") is not None else "n/a"
        L += ["", "## Live Gemini sample", "",
              f"{r['gemini']['succeeded']}/{r['gemini']['requests']} requests succeeded. Reinsertion {acc} "
              f"({g.get('correct', 0)}/{g.get('expected', 0)}), wrong person {g.get('wrong_person', 0)}, "
              f"leaks {g.get('leaks', 0)}. Mean LLM time {g.get('mean_llm_ms')} ms vs mean gateway overhead "
              f"{g.get('mean_overhead_ms')} ms."]
    L += ["", f"Model warm-up at server start: {r['model_load_ms']} ms (excluded from per-request overhead)."]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gemini", type=int, default=0, help="also send N documents through live Gemini")
    ap.add_argument("--heldout", action="store_true",
                    help="evaluate dataset/heldout_ground_truth.json (never tuned on) -> results_heldout.*")
    args = ap.parse_args()
    name = "heldout_ground_truth.json" if args.heldout else "ground_truth.json"
    gt = json.loads((ROOT / "dataset" / name).read_text(encoding="utf-8"))
    report = evaluate(gt["documents"], args.gemini)
    report["dataset"]["seed"] = gt.get("seed")
    report["dataset"]["name"] = "held-out (never tuned on)" if args.heldout else "main (used for error analysis)"
    stem = "results_heldout" if args.heldout else "results"
    if not args.heldout:
        held = OUT / "results_heldout.json"  # embed the held-out summary so the UI shows both
        if held.is_file():
            h = json.loads(held.read_text(encoding="utf-8"))
            report["heldout"] = {"dataset": h["dataset"], "leakage": h["leakage"],
                                 "detection": {"full": h["detection"]["full"]}, "reinsertion": h["reinsertion"]}
    (OUT / f"{stem}.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    md = to_markdown(report)
    (OUT / f"{stem}.md").write_text(md, encoding="utf-8", newline="\n")
    print(md)


if __name__ == "__main__":
    main()
