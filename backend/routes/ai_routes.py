"""
AI-powered endpoints that operate on processed meetings.

POST /meetings/{id}/ask   → Q&A against meeting transcript

Rate limiting:
  Simple token-bucket implemented with an in-memory dict keyed by user_id.
  Tracks request timestamps per user and slides the window every request.
  Limit: QA_RATE_LIMIT_PER_MINUTE requests per user per 60-second window.

  Why in-memory instead of Redis?
  - Simpler: no extra dependency for a single endpoint
  - Fine for single-instance deployment (Render free tier)
  - Visible: makes rate limiting logic explicit, good for portfolio review
  - Easy upgrade path: swap the dict for Redis INCR + EXPIRE in Phase N+1

  Trade-off: rate limit resets on server restart and doesn't work across
  multiple replicas. Acceptable for this scale.
"""

import logging
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Deque, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Meeting, User
from ..auth import get_current_user
from ..schemas import QARequest, QAResponse
from ..ai_service import answer_question
from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AI"])

# In-memory rate limiter
_rate_store: Dict[str, Deque[float]] = defaultdict(deque)
_rate_lock = Lock()


def _check_rate_limit(user_id: str) -> None:
    """
    Sliding-window rate limiter.
    Raises HTTP 429 if the user has exceeded QA_RATE_LIMIT_PER_MINUTE
    requests in the past 60 seconds.
    """
    limit = settings.QA_RATE_LIMIT_PER_MINUTE
    window = 60.0  # seconds
    now = time.time()
    cutoff = now - window

    with _rate_lock:
        timestamps = _rate_store[user_id]

        # Drop timestamps outside the sliding window
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()

        if len(timestamps) >= limit:
            oldest = timestamps[0]
            retry_after = int(window - (now - oldest)) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Rate limit exceeded: {limit} Q&A requests per minute. "
                    f"Retry after {retry_after} seconds."
                ),
                headers={"Retry-After": str(retry_after)},
            )

        timestamps.append(now)


# Q&A endpoint
@router.post(
    "/meetings/{meeting_id}/ask",
    response_model=QAResponse,
    summary="Ask a question about a meeting",
)
def ask_question(
    meeting_id: str,
    payload: QARequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Answer a natural language question about a specific meeting.

    **How it works:**
    - Retrieves the meeting's full transcript from the database
    - Passes transcript + question to Gemini 2.5 Flash in a single prompt
    - No RAG, no vector DB — Gemini's 1M token context handles any meeting length

    **Requirements:**
    - Meeting must belong to the authenticated user
    - Meeting must have `status = completed` (transcript must exist)
    - `GEMINI_API_KEY` must be configured

    **Rate limit:** {limit} requests per user per 60 seconds.
    """.format(limit=settings.QA_RATE_LIMIT_PER_MINUTE)

    # Rate limit check
    _check_rate_limit(current_user.id)

    # Load and validate meeting
    meeting = (
        db.query(Meeting)
        .filter(Meeting.id == meeting_id, Meeting.user_id == current_user.id)
        .first()
    )
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if meeting.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Meeting is not yet processed (status: {meeting.status}). "
                "Wait for processing to complete before asking questions."
            ),
        )

    if not meeting.transcript:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "This meeting has no transcript. "
                "Ensure GROQ_API_KEY is configured and reprocess the meeting."
            ),
        )

    # Check API key before calling
    if not settings.GEMINI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GEMINI_API_KEY is not configured. Q&A is unavailable.",
        )

    # Call Gemini
    try:
        logger.info(
            f"Q&A request: meeting={meeting_id}, user={current_user.id}, "
            f"question_len={len(payload.question)}"
        )
        answer = answer_question(
            transcript=meeting.transcript,
            question=payload.question,
            meeting_title=meeting.title,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except RuntimeError as e:
        logger.error(f"Q&A failed for meeting {meeting_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI service error: {str(e)}",
        )

    return QAResponse(
        meeting_id=meeting_id,
        question=payload.question,
        answer=answer,
        model=settings.GEMINI_MODEL,
    )