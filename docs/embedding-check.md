# Embedding compatibility check

This is an early provider smoke check, not the ingestion service or Checkpoint 4.

Google's official docs were checked on 19 October 2026:

- `gemini-embedding-2` supports 768-dimensional output using `output_dimensionality`.
- Its default is 3072; 768, 1536 and 3072 are recommended sizes.
- Standard text embeddings are advertised as free on the Free tier. This does not
  establish the user's actual project quota; inspect AI Studio and test the request.
- Free-tier inputs are marked as used for product improvement. Send only the
  synthetic sentence in this probe; no private PDFs or credentials are uploaded.
- For Embedding 2 text retrieval, Google recommends document/query prefixes rather
  than the older model's `task_type` field. The probe uses a document prefix.
- Multiple inputs may be aggregated into one vector by Embedding 2. Future ingestion
  must deliberately generate one vector per chunk rather than assume one per string.

## Setup

1. Open [Google AI Studio keys](https://aistudio.google.com/api-keys).
2. Create/select a Free-tier project with billing disabled. Don't enable paid billing.
3. Check its active model quota in AI Studio.
4. Save its key in ignored `backend/.env` as `DRDOC_GEMINI_API_KEY`. Never share it in chat.
5. From `backend/`, after confirming Free status:

```powershell
uv run --locked python -m scripts.check_embedding --free-tier-confirmed
```

This sends one small synthetic sentence through Google's official SDK, with a
15-second request timeout and one attempt (no retries). It checks one returned
vector has exactly 768 finite values and nonzero norm. It prints only summary
metadata, never the API key, raw response or vector. No database writes occur.
The confirmation flag is an operator assertion, not programmatic billing verification.

429 produces temporary unavailability; other failures produce safe messages.
There is no paid fallback. A successful request establishes access at that moment,
not future capacity, semantic retrieval quality or document/query compatibility.

Files: `scripts/check_embedding.py`, `scripts/__init__.py`, and
`tests/test_embedding_probe.py`; settings and dependency files are updated too.
Routine tests mock the SDK and use no real quota.

## Actual result — 19 October 2026

The user confirmed the key's project is Free tier. The live command succeeded:

```text
PASS: model=gemini-embedding-2, dimensions=768, finite=True, norm=1.000000
```

One synthetic-text request was made; no database writes or retries occurred.
This verifies current API access and output shape, not remaining quota or retrieval
quality. The mocked probe tests were subsequently run with the Checkpoint 3 offline
suite: 51 passed, 13 database tests skipped. They verify missing-key handling,
dimension checks, timeout/attempt configuration and safe quota-error handling,
without making additional Google API calls.

References:

- [Embedding dimensions and task formatting](https://ai.google.dev/gemini-api/docs/embeddings)
- [Pricing and data-use table](https://ai.google.dev/gemini-api/docs/pricing#gemini-embedding-2)
- [Account rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)
