"""Reproducible descriptive checks on real job postings.

No NDCG, MRR or Recall without independently annotated job relevance labels.
This evaluation reports dataset coverage and a known-title retrieval sanity check
(which is NOT a user-relevance or recommendation-quality benchmark).
"""
import json
from collections import Counter
from pathlib import Path
import numpy as np
from data import load_jobs
from recommender import JobRecommender


def evaluate():
    jobs = load_jobs()
    engine = JobRecommender(jobs)
    # Fixed subset of real titles: query is an exact observed title and hit is same job_key.
    # This leaks the target title by design and measures indexing integrity, not real relevance.
    sample_indices = np.linspace(0, len(jobs) - 1, num=min(30, len(jobs)), dtype=int)
    results = {}
    for mode in ("baseline", "hybrid"):
        hits = 0
        for idx in sample_indices:
            target = jobs[int(idx)]
            ranked = engine.recommend({"query": target["title"], "location": "",
                                       "remote_ok": False}, k=10, mode=mode)
            hits += int(any(result["job_key"] == target["job_key"] for result in ranked))
        results[mode] = {"known_title_hit_at_10": round(hits / len(sample_indices), 4),
                         "queries": len(sample_indices)}
    summary = {
        "dataset": "real employer ATS new-jobs incremental snapshot",
        "jobs_in_database": len(jobs),
        "distinct_employers": len(set(job["company"] for job in jobs)),
        "confirmed_remote_jobs": sum(job["is_remote"] is True for job in jobs),
        "remote_status_unknown": sum(job["is_remote"] is None for job in jobs),
        "jobs_with_apply_urls": sum(job["apply_url"].startswith(("https://", "http://")) for job in jobs),
        "source": "https://github.com/ConorsCode/open-jobs-data",
        "note": "This is not a relevance benchmark. Actual NDCG@10 requires independent, graded relevance labels.",
    }
    report = {"summary": summary, "sanity_checks": results}
    Path(__file__).with_name("benchmark.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
