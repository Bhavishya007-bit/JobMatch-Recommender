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


import pytest


@pytest.mark.parametrize("query", ["  ", " x ", "x" * 2001])
def test_invalid_query_is_client_error(query):
    with TestClient(app) as client:
        assert client.post("/recommend", json={"query": query}).status_code == 422


def test_query_is_trimmed():
    from app import Candidate
    assert Candidate(query="  engineer  ", location=" Delhi ").model_dump()["query"] == "engineer"
    assert Candidate(query="engineer", location=" Delhi ").location == "Delhi"


def test_refresh_disabled_by_default(monkeypatch):
    monkeypatch.delenv("JOBMATCH_REFRESH_TOKEN", raising=False)
    monkeypatch.setattr("app.refresh_from_web", lambda: pytest.fail("must not fetch"))
    with TestClient(app) as client:
        assert client.post("/refresh").status_code == 503


@pytest.mark.parametrize("token", [None, "wrong", "non-ascii-ü"])
def test_refresh_rejects_unauthorized_without_fetch(monkeypatch, token):
    monkeypatch.setenv("JOBMATCH_REFRESH_TOKEN", "test-secret")
    monkeypatch.setattr("app.refresh_from_web", lambda: pytest.fail("must not fetch"))
    from app import refresh
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        refresh(token)
    assert exc.value.status_code == 401


def test_authorized_refresh_updates_index(monkeypatch):
    monkeypatch.setenv("JOBMATCH_REFRESH_TOKEN", "test-secret")
    records = read_snapshot()
    monkeypatch.setattr("app.refresh_from_web", lambda: records)
    monkeypatch.setattr("app.upsert_jobs", lambda rows: len(rows))
    monkeypatch.setattr("app.load_jobs", lambda: records)
    with TestClient(app) as client:
        result = client.post("/refresh", headers={"X-Refresh-Token": "test-secret"})
        assert result.status_code == 200
        assert result.json()["total_jobs"] == len(records)


def test_failed_refresh_preserves_working_index(monkeypatch):
    monkeypatch.setenv("JOBMATCH_REFRESH_TOKEN", "test-secret")
    def unavailable():
        raise RuntimeError("upstream unavailable")
    monkeypatch.setattr("app.refresh_from_web", unavailable)
    with TestClient(app) as client:
        before = client.get("/health").json()
        assert client.post("/refresh", headers={"X-Refresh-Token": "test-secret"}).status_code == 502
        assert client.get("/health").json() == before
        assert client.post("/recommend", json={"query": "engineer"}).status_code == 200
