# MineArena PS-02 Privacy Gateway

MineArena masks sensitive values locally before sending document text to an LLM, checks the exact outbound payload, restores only request-scoped placeholders locally, and records a sanitized audit trail.

**New to the project? Start with [docs/TEAM_HANDBOOK.md](docs/TEAM_HANDBOOK.md)**: what we built, how to run it, how it works, and every measured number. See [docs/GUIDE.md](docs/GUIDE.md) for architecture diagrams, the Round 1 runbook, judge explanations, team handoffs, and current verification status.

## Start locally

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
# one-time download of the local NER model (~1 GB), so the demo never waits on the network:
python -c "from gliner import GLiNER; GLiNER.from_pretrained('urchade/gliner_multi_pii-v1')"
cp .env.example .env
# Add GEMINI_API_KEY to .env for Gemini. Keep the key out of source control.
uvicorn app.main:app --reload --app-dir backend      # models load at start-up (~8 s)
cd frontend && npm install && npm run dev            # UI at http://localhost:5173
```

Check that every detection layer actually loaded: `GET http://localhost:8000/api/v1/engines`. GLiNER and Presidio should both say `loaded`. If one says `failed`, the reason is shown there and in the server log. The gateway still runs on the rule-based detectors, but name and address recall drops sharply (see below).

For an offline request, send `"provider":"mock"` to `POST /api/v1/gateway/process`. Set `MOCK_MODE` (`echo|reorder|paraphrase|drop|unknown|fail|timeout`) to make the mock LLM misbehave.

## How detection works

| Layer | Finds | How |
|---|---|---|
| India ID recognizers | Aadhaar, PAN, GSTIN, Voter ID, Passport | Exact formats; Verhoeff/GSTIN checksums raise confidence |
| Microsoft Presidio | the same IDs (union) | Built-in `In*Recognizer`s plus ours, inside an `AnalyzerEngine` |
| GLiNER (`urchade/gliner_multi_pii-v1`) | names, addresses | Local NER model; labels `person`/`address`/`location` |
| Context rules | names, addresses | "Mera naam X hai", "Applicant: X", "lives in X": backup only |
| Propagation | other mentions | Repeats and first-name mentions reuse the owner's placeholder; a token shared by two people gets its own |
| Second pass | anything missed | GLiNER re-reads the masked draft line by line |
| Leakage guard | the exact outbound payload | Blocks (HTTP 409) if any mapped value or ID pattern remains |

## Dataset and evaluation (PS-02 3.7 / 3.8)

```bash
python dataset/generate_dataset.py      # 50 seeded synthetic docs, 237 labelled spans
cd dataset && python generate_heldout.py && cd ..   # 20 held-out docs (new phrasings)
python evaluation/run_eval.py --heldout # held-out first, so the main report embeds it
python evaluation/run_eval.py           # add --gemini 10 to include live Gemini requests
```

Results go to [evaluation/results.md](evaluation/results.md) and the **Evaluation** tab in the UI (`GET /api/v1/evaluation`). Latest run:

| | Held-out (never tuned on) | Main set (used for error analysis) |
|---|---|---|
| Raw PII in outbound payloads | **0** / 20 | **0** / 50 |
| Detection F1, relaxed (precision / recall) | 0.900 (0.857 / 0.947) | 1.000 (optimistic) |
| Name recall, GLiNER vs rules only | 0.950 vs 0.300 | 1.000 vs 0.556 |
| Reinsertion accuracy, mock keep/reorder/paraphrase/drop | 100%, 0 wrong-person | 100%, 0 wrong-person |
| Added latency per request (median) | ~215 ms | ~225 ms |

Live Gemini (10 requests): 7 succeeded, 38/38 placeholders restored, 0 leaks. Mean LLM time was 2.6 s against 0.26 s gateway overhead. The 3 failures were provider errors on back-to-back calls, probably free-tier rate limiting (not confirmed).

All numbers are on our own synthetic data. They show the method works; they are not a claim about real-world documents.

## Verify

```bash
pytest tests -q                                   # fast, rules-only, no model downloads
pytest tests/privacy/test_gliner_optional.py tests/privacy/test_presidio_optional.py   # real models
```

Do not use real identity data in demos or tests. Do not commit `.env`.
