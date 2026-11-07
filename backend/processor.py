"""
Background meeting processor.

Architecture:
  Upload endpoint → creates Meeting + Job records → spawns Thread → returns job_id
  Thread → updates Job status in DB + Redis at each step → signals completion

Why threading over Celery/RQ for this phase:
  - No broker infrastructure needed (Celery requires Redis/RabbitMQ as a *queue*)
  - Single-process, same container — simple to reason about and deploy
  - Appropriate for a portfolio project demonstrating the async pattern
  - Easy to swap out: replace `threading.Thread` with `.delay()` in Phase N+1

Thread safety:
  - Each background thread creates its OWN database session (never shares one).
  - SQLAlchemy's SessionLocal is thread-safe as long as sessions aren't shared.
  - Redis writes are atomic (SETEX).

Phase 3: ai_processor now defaults to ai_service.run_ai_pipeline.
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import Job, Meeting
from .cache import update_job_progress

logger = logging.getLogger(__name__)



# Step definitions (progress %, label) — matches real AI pipeline phases

PROCESSING_STEPS = [
    (10,  "Validating audio file"),
    (20,  "Audio stored in cloud"),
    (35,  "Downloading audio for transcription"),
    (55,  "Transcribing audio with Groq Whisper"),
    (80,  "Analysing meeting with Gemini AI"),
    (95,  "Saving results to database"),
    (100, "Complete"),
]



# Job state helpers — always use a fresh session in the background thread


def _update_job(
    db: Session,
    job: Job,
    status: str,
    progress: int,
    current_step: str,
    error_message: str = None,
) -> None:
    """
    Persist job state to DB and push to Redis cache.
    Called from background thread — uses the thread-local session.
    """
    job.status = status
    job.progress = progress
    job.current_step = current_step
    if error_message:
        job.error_message = error_message
    if status == "processing" and job.started_at is None:
        job.started_at = datetime.now(timezone.utc)
    if status in ("completed", "failed"):
        job.completed_at = datetime.now(timezone.utc)

    db.commit()

    # Mirror to Redis (best-effort — never raise on failure)
    update_job_progress(
        job_id=job.id,
        status=status,
        progress=progress,
        current_step=current_step,
        extra={
            "meeting_id": job.meeting_id,
            "error_message": error_message,
            "created_at": str(job.created_at),
            "started_at": str(job.started_at) if job.started_at else None,
            "completed_at": str(job.completed_at) if job.completed_at else None,
        },
    )


def _fail_job(db: Session, job: Job, meeting: Meeting, reason: str) -> None:
    """Mark both the Job and Meeting as failed with the full error reason."""
    logger.error(f"Job {job.id} failed: {reason}")
    _update_job(db, job, "failed", job.progress, f"Failed: {reason[:100]}", reason)
    meeting.status = "failed"
    meeting.error_message = reason
    db.commit()



# Main processing function — runs in a background daemon thread


def process_meeting(
    job_id: str,
    meeting_id: str,
    ai_processor: Optional[Callable] = None,
) -> None:
    """
    Background thread entry point. Full pipeline:

      10%  → Validate audio file exists
      20%  → Confirm cloud storage
      35%  → Signal download starting (ai_processor does the actual download)
      55%  → Signal transcription starting (Groq Whisper inside ai_processor)
      80%  → Signal Gemini analysis starting (inside ai_processor)
      95%  → Results saved to DB (inside ai_processor)
      100% → Mark complete

    The ai_processor callable is run_ai_pipeline from ai_service.py.
    It handles the heavy work (download → transcribe → analyse → save).
    Progress updates here bookend the AI work so the client sees movement.

    If ai_processor is None (no API keys set), the job completes without
    AI results — the transcript and analysis fields remain null.
    """
    # Each thread MUST create its own session — never share across threads
    db: Session = SessionLocal()

    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()

        if not job or not meeting:
            logger.error(f"process_meeting: job {job_id} or meeting {meeting_id} not found")
            return

        logger.info(f"Starting pipeline for meeting {meeting_id} (job {job_id})")

        
        # Step 1: Validate
        
        _update_job(db, job, "processing", 10, "Validating audio file")
        meeting.status = "processing"
        db.commit()

        if not meeting.storage_path:
            _fail_job(db, job, meeting, "No audio file found in storage")
            return

        
        # Step 2: Confirm storage
        
        _update_job(db, job, "processing", 20, "Audio stored in cloud")

        
        # Steps 3–5: AI pipeline (download → transcribe → analyse → save)
        
        if ai_processor is not None:
            try:
                _update_job(db, job, "processing", 35, "Downloading audio for transcription")
                # ai_processor drives its own progress internally and writes
                # transcript/analysis fields to the meeting record via db.
                # We update job progress before and after to bracket the work.
                _update_job(db, job, "processing", 55, "Transcribing audio with Groq Whisper")

                ai_processor(meeting_id=meeting_id, db=db)

                _update_job(db, job, "processing", 80, "Analysing meeting with Gemini AI")
                _update_job(db, job, "processing", 95, "Saving results to database")

            except Exception as e:
                _fail_job(db, job, meeting, f"AI processing error: {str(e)}")
                return
        else:
            # No AI keys configured — skip AI steps, still mark meeting done
            logger.warning(
                f"No ai_processor provided for job {job_id}. "
                "AI keys (GROQ_API_KEY, GEMINI_API_KEY) may not be set."
            )
            _update_job(db, job, "processing", 95, "Skipping AI (keys not configured)")

        
        # Step 6: Done
        
        _update_job(db, job, "completed", 100, "Complete")
        meeting.status = "completed"
        meeting.processed_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(f"Meeting {meeting_id} processed successfully (job {job_id})")

    except Exception as e:
        logger.exception(f"Unhandled error in process_meeting for job {job_id}: {e}")
        try:
            # Re-query in case the session is in a bad state
            job = db.query(Job).filter(Job.id == job_id).first()
            meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
            if job and meeting:
                _fail_job(db, job, meeting, f"Internal error: {str(e)}")
        except Exception:
            pass
    finally:
        db.close()



# Public API — called by meeting_routes.py


def enqueue_meeting(job_id: str, meeting_id: str) -> None:
    """
    Spawn a background daemon thread to process a meeting with the full AI pipeline.

    Lazily imports run_ai_pipeline so that missing API keys don't crash
    the import at startup — they only fail when a job actually runs.

    daemon=True: thread won't block process shutdown.
    In a production scale-out this becomes: celery_task.delay(job_id, meeting_id)
    """
    from .ai_service import run_ai_pipeline
    from .config import settings

    # Only wire in real AI if both API keys are present
    if settings.GROQ_API_KEY and settings.GEMINI_API_KEY:
        processor = run_ai_pipeline
        logger.info(f"AI pipeline enabled for job {job_id}")
    else:
        processor = None
        logger.warning(
            f"Job {job_id}: GROQ_API_KEY or GEMINI_API_KEY not set — "
            "meeting will be stored but not transcribed or analysed."
        )

    thread = threading.Thread(
        target=process_meeting,
        args=(job_id, meeting_id, processor),
        daemon=True,
        name=f"processor-{job_id[:8]}",
    )
    thread.start()
    logger.info(f"Enqueued job {job_id} for meeting {meeting_id} (thread: {thread.name})")
