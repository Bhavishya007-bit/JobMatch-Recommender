"""Update the committed real ATS jobs snapshot (for GitHub Actions)."""
import json
import urllib.request
from datetime import datetime, timezone
from data import ROOT, SOURCE_URL, normalize_record


def main():
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "JobMatch-Recommender/1.0"})
    with urllib.request.urlopen(req, timeout=45) as response:
        raw = json.load(response)
    if not isinstance(raw, list) or not raw:
        raise ValueError("Empty or invalid upstream data; keeping existing snapshot")
    records = [r for item in raw if isinstance(item, dict)
               if (r := normalize_record(item)) is not None]
    if not records or len(records) != len(raw):
        raise ValueError("Upstream data contained invalid listings; keeping existing snapshot")
    path = ROOT / "data" / "recent_jobs.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    metadata = {
        "source": "ConorsCode/open-jobs-data",
        "sourceRepository": "https://github.com/ConorsCode/open-jobs-data",
        "sourceFile": "data/new-jobs.json",
        "refreshedAt": datetime.now(timezone.utc).isoformat(),
        "validJobs": len(records),
        "distinctCompanies": len({r["company"] for r in records}),
        "note": "Real incremental employer ATS postings, not all active jobs. Apply links can expire.",
    }
    (ROOT / "data" / "provenance.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Refreshed real snapshot: {len(records)} jobs")


if __name__ == "__main__":
    main()
