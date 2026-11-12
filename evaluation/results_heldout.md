# Evaluation report - held-out (never tuned on)

Generated 2026-11-12T16:41:39+00:00 on 24 synthetic documents (76 labelled entities, 4 Hinglish, 4 with no PII). Mock LLM unless stated. Measured on our own seeded synthetic set; not a claim about real-world data.

## Leakage in outbound payloads (target 0)

- Whole PII values found in the audited outbound payload: **0** (of 24 payloads)
- Stricter residue check (any name token or PIN code left): **0**

## Detection - full (relaxed: same type, IoU >= 0.5 / strict: exact span)

| Type | Precision | Recall | F1 | Strict F1 | TP | FP | FN |
|---|---|---|---|---|---|---|---|
| PERSON | 0.776 | 0.950 | 0.854 | 0.854 | 38 | 11 | 2 |
| AADHAAR | 1.000 | 1.000 | 1.000 | 1.000 | 4 | 0 | 0 |
| PAN | 1.000 | 1.000 | 1.000 | 1.000 | 6 | 0 | 0 |
| GSTIN | 1.000 | 1.000 | 1.000 | 1.000 | 2 | 0 | 0 |
| VOTER_ID | 1.000 | 1.000 | 1.000 | 1.000 | 2 | 0 | 0 |
| PASSPORT | 1.000 | 1.000 | 1.000 | 1.000 | 4 | 0 | 0 |
| ADDRESS | 0.842 | 0.889 | 0.865 | 0.757 | 16 | 3 | 2 |
| **overall** | 0.837 | 0.947 | 0.889 | 0.864 | 72 | 14 | 4 |

Gateway overhead per request: mean 246.0 ms, median 222.0 ms, p95 418 ms (n=24). Blocked requests: 0.

## Detection - rules only (relaxed: same type, IoU >= 0.5 / strict: exact span)

| Type | Precision | Recall | F1 | Strict F1 | TP | FP | FN |
|---|---|---|---|---|---|---|---|
| PERSON | 0.875 | 0.350 | 0.500 | 0.500 | 14 | 2 | 26 |
| AADHAAR | 1.000 | 1.000 | 1.000 | 1.000 | 4 | 0 | 0 |
| PAN | 1.000 | 1.000 | 1.000 | 1.000 | 6 | 0 | 0 |
| GSTIN | 1.000 | 1.000 | 1.000 | 1.000 | 2 | 0 | 0 |
| VOTER_ID | 1.000 | 1.000 | 1.000 | 1.000 | 2 | 0 | 0 |
| PASSPORT | 1.000 | 1.000 | 1.000 | 1.000 | 4 | 0 | 0 |
| ADDRESS | 0.625 | 0.278 | 0.385 | 0.231 | 5 | 3 | 13 |
| **overall** | 0.881 | 0.487 | 0.627 | 0.593 | 37 | 5 | 39 |

Gateway overhead per request: mean 0.7 ms, median 1.0 ms, p95 1 ms (n=24). Blocked requests: 0.

## Placeholder reinsertion (mock LLM behaviours)

| LLM behaviour | Placeholders in reply | Restored correctly | Accuracy | Wrong person | Dropped (reported) | Unknown (left as-is) |
|---|---|---|---|---|---|---|
| echo | 74 | 74 | 100.0% | 0 | 0 | 0/0 |
| reorder | 74 | 74 | 100.0% | 0 | 0 | 0/0 |
| paraphrase | 74 | 74 | 100.0% | 0 | 0 | 0/0 |
| drop | 18 | 18 | 100.0% | 0 | 56 | 0/0 |
| unknown | 74 | 74 | 100.0% | 0 | 0 | 40/40 |

Model warm-up at server start: 9547 ms (excluded from per-request overhead).
