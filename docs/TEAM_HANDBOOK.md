# MineArena PS-02 — Team Handbook

> **Read this first.** This file explains everything we have built for PS-02 (DPDP-Ready Privacy Gateway):
> what it is, how to run it, how each part works, how we know it works, and our measured precision and recall.
> You need nothing else to get started. Every command is written out in full.
>
> - Branch: `feature/robust-detection-eval`
> - Last updated: 12 Nov 2026, evening (teammate review fixes, see [section 14](#14-changes-after-the-teammate-review-12-nov-evening))
> - All data in this repo is **synthetic**. Never put a real person's details into it.

---

## Contents

1. [The 60-second summary](#1-the-60-second-summary)
2. [What the problem statement asks for, and where we do it](#2-what-the-problem-statement-asks-for-and-where-we-do-it)
3. [How to run it (step by step)](#3-how-to-run-it-step-by-step)
4. [How everything works](#4-how-everything-works)
5. [How we are sure it works](#5-how-we-are-sure-it-works)
6. [Precision, recall and every other number](#6-precision-recall-and-every-other-number)
7. [The demo: what to show the judges](#7-the-demo-what-to-show-the-judges)
8. [Questions judges will ask, and our answers](#8-questions-judges-will-ask-and-our-answers)
9. [Known limitations (say these before the judges do)](#9-known-limitations-say-these-before-the-judges-do)
10. [Rules for changing the code](#10-rules-for-changing-the-code)
11. [Troubleshooting](#11-troubleshooting)
12. [File map](#12-file-map)
13. [Glossary](#13-glossary)
14. [Changes after the teammate review (12 Nov evening)](#14-changes-after-the-teammate-review-12-nov-evening)

---

## 1. The 60-second summary

- **What it is:** a **privacy gateway**: a small server that sits between a company's apps and an outside AI model (we use Google Gemini).
  - An app sends it a document, for example a loan application.
  - The gateway finds personal details **on our own machine**: names, addresses, Aadhaar, PAN, GSTIN, Voter ID and passport numbers.
  - It replaces each one with a tag such as `<PERSON_1>` or `<PAN_1>`.
  - It **checks the exact text about to leave**. If any real value is still in it, the request is blocked and the AI is never called.
  - It sends **only the tagged text** to Gemini.
  - When Gemini answers, it swaps the tags back to the real values **locally**.
  - It writes an audit record of what was sent and to which model, but never the real values.
- **Example:**
  - In: `My name is Rahul Sharma. My Aadhaar number is 1234-5678-9012 and my PAN is ABCDE1234F.`
  - Sent to Gemini: `My name is <PERSON_1>. My Aadhaar number is <AADHAAR_1> and my PAN is <PAN_1>.`
  - Gemini's reply is restored locally, so the final answer contains "Rahul Sharma" again.
- **Headline results** (synthetic data; full tables in [section 6](#6-precision-recall-and-every-other-number)):
  - **0** raw personal values found in any outbound payload, across 74 test documents.
  - Detection **F1 = 0.89** on 24 "held-out" documents: 20 written in phrasings we never tuned on, plus 4 with no personal data at all (precision 0.84, recall 0.95).
  - Restoring values when the AI reorders, paraphrases or drops tags: **100% correct, 0 wrong-person restorations**.
  - The gateway adds about **0.25 seconds** per request. Gemini itself takes about 2.6 seconds.
- **Tech stack:**
  - Python 3.12 with FastAPI (backend).
  - Microsoft Presidio plus our own India ID recognizers.
  - GLiNER, a local AI model for spotting names and addresses.
  - SQLite (audit log).
  - React + Vite (UI).

---

## 2. What the problem statement asks for, and where we do it

The PDF is `MineArena_PS02_DPDP_Privacy_Gateway.pdf`. Section numbers below are the PDF's.

- **3.1 PII detection engine**: done.
  - Microsoft Presidio, with India recognizers switched on: `backend/app/privacy/detection/presidio_engine.py`.
    - Presidio's own `InAadhaarRecognizer`, `InPanRecognizer`, `InGstinRecognizer`, `InVoterRecognizer` and `InPassportRecognizer`, **plus** ours wrapped as Presidio recognizers.
  - Detects Aadhaar, PAN, GSTIN, Voter ID and Passport: `backend/app/privacy/detection/india_recognizers.py`.
  - Local NER model for names and addresses: **GLiNER** (`urchade/gliner_multi_pii-v1`) in `backend/app/privacy/detection/ner_engine.py`.
  - Indian English and code-mixed (Hinglish) text: GLiNER is multilingual. There are also Hinglish rules ("Mera naam X hai", "X ne…", "Pune mein rehta hoon").
- **3.2 Masking and consistent placeholders**: done.
  - Tags look like `<PERSON_1>`, `<AADHAAR_1>`, `<PAN_1>`, `<GSTIN_1>`, `<ADDRESS_1>`, `<PASSPORT_1>`, `<VOTER_ID_1>`.
  - The same person or value always gets the same tag within one request, including first-name-only mentions.
  - The tag-to-value mapping lives **only in server memory**, for **one request**, and is destroyed afterwards: `backend/app/privacy/mapping/mapping_store.py`.
- **3.3 Gateway API with 4 stages** (Detect, Mask, Forward, Reinsert): done.
  - `POST /api/v1/gateway/process`: `backend/app/services/gateway_service.py`.
  - Pluggable LLM backend: `gemini`, `ollama` (local model) and `mock` (offline test model), in `backend/app/services/llm/`.
- **3.4 External LLM integration**: done, with Gemini `gemini-2.5-flash`, verified live.
  - The **exact** payload sent is stored in the audit log and returned as `outbound_payload`.
- **3.5 Local reinsertion**: done.
  - Handles reordered, paraphrased, dropped and invented tags.
  - Never puts one person's value into another person's tag.
  - Code: `backend/app/privacy/reinsertion/reinsertion_service.py`.
- **3.6 Demo interface, three sections side by side**: done.
  - React UI in `frontend/`. Columns: **A** original input, **B** exact outbound payload plus entity table, **C** final response.
- **3.7 About 50 synthetic labelled documents**: done.
  - 50 documents (15 loan, 15 KYC, 10 support, 10 insurance) with 230 labelled values, including raw JSON, `key=value` and lowercase-chat formats, plus 24 extra "held-out" documents (4 of them with no personal data).
  - Code: `dataset/`.
- **3.8 Metrics report**: done.
  - Leakage count, precision and recall per type, reinsertion accuracy and added latency.
  - `evaluation/results.md`, also shown in the UI's **Evaluation** tab.
- **Section 5 (optional extras)**: not done, by decision; the mandatory items came first.
  - Purpose-based policies: not built.
  - Format-preserving tokens: not built.
  - Local model fallback: the `ollama` provider exists in code but is **untested**.

---

## 3. How to run it (step by step)

### 3.1 One-time setup

- **You need:**
  - **Python 3.12** (3.10+ should work; we tested 3.12).
  - **Node.js 20+** (we tested 24) with npm.
  - **git**.
  - About **2 GB of free disk** (the NER model is about 1.1 GB).
  - Internet **once**, to download packages and the model.
- **Step 1: get the code**
  - `git clone <our repo URL>`
  - `cd <repo folder>`
  - `git checkout feature/robust-detection-eval` (until it is merged into main)
- **Step 2: Python environment** (from the repo root)
  - Windows (PowerShell):
    ```powershell
    py -3.12 -m venv .venv
    .venv\Scripts\activate
    ```
  - Mac / Linux:
    ```bash
    python3.12 -m venv .venv
    source .venv/bin/activate
    ```
  - Then, on any OS:
    ```bash
    pip install -r requirements.txt
    python -m spacy download en_core_web_sm
    ```
- **Step 3: download the NER model once** (about 1.1 GB, a few minutes)
  ```bash
  python -c "from gliner import GLiNER; GLiNER.from_pretrained('urchade/gliner_multi_pii-v1')"
  ```
  - It is cached in your user folder (`~/.cache/huggingface/`), so later runs work offline.
- **Step 4: settings file**
  - Copy `.env.example` to `.env` (Windows: `copy .env.example .env`; Mac/Linux: `cp .env.example .env`).
  - To use Gemini, put your key after `GEMINI_API_KEY=`.
    - Get a key from Google AI Studio.
    - **Never commit `.env`.** It is already in `.gitignore`.
  - Without a key, use the `mock` provider; everything else still works.
- **Step 5: frontend packages**
  ```bash
  cd frontend
  npm install
  cd ..
  ```

### 3.2 Every time you want to run it

- **Terminal 1, backend** (repo root, venv activated):
  ```bash
  uvicorn app.main:app --reload --app-dir backend
  ```
  - Wait about 8–10 seconds: the models load at start-up.
  - It is ready when you see `Uvicorn running on http://127.0.0.1:8000`.
- **Terminal 2, frontend:**
  ```bash
  cd frontend
  npm run dev
  ```
  - Open **http://localhost:5173** in a browser.
- **Check that everything really loaded** (important):
  - Open http://localhost:8000/api/v1/engines in the browser.
  - `gliner` and `presidio` must both say `"status": "loaded"`.
  - The UI shows the same thing as two green chips at the top right.
  - If one says `failed`, see [Troubleshooting](#11-troubleshooting). The gateway still works, but name and address detection gets much worse.

### 3.3 Settings you can change (in `.env`)

| Setting | Default | What it does |
|---|---|---|
| `GEMINI_API_KEY` | empty | Your Gemini key. Needed only for `provider: gemini`. |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Which Gemini model to call. |
| `DEFAULT_PROVIDER` | `gemini` | Provider used when a request doesn't name one. |
| `LLM_FALLBACK` | empty | If set to `mock` or `ollama`, used when Gemini fails. Keep it empty to see Gemini errors honestly. |
| `PRIVACY_NER` | `both` | `both` = GLiNER + rules (use this). `heuristic` = rules only (what the tests use). |
| `PRIVACY_USE_PRESIDIO` | `1` | Turns the Presidio layer on (`1`) or off (`0`). |
| `GLINER_MODEL` | `urchade/gliner_multi_pii-v1` | The NER model. |
| `GLINER_THRESHOLD` | `0.35` | Minimum confidence for a name or address. Lower = more masking. |
| `PRIVACY_PRELOAD` | `1` | Load models when the server starts instead of on the first request. |
| `MOCK_MODE` | `echo` | How the fake LLM behaves: `echo`, `reorder`, `paraphrase`, `drop`, `unknown`, `fail`, `timeout`. |
| `MAX_INPUT_CHARS` | `20000` | Longest document accepted. |
| `LLM_TIMEOUT_S` | `30` | Seconds before an LLM call counts as timed out. |
| `AUDIT_DB_PATH` | `audit.db` | Where the SQLite audit log is written. |

- **Restart the backend after changing `.env`.**

### 3.4 Sending a request without the UI

```bash
curl -X POST http://localhost:8000/api/v1/gateway/process \
  -H "Content-Type: application/json" \
  -d '{"text":"My name is Rahul Sharma. My PAN is ABCDE1234F.","task":"summarize","provider":"mock"}'
```

- `task` is `summarize` or `extract`.
- `provider` is `mock`, `gemini` or `ollama`.
- Other endpoints (all `GET`, all under `http://localhost:8000/api/v1`):
  - `/health`: is the server up.
  - `/engines`: which detection layers loaded (new).
  - `/audit` and `/audit/{request_id}`: audit records.
  - `/metrics`: totals from the audit log.
  - `/evaluation`: the latest evaluation report (new).

### 3.5 Running the tests

```bash
pytest tests -q
```
- Expected: **78 passed**, in about 10 seconds.
- These tests use the **rules-only** mode on purpose (fast, no model needed).

```bash
pytest tests/privacy/test_gliner_optional.py tests/privacy/test_presidio_optional.py -q
```
- Expected: **8 passed**.
- These use the **real** GLiNER and Presidio models.
- They are *skipped*, not failed, if the model is not downloaded.

### 3.6 Re-creating the dataset and the evaluation report

```bash
python dataset/generate_dataset.py                    # 50 documents
cd dataset && python generate_heldout.py && cd ..     # 20 held-out documents
python evaluation/run_eval.py --heldout               # held-out first
python evaluation/run_eval.py                         # main set (embeds the held-out summary)
python evaluation/run_eval.py --gemini 10             # optional: also 10 real Gemini calls
```

- The generators are **seeded**, so they produce exactly the same files every time.
- Results go to `evaluation/results.md`, `evaluation/results.json` and the held-out equivalents.
- The UI's Evaluation tab reads `results.json`.
- The main evaluation takes about 2 minutes.

---

## 4. How everything works

### 4.1 The big picture

```
                 ┌──────────────────── OUR MACHINE (nothing personal leaves) ─────────────────────┐
                 │                                                                                 │
 App / UI ──────►│ 1. Validate ─► 2. Detect ─► 3. Mask ─► 4. Build exact payload ─► 5. GUARD ──┐  │
 (document)      │                    │          │                                    │        │  │
                 │                    │     mapping (RAM only,                     unsafe?    │  │
                 │                    │      one request)                          → 409,     │  │
                 │                    │          │                                 LLM never  │  │
                 │                    │          │                                  called    │  │
                 │                    │          ▼                                            │  │
 App / UI ◄──────│ 8. Reply  ◄─ 7. Reinsert ◄──────────────────────────── reply with tags     │  │
                 │      │                                                         ▲          │  │
                 │      └─► 9. Audit (exact payload, model, timings; NO real values)         │  │
                 │          10. Destroy mapping                                     │          │  │
                 └──────────────────────────────────────────────────────────────────┼──────────┘  │
                                                                                     │  safe:      │
                                                              6. External LLM ◄──────┘  tagged text│
                                                                 (Gemini)                only      │
```

- The order of these steps is **security-critical**. It is written at the top of `backend/app/services/gateway_service.py`. Never reorder it.

### 4.2 Walking one document through

Input (task: extract):
```
Applicant Priya Nair and her husband Arjun Nair visited the branch. Priya Nair PAN ABCDE1234F,
Aadhaar 2345 6789 0123. Address: 14 Shivaji Nagar, Pune 411005. Arjun ka passport number is K1234567.
```

- **Step 1, validate:** the text is not empty, is under 20,000 characters, and the task and provider are allowed.
- **Step 2, detect.** Several detectors run, and their results are merged:
  - **ID recognizers (pattern + checksum):**
    - `ABCDE1234F` is a PAN.
    - `2345 6789 0123` is an Aadhaar.
    - `K1234567` is a passport ("passport" appears just before it, which raises confidence).
  - **Presidio** finds the same IDs again; that's a safety net. Where it disagrees with our exact format checks, ours win (explained in 4.3).
  - **GLiNER** finds `Priya Nair` (twice), `Arjun Nair` and `14 Shivaji Nagar, Pune` as an address.
  - **Rules** also find `Arjun` in "Arjun ka…" (a Hinglish pattern).
  - **Address + PIN:** the address span is extended to swallow the trailing `411005`.
- **Step 3, mask** (`masking_service.py`):
  - Same value means same tag: both "Priya Nair" mentions become `<PERSON_1>`.
  - "Arjun" in "Arjun ka" is a partial name belonging to exactly one detected person, so it reuses Arjun Nair's tag, `<PERSON_2>`. One person, one tag.
  - "Nair" is shared by two people. If it appeared on its own, it would get **its own** tag rather than being left in clear text or guessed.
  - **Second pass:** GLiNER re-reads the masked draft one line at a time and masks anything it still finds.
- **Steps 4–5, build the payload and guard it.** The guard checks the **exact string** that would be sent:
  - Is any original value from this request still in it?
  - Is anything still shaped like an Aadhaar, PAN, GSTIN, Voter ID or passport number?
  - If either check fails, the request returns **HTTP 409**, the LLM is **never called**, and the audit stores `sanitized_payload: null`.
- **Step 6, LLM:** Gemini receives only this:
  ```
  Applicant <PERSON_1> and her husband <PERSON_2> visited the branch. <PERSON_1> PAN <PAN_1>,
  Aadhaar <AADHAAR_1>. Address: <ADDRESS_1>. <PERSON_2> ka passport number is <PASSPORT_1>.
  ```
- **Step 7, reinsert:**
  - Each tag in Gemini's reply is swapped for its real value, in **one pass**; restored text is never re-scanned.
  - Small formatting changes by the LLM are tolerated: `<person_1>`, `< PERSON_1 >`, `[PAN_1]` and a bare `PERSON_1`.
  - A tag the LLM **dropped** is reported in `missing_placeholders`. We never guess where it should go.
  - A tag the LLM **invented** (e.g. `<PERSON_99>`) is left as-is and reported in `unknown_placeholders`.
- **Steps 8–10:**
  - The final answer is returned.
  - The audit row is written: entity types, exact payload, provider and model, timings, leak count.
  - The mapping is deleted from memory, even if something failed.

### 4.3 The detectors in detail

- **India ID recognizers** (`india_recognizers.py`). These are pure Python with no dependencies.

  | ID | Pattern | Extra checks |
  |---|---|---|
  | Aadhaar | 12 digits, optionally `1234 5678 9012` or `1234-5678-9012` | Verhoeff checksum. A bare 12-digit number with no hint is ignored, because it's probably an account number. |
  | PAN | `ABCDE1234F` (5 letters, 4 digits, 1 letter) | 4th letter must be a valid holder type (P, C, H, F…) for top confidence |
  | GSTIN | 15 characters: state code + PAN + entity + `Z` + check character | Mod-36 checksum |
  | Voter ID (EPIC) | 3 letters + 7 digits | The word "voter" or "EPIC" nearby raises confidence |
  | Passport | 1 letter + 7 digits | The word "passport" nearby raises confidence |

  - **A failed checksum lowers confidence but never un-masks a value.** Demo IDs like `1234-5678-9012` fail real checksums but must still be masked. We put zero leakage ahead of precision.
- **Presidio** (`presidio_engine.py`):
  - Runs Microsoft Presidio's `AnalyzerEngine` with spaCy `en_core_web_sm`, Presidio's built-in India recognizers, and ours.
  - Since Presidio 2.2.359, the India recognizers are **off by default**, so we register them explicitly.
  - Two fixes we found during evaluation:
    - Presidio's PAN pattern also matched Voter IDs. When two ID detectors claim the same span, **our exact-format recognizer wins**.
    - Presidio once tagged a date (`23-04-1991`) as a PAN. A Presidio ID match is now kept only if it has the real shape of that ID.
- **GLiNER** (`ner_engine.py`):
  - A small local AI model (about 1.1 GB, runs on CPU in about 100 ms per document) that finds spans of text matching labels we give it.
  - **Labels matter.** We use `person`, `address` and `location`, the labels this model was trained on.
    - The original code asked for `"person name"`, which returns **nothing**. That is why names were missed before.
  - Threshold 0.35 (change it with `GLINER_THRESHOLD`).
    - Bare `location` hits need at least 0.6, because they are noisier.
  - Filters that remove false hits:
    - Spans made only of role words ("customer", "Loan Officer", "applicant") or Hinglish fillers ("mera", "naam", "dhanyavaad").
    - Organisations tagged as places ("Canara Bank branch").
    - Our own `<PERSON_1>` tags (the model thinks they are people).
    - Honorifics are trimmed: "Smt. Lakshmi Devi" becomes "Lakshmi Devi".
  - Long documents are cut into chunks of about 250 words with overlap, because the model reads at most 384 words at a time.
- **Rules (heuristics)** (`ner_engine.py`, function `heuristic_ner`). These are backups, not the main detector. They catch:
  - "My name is X", "Mera naam X hai", "Mr./Smt./Shri X".
  - "Applicant: X", "Nominee: X", "I, X, residing at…".
  - "X ne/ka/ki…", "X and her husband Y", "X visited/applied/lives…".
  - "Address: …", "City: …", "lives in X", "X mein rehta hoon".
- **How results are merged** (`detection_service.py`, `resolve_overlaps`):
  - ID numbers win over names and addresses.
  - Longer spans win over shorter ones.
  - The outcome is deterministic: same input, same output.

### 4.4 Why we chose GLiNER (and not GraphRAG or training our own model)

- **GraphRAG:** no.
  - It is a technique for *answering questions* over documents, not for finding personal data.
  - It needs an LLM to build its graph, which means sending the raw text out. That breaks the core rule.
- **Training our own model (e.g. ModernBERT):** no.
  - It needs thousands of hand-labelled examples and time we don't have.
  - ModernBERT is English-focused, so it would be weak on Hinglish.
  - GLiNER is already a BERT-family model (mDeBERTa) fine-tuned for personal data, and it is multilingual.
- **Pure regex for names:** no.
  - On our held-out set, rules alone find only **30%** of names. GLiNER plus rules finds **95%**.
- **Regex for ID numbers:** yes.
  - IDs have fixed formats and checksums, so patterns are the correct tool. Presidio itself works this way.

### 4.5 Data the system keeps (and does not keep)

- **Kept in the audit log (SQLite, `audit.db`):**
  - Request ID and time, status, provider and model.
  - Entity *types* found, and the exact outbound payload (tags only).
  - Leak and missing counts, timings and any error code.
- **Never stored anywhere:** the original document, the real values, or the tag-to-value mapping.
  - The mapping lives in memory for one request only, with a 15-minute safety purge.
- **Error messages never contain personal data.** Bad requests report only *which field* was wrong.

---

## 5. How we are sure it works

The judges care most about evidence. Here is ours, from strongest to weakest.

- **1. We measure leakage on the exact audited payload, not on our own output.**
  - For each of 74 documents, we take the payload recorded in the audit log (what really would leave).
  - We search it for every labelled real value:
    - Aadhaar compared by digits only, so spaces and dashes can't hide it.
    - IDs compared ignoring case and spaces.
    - Names and addresses compared as whole words.
  - **Result: 0 leaks.**
  - We also run a **stricter** check: any single name word (3+ letters) or 6-digit PIN code from the labels. **Result: 0.**
- **2. A held-out set we never tuned on.**
  - While building, we looked at mistakes on the 50-document main set and fixed them. That makes the main-set scores **optimistic** (they reached 1.000).
  - So we wrote **20 more documents in different styles**: emails, WhatsApp-style chat, SMS, "near"/"opp." addresses, more Hinglish, three-person documents.
  - We ran them **once** and did **not** change the detector afterwards.
  - **These are the numbers we quote:** F1 0.89, recall 0.95, zero leaks.
  - **Rule for the team:** do not tune the detector on the held-out files, or they stop being a fair test.
- **3. Before/after comparison on the same data.**
  - The evaluation runs the same pipeline twice: with GLiNER, and rules-only.
  - The gap shows the model is doing real work (names: 0.95 vs 0.30 recall on held-out).
- **4. The real pipeline is tested, not a copy.**
  - The evaluation calls the actual `process_document` function: detect, mask, guard, LLM, reinsert, audit.
- **5. Reinsertion is tested against misbehaving LLMs.**
  - The mock LLM deliberately keeps, reorders, paraphrases, drops and invents tags.
  - For every tag in the reply, we check it was replaced by **the right person's** value, using the labels.
  - **100% correct, 0 wrong-person restorations, invented tags 130/130 left untouched.**
- **6. Real Gemini.**
  - We sent 10 documents through live `gemini-2.5-flash` (before the 12 Nov evening fixes; not re-run since). 7 succeeded, with **38/38** tags restored correctly and **0** leaks.
  - 3 failed with a provider error on back-to-back calls, probably the free-tier rate limit (not confirmed).
- **7. Automated tests** (78 fast + 8 with real models). They cover:
  - Messy real input (added after the teammate review): the exact screenshot prompt, Aadhaar with dots and
    slashes, `a.id=` / `unique id=` / `ekyc id` labels, spaced PAN and Voter ID, JSON staying valid JSON,
    `key=value`, lowercase names and cities, Hinglish spellings like "reheta" and "rahte".
  - The judge example: exact output.
  - All 7 entity types, and a GSTIN not being split into a PAN.
  - The same name always getting the same tag.
  - A shared surname never leaking; a lone ambiguous first name getting its own tag.
  - Hinglish; negative documents (no false alarms on plain text with numbers).
  - The guard blocking a leak with 409 and **never calling the LLM**, and the blocked request storing no payload.
  - Reinsertion edge cases: markdown, adjacent tags, possessives, 50 repeats, lower-case tags, cross-request isolation, 40 parallel requests.
  - Error codes 502/504, CORS, and request bodies never being echoed back.
- **8. Reproducibility.**
  - The dataset is generated from a fixed seed (42 main, 7 held-out). Running the generator again gives byte-identical files.
  - The positions of labelled values are recorded **while the text is generated** and verified (`text[start:end] == value`). Nobody counted characters by hand.

---

## 6. Precision, recall and every other number

### 6.1 How to read these

- **Precision:** of everything we masked, how much really was personal data. Low precision means **over-masking**: annoying, but safe.
- **Recall:** of all the personal data, how much we caught. Low recall means **leaks**, which is dangerous. **Recall matters more.**
- **F1:** a single score combining both.
- **Relaxed match** (our headline): same type, and our span overlaps the true span by at least 50% (IoU ≥ 0.5).
- **Strict match:** exactly the same characters. This is harsher; for example, "14 Shivaji Nagar, Pune" vs "Flat 14, Shivaji Nagar, Pune" fails strict.
- **TP / FP / FN:** correct finds / wrong finds / misses.

### 6.2 Held-out set: the honest numbers (24 documents: 20 with 76 labelled values, 4 with none)

| Type | Precision | Recall | F1 | Strict F1 | TP | FP | FN |
|---|---|---|---|---|---|---|---|
| PERSON | 0.776 | 0.950 | 0.854 | 0.854 | 38 | 11 | 2 |
| AADHAAR | 1.000 | 1.000 | 1.000 | 1.000 | 4 | 0 | 0 |
| PAN | 1.000 | 1.000 | 1.000 | 1.000 | 6 | 0 | 0 |
| GSTIN | 1.000 | 1.000 | 1.000 | 1.000 | 2 | 0 | 0 |
| VOTER_ID | 1.000 | 1.000 | 1.000 | 1.000 | 2 | 0 | 0 |
| PASSPORT | 1.000 | 1.000 | 1.000 | 1.000 | 4 | 0 | 0 |
| ADDRESS | 0.842 | 0.889 | 0.865 | 0.757 | 16 | 3 | 2 |
| **Overall** | **0.837** | **0.947** | **0.889** | 0.864 | 72 | 14 | 4 |

- The same documents with **rules only (no GLiNER)**:
  - PERSON recall 0.350, ADDRESS recall 0.278.
  - Overall F1 0.627.
- What this tells us:
  - ID numbers are essentially solved: fixed formats plus checksums.
  - Names and addresses are where the AI model matters. Its weak spot is **over-masking names** (precision 0.79): it sometimes masks a word that isn't a name. That is the safe direction.
  - The 4 misses did **not** cause leaks; the leakage checks found 0. They were partly-matched spans or values still masked under a different span.
  - **Caveat:** the held-out set is small (20 documents with personal data; only 2 GSTINs and 2 Voter IDs), so per-type numbers for rare types are not statistically strong.
  - **The 4 negative documents** (added 12 Nov) produced 2 false positives: "Credit" (from "Credit Officer") tagged as a name,
    and "Koramangala branch" tagged as an address. We left them in: tuning them away would make the held-out set unfair.
    The 20 original documents score exactly as before the review fixes (no regression).

### 6.3 Main set (50 documents, 230 labelled values; used for error analysis, so optimistic)

- With GLiNER (full engine): every type 1.000 precision and recall.
  - Strict F1 0.983; addresses 0.913 strict, because boundaries differ slightly.
- Rules only:
  - PERSON recall 0.606, ADDRESS recall 0.609.
  - Overall F1 0.852 (it was 0.830 before the review fixes: the fallback mode got stronger).
- What's in the set:
  - 15 loan, 15 KYC, 10 support and 10 insurance documents.
  - 10 Hinglish documents; 5 with no personal data at all (negatives).
  - Labelled values by type: PERSON 94, ADDRESS 46, PAN 35, AADHAAR 25, VOTER_ID 12, PASSPORT 10, GSTIN 8.
  - Deliberately hard cases:
    - Two people sharing a surname; first-name-only re-mentions.
    - Initials ("K. Ramesh"); honorifics ("Smt.", "Shri").
    - A lowercase chat name; multi-line forms.
    - Raw JSON and `key=value` exports, a dotted Aadhaar with an `a.id=` label, a spaced PAN, and lowercase Hinglish
      with the spelling "reheta" (added after the teammate review).
    - Bank codes and policy numbers that look like IDs but aren't.

### 6.4 Leakage (target: 0)

| Check | Main (50) | Held-out (20) |
|---|---|---|
| Whole real values found in the audited outbound payload | **0** | **0** |
| Stricter: any name word or PIN code left | **0** | **0** |
| Requests blocked by the guard | 0 | 0 |

### 6.5 Reinsertion accuracy (mock LLM misbehaving on purpose)

| What the LLM did | Tags in reply (main) | Restored correctly | Accuracy | Wrong person | Dropped tags (reported, not guessed) | Invented tags left untouched |
|---|---|---|---|---|---|---|
| Keeps every tag | 207 | 207 | 100% | 0 | 0 | — |
| Reorders tags | 207 | 207 | 100% | 0 | 0 | — |
| Paraphrases around them | 207 | 207 | 100% | 0 | 0 | — |
| Drops most tags | 45 | 45 | 100% | 0 | 162 | — |
| Invents unknown tags | 207 | 207 | 100% | 0 | 0 | 90 / 90 |

- The held-out set gives the same result: 100%, 0 wrong-person, 40/40 invented tags untouched.
- Live Gemini: 38/38 restored (100%), 0 wrong-person (measured before the 12 Nov evening fixes).
- **Honest note:** the mock modes reuse our exact tags, so 100% is expected there. The real test of reinsertion is Gemini paraphrasing freely, and that also scored 100% on our 7-request sample.

### 6.6 Latency (extra time the gateway adds)

| | Median | Mean | 95th percentile |
|---|---|---|---|
| Gateway overhead, held-out (n=24) | 222 ms | 246 ms | 418 ms |
| Gateway overhead, main (n=50) | 252 ms | 265 ms | 337 ms |
| Rules-only engine (for comparison) | ~0 ms | ~0.3 ms | 1 ms |
| Gemini call itself (live sample, n=7) | — | 2,572 ms | — |

- So the gateway adds roughly **10%** on top of a real Gemini call.
- Model loading takes about **8 seconds once, at server start**. It is excluded from the per-request numbers.
- Measured on a Windows laptop CPU (no GPU).

---

## 7. The demo: what to show the judges

- **Before the judges arrive:**
  - Start the backend and frontend. Check the two green engine chips.
  - Run one mock request so everything is warm.
- **Demo flow** (pick from the "Sample document" dropdown in the UI):
  1. **D1, judge example.** Show column B: exactly `My name is <PERSON_1>. My Aadhaar number is <AADHAAR_1> and my PAN is <PAN_1>.` Then column C: values restored.
  2. **D2, Hinglish** ("Mera naam Rahul Sharma hai. Main Pune mein rehta hoon…"). Name and city are both masked.
  3. **D4, couple sharing a surname.** Point out:
     - One tag per person, even for "Arjun ka…".
     - No "Nair" anywhere in column B.
     - This exact document leaked a surname to Gemini in an early version; now it doesn't.
  3b. **D7, messy chat** (lowercase Hinglish, "reheta", dotted and slashed Aadhaar, spaced PAN) and
      **D8, raw JSON payload**: everything masked, and the JSON in column B is still valid JSON.
      Judges type input like this; showing it pre-empts the question.
  4. **Switch the provider to Gemini** and run D5 (insurance claim, all 7 types). Show the real model, LLM time vs gateway overhead, and the restored answer.
  5. **Misbehaving LLM:**
     - Stop the backend, set `MOCK_MODE=drop` in `.env`, restart, and run D1 with provider Mock.
     - Column C shows "The LLM dropped … Reported, not guessed."
     - (Also try `reorder`, `paraphrase` and `unknown`.)
  6. **Blocked leak (409).**
     - The UI can't easily force a leak, because detection catches everything first.
     - So show the automated test instead: `pytest tests/backend/test_gateway.py -k leak -v`. It proves the guard blocks with 409 and the LLM is **never called**.
  7. **Audit trail tab:** each request with model, entity types and leak count, and never the real values.
  8. **Evaluation tab:** zero leakage, held-out F1 0.89, 100% reinsertion, about 0.25 s overhead.
     - Toggle "Main set" to show the rules-only vs GLiNER recall gap.
- **One honest sentence to say:** "Our numbers are on synthetic data we generated, including a held-out set we never tuned on. ID detection is near perfect; names are where we lean towards over-masking, which is the safe side."

---

## 8. Questions judges will ask, and our answers

- **"How do you know nothing leaks?"**
  - We check the exact audited payload against every labelled value in 74 documents: 0 leaks.
  - At run time, a guard re-checks every outgoing payload and blocks with 409 if anything remains. The LLM is never called in that case.
- **"What if your detector misses a name completely?"**
  - Then the guard can't know it's a name. That is our main residual risk, and we say so.
  - We reduce it in three ways:
    - Two detection passes (whole document, then line by line).
    - Masking every part of a detected name everywhere it appears.
    - A low confidence threshold, which prefers over-masking.
  - We measure it: 95% name recall on held-out data.
- **"Why not just use regex?"**
  - For IDs we do, because they have fixed formats and checksums.
  - For names, regex finds 30% on new phrasings; the model finds 95%.
- **"Why not GraphRAG / fine-tune your own model?"** See [4.4](#44-why-we-chose-gliner-and-not-graphrag-or-training-our-own-model).
- **"What if the LLM paraphrases or reorders?"**
  - Tags are matched by name, not position, so order doesn't matter.
  - Formatting variants are tolerated. Dropped tags are reported, never guessed.
- **"Could one person's data end up in another's place?"**
  - Each tag maps to exactly one value, for one request only.
  - A name word shared by two people gets its own separate tag.
  - Measured wrong-person restorations: 0.
- **"How does this relate to DPDP?"**
  - The DPDP Rules 2025 list masking and "virtual tokens mapped to the personal data" as security safeguards (Rule 6, as summarised by law-firm notes; we have not verified it against the gazette text), and the audit log supports accountability.
  - We do **not** claim the gateway makes anyone DPDP-compliant. It is one technical safeguard.
- **"Where is the mapping stored?"**
  - In server memory, for one request, deleted in a `finally` block, with a 15-minute safety purge. Never on disk, never in the audit.
- **"How much slower is it?"** About 0.25 s per request, roughly 10% of a Gemini call.

---

## 9. Known limitations (say these before the judges do)

- **Synthetic data only.** Our documents are generated from templates we wrote. Real documents are messier, so real-world accuracy will be lower than our numbers.
- **The held-out set is small** (20 documents with personal data, plus 4 without), so rare types (GSTIN, Voter ID) have only 2 examples each there.
- **Name precision is 0.79 on held-out data.** We over-mask some ordinary words. That is safe for privacy, but it can make the LLM's answer slightly less useful.
- **Names and addresses the model misses entirely cannot be caught by the guard.** The guard only knows values we detected, plus ID-shaped patterns.
- **Some filter word lists** (role words, Hinglish fillers, organisation words) were extended after looking at the main set's errors. That is why we quote held-out numbers.
- **Email and phone numbers are not masked.** They are not among the 7 required types, and adding them needs team agreement.
- **The mapping is in memory, single process.** Running several server processes behind a load balancer would need a shared store.
- **Live Gemini sample:** 3 of 10 calls failed (likely rate limiting, not confirmed). Leave a few seconds between demo calls.
- **Ollama (local model fallback) is untested.** Optional extras (purpose policies, format-preserving tokens) are not built.
- **The "Live gateway totals" in the Evaluation tab** include old requests from the audit DB. Delete `audit.db` (with the server stopped) for a clean demo.

---

## 10. Rules for changing the code

- **Frozen. Don't rename or change these without the whole team agreeing:**
  - The 7 entity names `PERSON, AADHAAR, PAN, GSTIN, VOTER_ID, PASSPORT, ADDRESS` and the `<TYPE_N>` tag format.
  - The four privacy functions (`sanitize_document`, `validate_outbound_payload`, `reinsert_placeholders`, `destroy_mapping`) and their return fields.
  - API paths, the request shape, the response fields and the error format and codes.
  - The step order in `gateway_service.py`.
- **Before you push:**
  - Run `pytest tests -q`: all must pass.
  - If you touched detection, also run the real-model tests and the evaluation. Compare `evaluation/results_heldout.md` with this handbook.
- **Never commit:**
  - `.env` or any key.
  - `audit.db`.
  - Real people's data.
- **Never tune on the held-out set.**
  - If you change the detector, report the held-out numbers as they come out.
  - If you need more test data, add new templates to `generate_dataset.py`, not to `generate_heldout.py`.
- **Ownership** (from the team plan):
  - Member 1 (Abhay): `backend/app/core|services|api|database`.
  - Member 2: `backend/app/privacy/`, `tests/privacy/`.
  - Member 3: `frontend/`, `dataset/`, `evaluation/`.
  - This branch touched all three areas. Pull it before you start new work, to avoid conflicts.

---

## 11. Troubleshooting

- **`/engines` shows GLiNER `failed`:**
  - Read the `error` text there.
  - Usually: `pip install -r requirements.txt` (it needs `sentencepiece` and `protobuf`), or the model isn't downloaded (run Step 3).
  - Restart the backend afterwards.
- **`/engines` shows GLiNER `disabled`:** `PRIVACY_NER` in `.env` isn't `both`.
- **Presidio `failed`:** run `python -m spacy download en_core_web_sm`.
- **The first request is very slow (40+ seconds):** `PRIVACY_PRELOAD` is `0`, or the model is downloading. Download it in advance (Step 3).
- **The UI says "Cannot reach MineArena API":**
  - The backend isn't running on port 8000.
  - Or you changed the UI port, in which case add it to `CORS_ORIGINS` in `.env`.
- **Gemini errors (502 "LLM provider error"):**
  - Check `GEMINI_API_KEY`. Wait a few seconds between calls (rate limits).
  - Try `GEMINI_MODEL=gemini-2.5-flash`.
  - For the demo you can set `LLM_FALLBACK=mock`. The response then says `fallback_used: true`, so it stays honest.
- **`npm ci` fails ("lock file out of sync"):** use `npm install` instead.
- **Port already in use:**
  - Close the other server.
  - Or use `--port 8001`, then start the UI with `VITE_API_BASE_URL=http://localhost:8001/api/v1 npm run dev`.
- **Tests fail only on your machine:** make sure the venv is activated and you are in the repo root.
- **Warnings in the server log about `torch.jit`, `resume_download` or "symlinks":** harmless.

---

## 12. File map

```
repo/
├── README.md                     quick start + headline numbers
├── requirements.txt              Python packages
├── .env.example                  copy to .env (never commit .env)
├── backend/app/
│   ├── main.py                   FastAPI app; loads models at start-up
│   ├── api/routes/
│   │   ├── gateway.py            POST /gateway/process
│   │   ├── audit.py, metrics.py, health.py
│   │   └── engines.py            GET /engines and /evaluation (new)
│   ├── core/                     config.py (reads .env), errors.py (error codes)
│   ├── database/db.py            SQLite audit log
│   ├── services/
│   │   ├── gateway_service.py    THE pipeline (security-critical order)
│   │   └── llm/                  gemini_provider.py, local_providers.py (ollama + mock), base.py (prompt)
│   └── privacy/                  the privacy engine
│       ├── __init__.py           the 4 public functions
│       ├── schemas.py            entity names, Span type
│       ├── detection/
│       │   ├── india_recognizers.py   ID patterns + checksums
│       │   ├── presidio_engine.py     Presidio setup
│       │   ├── ner_engine.py          GLiNER + rules for names/addresses
│       │   └── detection_service.py   merges detectors, PIN extension, engine status
│       ├── masking/masking_service.py  tags, consistency, shared names, second pass
│       ├── mapping/mapping_store.py    in-memory, per-request mapping
│       ├── security/leakage_guard.py   checks the exact outbound text
│       └── reinsertion/reinsertion_service.py
├── frontend/src/
│   ├── App.jsx                   3-column workspace, tabs
│   ├── components/GatewayViews.jsx    highlighting + entity table
│   ├── pages/EvaluationReport.jsx     Evaluation tab
│   ├── samples.js                demo documents D1–D8
│   └── services/api.js           calls to the backend
├── dataset/
│   ├── generate_dataset.py       50 docs, seed 42  → loan/ kyc/ support/ insurance/ + ground_truth.json
│   └── generate_heldout.py       20 docs, seed 7   → heldout/ + heldout_ground_truth.json
├── evaluation/
│   ├── run_eval.py               runs the real pipeline, computes all metrics
│   └── results.md / .json, results_heldout.md / .json
├── tests/                        78 fast tests + optional real-model tests
├── scripts/solo_demo.py          command-line demo (server must be running)
└── docs/
    ├── TEAM_HANDBOOK.md          this file
    └── GUIDE.md                  original team guide and runbook
```

---

## 13. Glossary

- **PII:** personally identifiable information, i.e. data that identifies a person.
- **Placeholder / tag:** `<PERSON_1>` etc., what replaces a real value.
- **Mapping:** the private table "`<PERSON_1>` = Priya Nair". It lives in memory, for one request only.
- **Outbound payload:** the exact text sent to the external LLM.
- **Guard:** the final check on the outbound payload. It blocks with HTTP 409 if anything real remains.
- **Reinsertion:** putting the real values back into the LLM's answer, locally.
- **NER:** named entity recognition, i.e. finding names, places and so on in text.
- **GLiNER:** the local NER model we use. Runs on CPU; no data leaves the machine.
- **Presidio:** Microsoft's open-source PII detection framework.
- **Heuristics / rules:** hand-written patterns such as "Mera naam X hai".
- **Checksum:** a check digit that makes a typo or fake ID detectable (Verhoeff for Aadhaar, mod-36 for GSTIN).
- **Held-out set:** test documents never used to adjust the system, giving an honest score.
- **Precision / recall / F1:** see [6.1](#61-how-to-read-these).
- **IoU:** intersection over union, how much two text spans overlap (0 = none, 1 = identical).
- **Mock provider:** a fake LLM for testing without an API key. It can misbehave on purpose.
- **DPDP:** India's Digital Personal Data Protection Act 2023 and Rules 2025.

---

## 14. Changes after the teammate review (12 Nov evening)

A teammate tested the app with realistic messy input and sent a list of problems (`suggestions.txt`).
We **re-tested every claim on our own code** before changing anything. The headline was real: on the prompt
below, two values went to the LLM unmasked **while the UI showed "Guard passed · 0 leaks"**.

```
hi mera naam aditya hai aur me pune me reheta hu also mera adhaar no 5555-6666-7894 hai and
mere dost ka name rahul hai aur uska adhar no 1111.2222.8888 hai
```

### 14.1 What was wrong, and what we changed

| Problem (reproduced on our code) | Why it happened | Fix | File |
|---|---|---|---|
| Dotted / slashed Aadhaar (`1111.2222.8888`, `1234/5678/9012`) leaked, and the guard said 0 leaks | The Aadhaar pattern only allowed spaces and dashes. The guard re-uses the same pattern, so it was blind too. | Pattern accepts space, dash, dot and slash, and refuses to match inside longer dotted numbers (invoice and version numbers). | `india_recognizers.py` |
| Lowercase city "pune" leaked ("aur me pune me reheta hu") | The Hinglish rule needed a capital letter and didn't know the spelling "reheta"; GLiNER scored the lowercase city too low | New residence rule: any case, verb spellings reh/rah(e)ta/ti/te/na/ne, keeps only the place word right before "me/mein" (never the pronoun or a person before it) | `ner_engine.py` |
| `unique id=`, `ekyc id`, `a.id=`, `u.id=` Aadhaar labels missed | Not in the keyword list | Added; keyword window 40 → 60 characters | `india_recognizers.py` |
| Spaced PAN / Voter ID / passport (`ABCDE 1234 F`, `XYZ 1234567`) leaked, guard passed | Only compact forms were recognised | Spaced forms accepted **only when the keyword (pan / voter / passport) is just before them**, so ordinary text like "Room ABC 1234567" stays untouched | `india_recognizers.py` |
| Raw JSON was mangled: `"address<ADDRESS_1><PAN_1>…` | The address rule ran past the closing quote and swallowed the rest of the object | Label rules stop at quotes, `;`, `\|` and the next `key=` / `"key":`. Masked JSON now parses as valid JSON. | `ner_engine.py` |
| Lowercase names in chat ("my name is aditya kulkarni and…", JSON `"name": "rahul sharma"`) depended on GLiNER alone | The name rules needed capital letters | Lowercase trigger and label rules; the value runs until a stop word (hai, and, aur…). Capitalised names still end at the first lowercase word. | `ner_engine.py` |
| "i live in nashik" leaked in rules-only mode | The English residence rule needed a capital letter | Lowercase version, which skips "i live in a flat…" | `ner_engine.py` |
| GLiNER tagged the Hinglish word "me" as a person, and propagation then masked every "me" | No filter for function words | Spans made only of function words, or a single token under 3 letters, are never names or places | `ner_engine.py` |
| `ABCDE-1234-F` and `ABCDE1234F` got different tags; the guard compared IDs ignoring spaces only | `normalize()` stripped only spaces | IDs compared ignoring space, dash, dot and slash, in both masking and the guard | `mapping_store.py`, `leakage_guard.py` |
| Presidio would have thrown away dotted / spaced IDs | Its shape check didn't allow those separators | Shape check uses the same separators | `presidio_engine.py` |
| Two simultaneous first requests could load the 1.1 GB model twice | No lock on the lazy loaders | `threading.Lock` around GLiNER and Presidio loading | `ner_engine.py`, `presidio_engine.py` |
| Model load could stall on bad Wi-Fi | It always checked HuggingFace first | Loads from the local cache first (`local_files_only=True`), downloads only if missing | `ner_engine.py` |
| Opening `http://localhost:8000/` returned a 404 | No root route | `GET /` returns the service name and links to `/docs`, `/api/v1/health` and `/api/v1/engines` | `main.py` |
| 9 empty `.jsx` files in `frontend/src` | Leftover stubs | Deleted (nothing imported them) | `frontend/src/` |

**Also added:**
- Demo samples **D7** (the messy chat above, plus a spaced PAN and a slashed `a.id=`) and **D8** (raw JSON support payload).
- **19 regression tests**: the screenshot prompt, every Aadhaar separator, abbreviated labels, spaced IDs with and without keywords, JSON validity, `key=value`, lowercase English and Hinglish, ID normalisation, and the root route.
  - They run in **rules-only mode**, so they also prove the fallback works if GLiNER fails to load.
- Main dataset: 3 new templates (lowercase Hinglish + spaced PAN, `key=value` export + dotted Aadhaar, raw JSON payload).
- Held-out set: **4 negative documents** with no personal data, to measure false alarms.
  - The 20 original held-out documents are **byte-identical** (checked by fingerprint), and we did not tune on any held-out result.

### 14.2 Effect on the numbers

| | Before review | After review fixes |
|---|---|---|
| Leaks (whole value / stricter residue) | 0 / 0 | **0 / 0** |
| Held-out recall (full engine) | 0.947 | **0.947** (unchanged) |
| Held-out precision (full engine) | 0.857 (20 docs) | **0.837** (24 docs; the 2 new false positives are both in the new negative docs) |
| Held-out F1, rules-only fallback | 0.603 | **0.627** |
| Main-set F1, rules-only fallback | 0.830 | **0.852** |
| Fast tests | 59 | **78** |
| Gateway overhead (median, main set) | ~232 ms | ~252 ms |

### 14.3 Suggestions we checked and deliberately did NOT follow

- **"Make `tests/conftest.py` use `setdefault`."**
  - The fast tests assert exact outputs from rules-only mode.
  - With `setdefault`, a `PRIVACY_NER=both` left in someone's shell would quietly switch them to GLiNER, making them slow and flaky.
  - Forcing the mode is intentional. The real-model tests live in the `*_optional.py` files.
- **"Lower the GLiNER location threshold to 0.45 / raise the PERSON threshold to 0.40."**
  - Choosing thresholds by looking at held-out results is tuning on the test set, which would make our honest numbers dishonest.
  - The leaks were fixed with context rules instead, which work even without the model.
  - Re-tune thresholds only with a *new* test set.
- **"Add a city gazetteer."** Not needed for the reported leaks. The residence rules cover them without a hand-maintained list of cities.
- **Round 2 / sponsor features** (email, phone, UPI, card masking with a policy selector; purpose policies; Redis mapping store; API keys; audit export; tested Ollama fallback).
  - These are new features, not fixes. They are listed in the review as "pick 2–3 if time permits".
  - The team should choose which, if any, to build. Email and phone are still **not** masked (see section 9).

### 14.4 How to check these fixes yourself

```bash
pytest tests/privacy/test_privacy.py -q -k "screenshot or aadhaar or spaced or json or key_value or lowercase or hinglish or normalize"
```
In the UI, pick **D7** and **D8** from the sample dropdown. Column B must show no raw value, and D8's payload must still be valid JSON.
