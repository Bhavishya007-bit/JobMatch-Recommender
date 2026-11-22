from pathlib import Path
import sqlite3
import tempfile
from fastapi.testclient import TestClient

from app import app
from data import load_jobs, read_snapshot, upsert_jobs
from recommender import JobRecommender


def test_real_snapshot_has_employer_urls_and_no_fake_descriptions():
    jobs = read_snapshot()
    assert len(jobs) > 100
    assert all(job["apply_url"].startswith(("http://", "https://")) for job in jobs)
    assert all("Sample Employer" not in job["company"] for job in jobs)
    assert all("description" not in job and "skills" not in job for job in jobs)


def test_sqlite_ingestion_is_idempotent(tmp_path):
    p = tmp_path / "jobs.sqlite"
    jobs = read_snapshot()
    upsert_jobs(jobs, p)
    upsert_jobs(jobs, p)
    with sqlite3.connect(p) as conn:
        assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == len(jobs)
    assert len(load_jobs(p)) == len(jobs)


def test_recommendations_have_real_source_urls():
    engine = JobRecommender(read_snapshot())
    ranked = engine.recommend({"query": "software engineer", "location": "Bengaluru"}, k=5)
    assert len(ranked) == 5
    assert all(r["apply_url"].startswith("https://") for r in ranked)


def test_remote_filter_uses_confirmed_remote_only():
    engine = JobRecommender(read_snapshot())
    ranked = engine.recommend({"query": "engineer", "remote_only": True}, k=10)
    assert all(r["is_remote"] is True for r in ranked)


def test_api():
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["job_count"] > 100
        res = client.post("/recommend?k=3", json={"query": "software engineering internship"})
        assert res.status_code == 200
        assert res.json()["count"] == 3
