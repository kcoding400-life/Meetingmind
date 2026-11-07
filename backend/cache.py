"""
Redis integration for job status caching.

Design decisions:
- Redis stores job status as a JSON blob under the key "job:{job_id}".
- TTL = 24 hours (configurable). After that the key expires automatically.
- ALL Redis calls are wrapped in try/except — if Redis is unavailable,
  the app degrades gracefully (falls back to DB for job status).
- We do NOT use Redis as a job queue or broker. It's purely a read cache
  for the polling endpoint, so job status updates don't hammer the DB.
- get_redis() returns a new connection per call. Redis connections are
  cheap and pool internally; this avoids stale connection issues.
"""

import json
import logging
from typing import Optional

import redis

from .config import settings

logger = logging.getLogger(__name__)



# Connection


def get_redis() -> Optional[redis.Redis]:
    """
    Return a Redis client, or None if Redis is unavailable.
    Callers must handle the None case.
    """
    try:
        client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,  # fail fast if Redis is down
            socket_timeout=2,
        )
        client.ping()
        return client
    except Exception as e:
        logger.warning(f"Redis unavailable: {e}")
        return None


def check_redis_connection() -> bool:
    """Ping Redis. Used by the /health endpoint."""
    client = get_redis()
    return client is not None



# Job status cache


def _job_key(job_id: str) -> str:
    return f"job:{job_id}"


def cache_job_status(job_id: str, status_data: dict) -> bool:
    """
    Write job status to Redis.
    status_data should match the JobStatusResponse schema.
    Returns True on success, False if Redis is unavailable.
    """
    client = get_redis()
    if client is None:
        return False
    try:
        client.setex(
            name=_job_key(job_id),
            time=settings.REDIS_JOB_TTL,
            value=json.dumps(status_data, default=str),
        )
        return True
    except Exception as e:
        logger.warning(f"Failed to cache job {job_id}: {e}")
        return False


def get_cached_job_status(job_id: str) -> Optional[dict]:
    """
    Read job status from Redis.
    Returns the status dict or None (cache miss or Redis unavailable).
    """
    client = get_redis()
    if client is None:
        return None
    try:
        raw = client.get(_job_key(job_id))
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.warning(f"Failed to read cached job {job_id}: {e}")
        return None


def invalidate_job_cache(job_id: str) -> bool:
    """Delete a job's cached status. Called when a job is deleted."""
    client = get_redis()
    if client is None:
        return False
    try:
        client.delete(_job_key(job_id))
        return True
    except Exception as e:
        logger.warning(f"Failed to invalidate job cache {job_id}: {e}")
        return False


def update_job_progress(
    job_id: str,
    status: str,
    progress: int,
    current_step: str,
    extra: Optional[dict] = None,
) -> bool:
    """
    Convenience function used by the background worker to push progress
    updates to Redis without touching the DB every step.

    extra: any additional fields to merge into the cache entry.
    """
    data = {
        "job_id": job_id,
        "status": status,
        "progress": progress,
        "current_step": current_step,
    }
    if extra:
        data.update(extra)
    return cache_job_status(job_id, data)
