# JobMatch — Real Job Listings Recommender

A Python/FastAPI search and ranking prototype built on **genuine job listings from employer applicant-tracking systems**. Unlike the initial synthetic proof-of-concept, the current version stores and ranks real company names, actual job titles, locations and application URLs. This is a portfolio prototype, not a production job board.

## Source and provenance

- Public upstream: [ConorsCode/open-jobs-data](https://github.com/ConorsCode/open-jobs-data)
- Direct jobs snapshot: [data/recent_jobs.json](data/recent_jobs.json)
- Provenance: [data/provenance.json](data/provenance.json)
- The committed snapshot contains **1,326 genuine job listings from 147 companies**, scraped on November 21, 2026, with **1,326 application URLs**.
- Daily incremental source: `data/new-jobs.json`, not the upstream complete active job index. Listings can expire, and source URLs do not guarantee an opening remains available.
- Original source offers a separate larger `data/jobs.json` index. Refresh currently ingests the *new jobs* incremental feed and accumulates records by `platform:jobId` over time.
- Most source records **do not contain detailed job descriptions, skill requirements, salary, or independently annotated relevance judgments**. The app does not fabricate them.

## How it works

1. `data.py` reads actual raw employer-ATS records from the included dated snapshot, validates them, and **upserts** them into SQLite with stable `platform:jobId` keys.
2. `recommender.py` indexes the *provided* title/department/company text using TF-IDF, adds low-rank LSA retrieval (TruncatedSVD), and supports confirmed-remote and internship filters. An optional location preference influences ranking.
3. `app.py` exposes `/health`, `/jobs`, `/recommend`, and an opt-in `/refresh` endpoint that fetches current incremental data (network required).
4. `evaluate.py` records descriptive dataset coverage and an **exact-title retrieval sanity check**. This is not a real recommendation accuracy measurement.

## Quick start

Requires Python 3.10+.

```bash
python -m pip install -r requirements.txt
python evaluate.py
pytest -q
uvicorn app:app --reload
```

Interactive docs: http://127.0.0.1:8000/docs

Example query:

```bash
curl -X POST 'http://127.0.0.1:8000/recommend?k=5' \
-H 'Content-Type: application/json' \
-d '{"query":"Python software engineer internship","location":"Bengaluru","remote_ok":true,"internship_only":true}'
```

Refresh from upstream:

```bash
python data.py --refresh
```

The refresh command **requires internet access** and fails clearly if upstream is unavailable. The included real snapshot lets the project run offline. To avoid abusive upstream requests, refresh no more than necessary (e.g., once daily). Old jobs remain stored; current code does not yet expire removed positions.

## Evaluation ethics

The prior synthetic NDCG@10 result is **retired**: it did not measure real-world recommendation quality. We do not report NDCG, MRR or Recall on the real dataset because it lacks independent user-to-job relevance labels. Known-title retrieval is merely a diagnostic for indexing, and should **not** be described as model accuracy.

## Limitations and production TODOs

- Add actual descriptions from legally accessible sources to support skills and deeper semantics.
- Create a human-reviewed relevance dataset and run NDCG@10, Recall@10 and MRR@10 against graded labels.
- Add expiration/removal detection; a daily GitHub Actions snapshot refresh is configured.
- Add rate limits, refresh concurrency control, retries and monitoring before any public deployment.
- LSA is *not* a transformer-embedding model, and this prototype does not contain an autonomous LLM agent, durable personalization, or production traffic.

## License and third-party data

Consult upstream source policies before redistributing a commercial derivative. No rights are claimed to the job listings or company names.

## API reliability

Search queries are trimmed and must contain 2–2,000 characters; location text is limited to 200 characters. Invalid input returns HTTP 422.

HTTP refresh is disabled (503) unless `JOBMATCH_REFRESH_TOKEN` is configured. Callers must provide the same secret in `X-Refresh-Token`; missing or incorrect credentials return 401 before any upstream request. Use HTTPS and keep this server-side token private. The CLI and scheduled snapshot refresh remain independent. A failed refresh returns 502 and preserves the in-memory search index. This is a prototype safeguard, not a complete public-deployment security model.
