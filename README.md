# MineArena PS-02 Privacy Gateway

MineArena masks sensitive values locally before sending document text to an LLM, checks the exact outbound payload, restores only request-scoped placeholders locally, and records a sanitized audit trail.

See [docs/GUIDE.md](docs/GUIDE.md) for architecture diagrams, the Round 1 runbook, judge explanations, team handoffs, and current verification status.

## Start locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Add GEMINI_API_KEY to .env for Gemini. Keep the key out of source control.
uvicorn app.main:app --reload --app-dir backend
```

Health check: `GET http://localhost:8000/api/v1/health`.

For an offline request, send `"provider":"mock"` to `POST /api/v1/gateway/process`. To test the API-backed provider, configure a valid key and model in `.env`. Optional local NER and Presidio setup are described in `docs/GUIDE.md` and the master guide.

## Verify

```bash
pytest tests -q
```

Do not use real identity data in demos or tests. Do not commit `.env`.
