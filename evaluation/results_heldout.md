# Evaluation report - held-out (never tuned on)

Generated 2026-11-12T14:44:23+00:00 on 20 synthetic documents (76 labelled entities, 4 Hinglish, 0 with no PII). Mock LLM unless stated. Measured on our own seeded synthetic set; not a claim about real-world data.

## Leakage in outbound payloads (target 0)

- Whole PII values found in the audited outbound payload: **0** (of 20 payloads)
- Stricter residue check (any name token or PIN code left): **0**

## Detection - full (relaxed: same type, IoU >= 0.5 / strict: exact span)

| Type | Precision | Recall | F1 | Strict F1 | TP | FP | FN |
|---|---|---|---|---|---|---|---|
| PERSON | 0.792 | 0.950 | 0.864 | 0.864 | 38 | 10 | 2 |
| AADHAAR | 1.000 | 1.000 | 1.000 | 1.000 | 4 | 0 | 0 |
| PAN | 1.000 | 1.000 | 1.000 | 1.000 | 6 | 0 | 0 |
| GSTIN | 1.000 | 1.000 | 1.000 | 1.000 | 2 | 0 | 0 |
| VOTER_ID | 1.000 | 1.000 | 1.000 | 1.000 | 2 | 0 | 0 |
| PASSPORT | 1.000 | 1.000 | 1.000 | 1.000 | 4 | 0 | 0 |
| ADDRESS | 0.889 | 0.889 | 0.889 | 0.778 | 16 | 2 | 2 |
| **overall** | 0.857 | 0.947 | 0.900 | 0.875 | 72 | 12 | 4 |

Gateway overhead per request: mean 236.9 ms, median 215.0 ms, p95 402 ms (n=20). Blocked requests: 0.

## Detection - rules only (relaxed: same type, IoU >= 0.5 / strict: exact span)

| Type | Precision | Recall | F1 | Strict F1 | TP | FP | FN |
|---|---|---|---|---|---|---|---|
| PERSON | 0.857 | 0.300 | 0.444 | 0.444 | 12 | 2 | 28 |
| AADHAAR | 1.000 | 1.000 | 1.000 | 1.000 | 4 | 0 | 0 |
| PAN | 1.000 | 1.000 | 1.000 | 1.000 | 6 | 0 | 0 |
| GSTIN | 1.000 | 1.000 | 1.000 | 1.000 | 2 | 0 | 0 |
| VOTER_ID | 1.000 | 1.000 | 1.000 | 1.000 | 2 | 0 | 0 |
| PASSPORT | 1.000 | 1.000 | 1.000 | 1.000 | 4 | 0 | 0 |
| ADDRESS | 0.625 | 0.278 | 0.385 | 0.231 | 5 | 3 | 13 |
| **overall** | 0.875 | 0.461 | 0.603 | 0.569 | 35 | 5 | 41 |

Gateway overhead per request: mean 0.2 ms, median 0.0 ms, p95 1 ms (n=20). Blocked requests: 0.

## Placeholder reinsertion (mock LLM behaviours)

| LLM behaviour | Placeholders in reply | Restored correctly | Accuracy | Wrong person | Dropped (reported) | Unknown (left as-is) |
|---|---|---|---|---|---|---|
| echo | 74 | 74 | 100.0% | 0 | 0 | 0/0 |
| reorder | 74 | 74 | 100.0% | 0 | 0 | 0/0 |
| paraphrase | 74 | 74 | 100.0% | 0 | 0 | 0/0 |
| drop | 18 | 18 | 100.0% | 0 | 56 | 0/0 |
| unknown | 74 | 74 | 100.0% | 0 | 0 | 40/40 |

Model warm-up at server start: 8183 ms (excluded from per-request overhead).
