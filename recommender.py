"""Real ATS listing retrieval: TF-IDF and LSA, with transparent metadata filters.

Upstream data has no detailed job descriptions, inferred skills, or verified relevance labels.
Therefore this ranks actual titles/departments/companies only. No fake skills.
"""
from __future__ import annotations
from typing import Any
import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from data import load_jobs


class JobRecommender:
    def __init__(self, jobs: list[dict]):
        self.jobs = list(jobs)
        if not self.jobs:
            raise ValueError("No jobs available. Ingest a real snapshot first.")
        corpus = [self.document(job) for job in self.jobs]
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
        self.tfidf = self.vectorizer.fit_transform(corpus)
        dims = min(60, self.tfidf.shape[0] - 1, self.tfidf.shape[1] - 1)
        self.reducer = TruncatedSVD(n_components=dims, random_state=42) if dims >= 2 else None
        self.lsa = self.reducer.fit_transform(self.tfidf) if self.reducer else None

    @staticmethod
    def document(job: dict) -> str:
        # Only information actually provided by upstream; no invented descriptions or requirements.
        return " ".join([str(job.get("title") or "")] * 3 +
                        [str(job.get("department") or ""), str(job.get("company") or "")])

    def recommend(self, profile: dict[str, Any], k: int = 10, mode: str = "hybrid") -> list[dict]:
        if mode not in ("hybrid", "baseline"):
            raise ValueError("mode must be 'hybrid' or 'baseline'")
        query = str(profile.get("query") or "").strip()
        if not query:
            raise ValueError("query must not be blank")
        text_vector = self.vectorizer.transform([query])
        lexical = cosine_similarity(text_vector, self.tfidf)[0]
        semantic = cosine_similarity(self.reducer.transform(text_vector), self.lsa)[0] if self.reducer else lexical
        # Using raw cosine similarities; the text feature is LSA, not transformer embeddings.
        desired_location = str(profile.get("location") or "").casefold().strip()
        remote_only = bool(profile.get("remote_only", False))
        remote_ok = bool(profile.get("remote_ok", True))
        internship_only = bool(profile.get("internship_only", False))
        filtered = []
        for idx, job in enumerate(self.jobs):
            if remote_only and job["is_remote"] is not True:
                continue
            if not remote_ok and job["is_remote"] is True:
                continue
            if internship_only and not any(t in job["title"].casefold() for t in ("intern", "internship")):
                continue
            locations = " ".join(job["locations"]).casefold()
            loc_match = bool(desired_location and desired_location in locations)
            remote_match = bool(remote_ok and job["is_remote"] is True)
            score = float(lexical[idx]) if mode == "baseline" else (
                0.65 * float(lexical[idx]) + 0.25 * max(0.0, float(semantic[idx]))
                + 0.10 * float(loc_match or remote_match)
            )
            filtered.append({
                "job_key": job["job_key"],
                "title": job["title"], "company": job["company"], "department": job["department"],
                "locations": job["locations"], "is_remote": job["is_remote"],
                "employment_type": job["employment_type"], "apply_url": job["apply_url"],
                "platform": job["platform"], "posted_at": job["posted_at"],
                "scraped_at": job["scraped_at"], "score": round(score, 6),
                "signals": {"text_similarity": round(float(lexical[idx]), 5),
                            "lsa_similarity": round(float(semantic[idx]), 5),
                            "location_match": loc_match, "confirmed_remote": job["is_remote"] is True},
            })
        filtered.sort(key=lambda r: (-r["score"], r["job_key"]))
        return filtered[:k]
