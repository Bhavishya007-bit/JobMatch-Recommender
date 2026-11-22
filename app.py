"""FastAPI service over real employer ATS job listings."""
from contextlib import asynccontextmanager
import os
import secrets
from fastapi import FastAPI, HTTPException, Query, Header
from pydantic import BaseModel, Field, field_validator

from data import load_jobs, refresh_from_web, upsert_jobs
from recommender import JobRecommender

engine: JobRecommender | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine
    engine = JobRecommender(load_jobs())
    yield


app = FastAPI(
    title="JobMatch — Real Job Postings Recommendation API",
    description="Real ATS job metadata; lexical+LSA ranking, optional location filters. Never fabricates listings.",
    version="0.2.0", lifespan=lifespan
)


class Candidate(BaseModel):
    query: str = Field(min_length=2, max_length=2000, description="Search phrase, e.g. 'Python AI engineer internship'")
    location: str = Field(default="", max_length=200)
    remote_only: bool = False
    remote_ok: bool = True
    internship_only: bool = False


    @field_validator("query", "location", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


def model() -> JobRecommender:
    if engine is None:
        raise HTTPException(status_code=503, detail="Recommendation index is not loaded")
    return engine


@app.get("/health")
def health():
    return {"status": "ok", "job_count": len(model().jobs), "dataset": "real ATS postings"}


@app.get("/jobs")
def jobs(limit: int = Query(20, ge=1, le=100)):
    return model().jobs[:limit]


@app.post("/recommend")
def recommend(candidate: Candidate, k: int = Query(10, ge=1, le=50)):
    recommendations = model().recommend(candidate.model_dump(), k=k)
    return {"count": len(recommendations), "recommendations": recommendations}


@app.post("/refresh")
def refresh(x_refresh_token: str | None = Header(default=None)):
    """Fetch upstream's daily incremental new jobs; requires network access.
    Disabled unless JOBMATCH_REFRESH_TOKEN is configured; requires matching header.
    """
    global engine
    configured_token = os.environ.get("JOBMATCH_REFRESH_TOKEN", "")
    if not configured_token:
        raise HTTPException(status_code=503, detail="HTTP refresh is disabled")
    if not x_refresh_token or not secrets.compare_digest(
        x_refresh_token.encode("utf-8"), configured_token.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    try:
        records = refresh_from_web()
        changed = upsert_jobs(records)
        engine = JobRecommender(load_jobs())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Refresh failed: {type(exc).__name__}") from exc
    return {"ingested": changed, "total_jobs": len(engine.jobs), "source": "ConorsCode/open-jobs-data"}
