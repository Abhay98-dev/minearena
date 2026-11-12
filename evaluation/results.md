# Evaluation report - main (used for error analysis)

Generated 2026-11-12T14:45:14+00:00 on 50 synthetic documents (237 labelled entities, 10 Hinglish, 5 with no PII). Mock LLM unless stated. Measured on our own seeded synthetic set; not a claim about real-world data.

## Leakage in outbound payloads (target 0)

- Whole PII values found in the audited outbound payload: **0** (of 50 payloads)
- Stricter residue check (any name token or PIN code left): **0**

## Detection - full (relaxed: same type, IoU >= 0.5 / strict: exact span)

| Type | Precision | Recall | F1 | Strict F1 | TP | FP | FN |
|---|---|---|---|---|---|---|---|
| PERSON | 1.000 | 1.000 | 1.000 | 1.000 | 99 | 0 | 0 |
| AADHAAR | 1.000 | 1.000 | 1.000 | 1.000 | 25 | 0 | 0 |
| PAN | 1.000 | 1.000 | 1.000 | 1.000 | 35 | 0 | 0 |
| GSTIN | 1.000 | 1.000 | 1.000 | 1.000 | 9 | 0 | 0 |
| VOTER_ID | 1.000 | 1.000 | 1.000 | 1.000 | 12 | 0 | 0 |
| PASSPORT | 1.000 | 1.000 | 1.000 | 1.000 | 12 | 0 | 0 |
| ADDRESS | 1.000 | 1.000 | 1.000 | 0.889 | 45 | 0 | 0 |
| **overall** | 1.000 | 1.000 | 1.000 | 0.979 | 237 | 0 | 0 |

Gateway overhead per request: mean 240.6 ms, median 225.0 ms, p95 298 ms (n=50). Blocked requests: 0.

## Detection - rules only (relaxed: same type, IoU >= 0.5 / strict: exact span)

| Type | Precision | Recall | F1 | Strict F1 | TP | FP | FN |
|---|---|---|---|---|---|---|---|
| PERSON | 0.948 | 0.556 | 0.701 | 0.701 | 55 | 3 | 44 |
| AADHAAR | 1.000 | 1.000 | 1.000 | 1.000 | 25 | 0 | 0 |
| PAN | 1.000 | 1.000 | 1.000 | 1.000 | 35 | 0 | 0 |
| GSTIN | 1.000 | 1.000 | 1.000 | 1.000 | 9 | 0 | 0 |
| VOTER_ID | 1.000 | 1.000 | 1.000 | 1.000 | 12 | 0 | 0 |
| PASSPORT | 1.000 | 1.000 | 1.000 | 1.000 | 12 | 0 | 0 |
| ADDRESS | 0.862 | 0.556 | 0.676 | 0.541 | 25 | 4 | 20 |
| **overall** | 0.961 | 0.730 | 0.830 | 0.806 | 173 | 7 | 64 |

Gateway overhead per request: mean 0.3 ms, median 0.0 ms, p95 1 ms (n=50). Blocked requests: 0.

## Placeholder reinsertion (mock LLM behaviours)

| LLM behaviour | Placeholders in reply | Restored correctly | Accuracy | Wrong person | Dropped (reported) | Unknown (left as-is) |
|---|---|---|---|---|---|---|
| echo | 211 | 211 | 100.0% | 0 | 0 | 0/0 |
| reorder | 211 | 211 | 100.0% | 0 | 0 | 0/0 |
| paraphrase | 211 | 211 | 100.0% | 0 | 0 | 0/0 |
| drop | 45 | 45 | 100.0% | 0 | 166 | 0/0 |
| unknown | 211 | 211 | 100.0% | 0 | 0 | 90/90 |

Model warm-up at server start: 7920 ms (excluded from per-request overhead).
