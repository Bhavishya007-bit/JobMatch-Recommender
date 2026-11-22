"""Real employer-ATS job metadata loader and incremental refresh.

Source: https://github.com/ConorsCode/open-jobs-data
The shipped data/recent_jobs.json is an actual dated snapshot of new postings.
No fabricated listings, skills, descriptions, or user preferences.
"""
from __future__ import annotations
import json
import sqlite3
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "jobs.sqlite"
SNAPSHOT_PATH = ROOT / "data" / "recent_jobs.json"
SOURCE_URL = "https://raw.githubusercontent.com/ConorsCode/open-jobs-data/main/data/new-jobs.json"

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    job_key TEXT PRIMARY KEY,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    department TEXT,
    locations_json TEXT NOT NULL,
    is_remote INTEGER,
    employment_type TEXT,
    apply_url TEXT NOT NULL,
    platform TEXT NOT NULL,
    job_id TEXT NOT NULL,
    posted_at TEXT,
    scraped_at TEXT,
    first_seen_at TEXT,
    last_refreshed_at TEXT NOT NULL
)
"""


def normalize_record(raw: dict) -> dict | None:
    platform, job_id = str(raw.get("platform") or "").strip(), str(raw.get("jobId") or "").strip()
    title, company = str(raw.get("title") or "").strip(), str(raw.get("company") or "").strip()
    url = str(raw.get("applyUrl") or "").strip()
    if not (platform and job_id and title and company and url.startswith(("https://", "http://"))):
        return None
    locations = raw.get("locations") or []
    if not isinstance(locations, list):
        locations = [str(locations)]
    remote = raw.get("isRemote")
    return {
        "job_key": f"{platform}:{job_id}",
        "company": company,
        "title": title,
        "department": raw.get("department"),
        "locations": [str(v).strip() for v in locations if v],
        "is_remote": remote if isinstance(remote, bool) else None,
        "employment_type": raw.get("employmentType"),
        "apply_url": url,
        "platform": platform,
        "job_id": job_id,
        "posted_at": raw.get("postedAt"),
        "scraped_at": raw.get("scrapedAt"),
        "first_seen_at": raw.get("firstSeenAt"),
    }


def read_snapshot(path: Path = SNAPSHOT_PATH) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Jobs snapshot must be a list")
    return [r for item in raw if isinstance(item, dict) if (r := normalize_record(item)) is not None]


def refresh_from_web(url: str = SOURCE_URL, timeout: int = 25) -> list[dict]:
    """Fetch today's upstream incremental snapshot. Never invent fallback listings."""
    req = urllib.request.Request(url, headers={"User-Agent": "JobMatch-Recommender/1.0 (portfolio; GitHub)"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = json.load(response)
    if not isinstance(raw, list):
        raise ValueError("Unexpected upstream jobs payload")
    records = [r for item in raw if isinstance(item, dict) if (r := normalize_record(item)) is not None]
    if not records:
        raise ValueError("Upstream data contains no valid jobs; leaving database unchanged")
    return records


def upsert_jobs(records: list[dict], db_path: Path = DB_PATH) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(CREATE_SQL)
        conn.executemany("""
            INSERT INTO jobs (job_key, company, title, department, locations_json, is_remote,
              employment_type, apply_url, platform, job_id, posted_at, scraped_at,
              first_seen_at, last_refreshed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_key) DO UPDATE SET
              company=excluded.company, title=excluded.title,
              department=excluded.department, locations_json=excluded.locations_json,
              is_remote=excluded.is_remote, employment_type=excluded.employment_type,
              apply_url=excluded.apply_url, posted_at=excluded.posted_at,
              scraped_at=excluded.scraped_at, last_refreshed_at=excluded.last_refreshed_at
        """, [
            (r["job_key"], r["company"], r["title"], r["department"], json.dumps(r["locations"]),
             None if r["is_remote"] is None else int(r["is_remote"]),
             r["employment_type"], r["apply_url"], r["platform"], r["job_id"],
             r["posted_at"], r["scraped_at"], r["first_seen_at"], now)
            for r in records
        ])
        conn.commit()
    return len(records)


def load_jobs(db_path: Path = DB_PATH, seed_path: Path = SNAPSHOT_PATH) -> list[dict]:
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(CREATE_SQL)
        count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    if count == 0:
        upsert_jobs(read_snapshot(seed_path), db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM jobs ORDER BY job_key").fetchall()
    results = []
    for row in rows:
        j = dict(row)
        j["locations"] = json.loads(j.pop("locations_json"))
        j["is_remote"] = None if j["is_remote"] is None else bool(j["is_remote"])
        results.append(j)
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ingest real employer ATS job listings")
    parser.add_argument("--refresh", action="store_true", help="Fetch fresh incremental listings from upstream")
    args = parser.parse_args()
    rows = refresh_from_web() if args.refresh else read_snapshot()
    inserted = upsert_jobs(rows)
    print(f"Upserted {inserted} genuine listings; SQLite now has {len(load_jobs())} records")
