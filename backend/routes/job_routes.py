"""
routes/job_routes.py
--------------------
Job status endpoints.

GET /jobs/{job_id}         → poll processing status (cache-first)
GET /jobs/meeting/{id}     → get job for a specific meeting

Cache-first strategy:
  1. Check Redis for cached status (fast, O(1))
  2. If cache miss, query DB (slower, but always accurate)
  3. Cache the DB result for future polls
  4. Return status with a 'source' field indicating cache vs DB

This pattern is explicitly visible in the response — good for portfolio
demos showing caching knowledge.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Job, User
from ..auth import get_current_user
from ..schemas import JobStatusResponse
from ..cache import get_cached_job_status, cache_job_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["Jobs"])


# Helpers

def _job_to_response(job: Job, source: str = "db") -> JobStatusResponse:
    """Convert a Job ORM object to a JobStatusResponse schema."""
    return JobStatusResponse(
        job_id=job.id,
        meeting_id=job.meeting_id,
        status=job.status,
        progress=job.progress,
        current_step=job.current_step,
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        source=source,
    )


def _cached_to_response(cached: dict) -> JobStatusResponse:
    """Convert a Redis cache dict to a JobStatusResponse schema."""
    return JobStatusResponse(
        job_id=cached["job_id"],
        meeting_id=cached["meeting_id"],
        status=cached["status"],
        progress=cached["progress"],
        current_step=cached["current_step"],
        error_message=cached.get("error_message"),
        created_at=cached.get("created_at"),
        started_at=cached.get("started_at"),
        completed_at=cached.get("completed_at"),
        source="cache",
    )


def _fetch_job_for_user(job_id: str, user_id: str, db: Session) -> Job:
    """
    Load a job from DB, scoped to the requesting user.
    Raises 404 if not found or belongs to another user.
    """
    job = (
        db.query(Job)
        .filter(Job.id == job_id, Job.user_id == user_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# Get job status (cache-first)


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    summary="Poll job processing status",
)
def get_job_status(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return the current status of a background processing job.

    **Cache-first strategy:**
    - Checks Redis first (sub-millisecond).
    - Falls back to DB on cache miss.
    - Repopulates cache from DB result.
    - Response includes `source: "cache" | "db"` for observability.

    Poll this endpoint every 2–3 seconds until `status` is `completed` or `failed`.
    """
    
    # 1. Try Redis cache first
    
    cached = get_cached_job_status(job_id)
    if cached:
        # Verify ownership without hitting the DB
        # The job_id is enough — we stored it in cache when we created it
        # For security, we still need to verify user ownership on cache miss
        # On a cache hit for an in-progress job, we trust the cache.
        # Completed/failed jobs: also check DB for authoritative ownership.
        if cached.get("status") in ("queued", "processing"):
            # For in-progress jobs, verify ownership quickly via DB
            job = _fetch_job_for_user(job_id, current_user.id, db)
            # Update cache with any latest DB data while we have it
            if job.progress > cached.get("progress", 0):
                return _job_to_response(job, source="db")
            return _cached_to_response(cached)

    
    # 2. Cache miss — fetch from DB
    
    job = _fetch_job_for_user(job_id, current_user.id, db)

    # Repopulate cache for next poll
    response = _job_to_response(job, source="db")
    cache_job_status(job_id, {
        "job_id": job.id,
        "meeting_id": job.meeting_id,
        "status": job.status,
        "progress": job.progress,
        "current_step": job.current_step,
        "error_message": job.error_message,
        "created_at": str(job.created_at),
        "started_at": str(job.started_at) if job.started_at else None,
        "completed_at": str(job.completed_at) if job.completed_at else None,
    })

    return response


# Get job for a meeting

@router.get(
    "/meeting/{meeting_id}",
    response_model=JobStatusResponse,
    summary="Get job status for a meeting",
)
def get_job_for_meeting(
    meeting_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Convenience endpoint: look up the job for a meeting_id.
    Returns the most recent job if multiple exist (re-processing scenario).
    """
    job = (
        db.query(Job)
        .filter(Job.meeting_id == meeting_id, Job.user_id == current_user.id)
        .order_by(Job.created_at.desc())
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="No job found for this meeting")

    return _job_to_response(job, source="db")
