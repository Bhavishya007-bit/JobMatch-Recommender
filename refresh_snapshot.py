"""Refresh the committed jobs snapshot from the actual public ATS feed.

Intended for daily GitHub Actions updates. No fake listings are generated.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from data import ROOT, refresh_from_web

def main():
    records = refresh_from_web()
    # Keep original source fields, not transformed/indexed records.
    # The upstream URL is public and does not require an API key.
    import urllib.request
    url = "https://raw.githubusercontent.com/ConorsCode/open-jobs-data/main/data/new-jobs.json"
    request = urllib.request.Request(url, headers={"User-Agent": "JobMatch-Recommender/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = json.load(response)
    if not isinstance(raw, list) or not raw:
        raise ValueError("Refusing to overwrite with empty upstream dataset")
    path = ROOT / "data" / "recent_jobs.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    companies = len({r["company"] for r in records})
    metadata = {
        "source": "ConorsCode/open-jobs-data",
        "sourceRepository": "https://github.com/ConorsCode/open-jobs-data",
        "sourceFile": "data/new-jobs.json",
        "refreshedAt": datetime.now(timezone.utc).isoformat(),
        "validJobs": len(records), "distinctCompanies": companies,
        "note": "Actual incremental postings from employer ATS feeds; not all active jobs. Vacancies can expire."
    }
    (ROOT / "data" / "provenance.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(records)} genuine listings from {companies} companies to {path}")

if __name__ == "__main__":
    main()
