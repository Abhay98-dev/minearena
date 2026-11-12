# Evaluation report - main (used for error analysis)

Generated 2026-11-12T16:42:52+00:00 on 50 synthetic documents (230 labelled entities, 11 Hinglish, 5 with no PII). Mock LLM unless stated. Measured on our own seeded synthetic set; not a claim about real-world data.

## Leakage in outbound payloads (target 0)

- Whole PII values found in the audited outbound payload: **0** (of 50 payloads)
- Stricter residue check (any name token or PIN code left): **0**

## Detection - full (relaxed: same type, IoU >= 0.5 / strict: exact span)

| Type | Precision | Recall | F1 | Strict F1 | TP | FP | FN |
|---|---|---|---|---|---|---|---|
| PERSON | 1.000 | 1.000 | 1.000 | 1.000 | 94 | 0 | 0 |
| AADHAAR | 1.000 | 1.000 | 1.000 | 1.000 | 25 | 0 | 0 |
| PAN | 1.000 | 1.000 | 1.000 | 1.000 | 35 | 0 | 0 |
| GSTIN | 1.000 | 1.000 | 1.000 | 1.000 | 8 | 0 | 0 |
| VOTER_ID | 1.000 | 1.000 | 1.000 | 1.000 | 12 | 0 | 0 |
| PASSPORT | 1.000 | 1.000 | 1.000 | 1.000 | 10 | 0 | 0 |
| ADDRESS | 1.000 | 1.000 | 1.000 | 0.913 | 46 | 0 | 0 |
| **overall** | 1.000 | 1.000 | 1.000 | 0.983 | 230 | 0 | 0 |

Gateway overhead per request: mean 265.2 ms, median 252.5 ms, p95 337 ms (n=50). Blocked requests: 0.

## Detection - rules only (relaxed: same type, IoU >= 0.5 / strict: exact span)

| Type | Precision | Recall | F1 | Strict F1 | TP | FP | FN |
|---|---|---|---|---|---|---|---|
| PERSON | 0.950 | 0.606 | 0.740 | 0.727 | 57 | 3 | 37 |
| AADHAAR | 1.000 | 1.000 | 1.000 | 1.000 | 25 | 0 | 0 |
| PAN | 1.000 | 1.000 | 1.000 | 1.000 | 35 | 0 | 0 |
| GSTIN | 1.000 | 1.000 | 1.000 | 1.000 | 8 | 0 | 0 |
| VOTER_ID | 1.000 | 1.000 | 1.000 | 1.000 | 12 | 0 | 0 |
| PASSPORT | 1.000 | 1.000 | 1.000 | 1.000 | 10 | 0 | 0 |
| ADDRESS | 0.903 | 0.609 | 0.727 | 0.597 | 28 | 3 | 18 |
| **overall** | 0.967 | 0.761 | 0.852 | 0.822 | 175 | 6 | 55 |

Gateway overhead per request: mean 0.9 ms, median 1.0 ms, p95 1 ms (n=50). Blocked requests: 0.

## Placeholder reinsertion (mock LLM behaviours)

| LLM behaviour | Placeholders in reply | Restored correctly | Accuracy | Wrong person | Dropped (reported) | Unknown (left as-is) |
|---|---|---|---|---|---|---|
| echo | 207 | 207 | 100.0% | 0 | 0 | 0/0 |
| reorder | 207 | 207 | 100.0% | 0 | 0 | 0/0 |
| paraphrase | 207 | 207 | 100.0% | 0 | 0 | 0/0 |
| drop | 45 | 45 | 100.0% | 0 | 162 | 0/0 |
| unknown | 207 | 207 | 100.0% | 0 | 0 | 90/90 |

Model warm-up at server start: 8436 ms (excluded from per-request overhead).
