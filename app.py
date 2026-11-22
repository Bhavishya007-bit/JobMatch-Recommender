"""FastAPI service over real employer ATS job listings."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

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
    query: str = Field(min_length=2, description="Search phrase, e.g. 'Python AI engineer internship'")
    location: str = ""
    remote_only: bool = False
    remote_ok: bool = True
    internship_only: bool = False


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
def refresh():
    """Fetch upstream's daily incremental new jobs; requires network access.
    Secure this endpoint with authentication before deploying publicly.
    """
    global engine
    try:
        records = refresh_from_web()
        changed = upsert_jobs(records)
        engine = JobRecommender(load_jobs())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Refresh failed: {type(exc).__name__}") from exc
    return {"ingested": changed, "total_jobs": len(engine.jobs), "source": "ConorsCode/open-jobs-data"}
