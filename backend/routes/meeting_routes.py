"""
Meeting management endpoints.

POST   /meetings/upload           → upload audio, create job, start processing
GET    /meetings                  → list all meetings for current user
GET    /meetings/{id}             → get single meeting with all fields
DELETE /meetings/{id}             → delete meeting + audio file + job

All routes require authentication. All queries are scoped to current_user.id.
"""

import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Meeting, Job, User
from ..auth import get_current_user
from ..schemas import (
    MeetingUploadResponse,
    MeetingResponse,
    MeetingListResponse,
    MeetingListItem,
    MessageResponse,
)
from ..storage import upload_audio, delete_audio, validate_audio_file
from ..processor import enqueue_meeting

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/meetings", tags=["Meetings"])


# Upload


@router.post(
    "/upload",
    response_model=MeetingUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a meeting audio file",
)
async def upload_meeting(
    title: str = Form(..., description="Meeting title"),
    description: Optional[str] = Form(None, description="Optional description"),
    file: UploadFile = File(..., description="Audio file (mp3, mp4, m4a, wav, etc.)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a meeting recording. Returns immediately with a job_id for polling.

    Flow:
      1. Validate file type and size
      2. Create Meeting record (status=pending)
      3. Create Job record (status=queued)
      4. Upload audio to Supabase Storage
      5. Spawn background thread for processing
      6. Return {meeting_id, job_id} — client polls /jobs/{job_id} for progress
    """
    # 1. Read file into memory and validate
   
    file_bytes = await file.read()
    file_size = len(file_bytes)

    validation_error = validate_audio_file(file.filename, file_size)
    if validation_error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=validation_error,
        )

    
    # 2. Create Meeting record
    
    meeting_id = str(uuid.uuid4())
    meeting = Meeting(
        id=meeting_id,
        user_id=current_user.id,
        title=title.strip(),
        description=description.strip() if description else None,
        file_name=file.filename,
        file_size_bytes=file_size,
        status="pending",
    )
    db.add(meeting)
    db.flush()  # get the ID into DB without committing yet

    
    # 3. Create Job record
    
    job_id = str(uuid.uuid4())
    job = Job(
        id=job_id,
        meeting_id=meeting_id,
        user_id=current_user.id,
        status="queued",
        progress=0,
        current_step="Waiting to start",
    )
    db.add(job)
    db.commit()

    
    # 4. Upload to Supabase Storage
    
    try:
        storage_result = upload_audio(
            user_id=current_user.id,
            meeting_id=meeting_id,
            file=file,
            file_bytes=file_bytes,
        )
        meeting.storage_path = storage_result["storage_path"]
        meeting.file_size_bytes = storage_result["file_size"]
        db.commit()

    except Exception as e:
        # Storage upload failed — mark job as failed immediately
        logger.error(f"Storage upload failed for meeting {meeting_id}: {e}")
        job.status = "failed"
        job.current_step = "Storage upload failed"
        job.error_message = str(e)
        meeting.status = "failed"
        meeting.error_message = f"File upload failed: {str(e)}"
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not upload audio file: {str(e)}",
        )

    
    # 5. Enqueue background processing
    # enqueue_meeting now wires in run_ai_pipeline automatically when
    # GROQ_API_KEY + GEMINI_API_KEY are present in the environment.
    
    enqueue_meeting(job_id=job_id, meeting_id=meeting_id)

    logger.info(
        f"Meeting {meeting_id} uploaded by user {current_user.id}. "
        f"Job {job_id} enqueued."
    )

    return MeetingUploadResponse(
        meeting_id=meeting_id,
        job_id=job_id,
        message="Upload successful. Processing has started.",
    )


# List meetings

@router.get(
    "",
    response_model=MeetingListResponse,
    summary="List all meetings for current user",
)
def list_meetings(
    skip: int = 0,
    limit: int = 50,
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return a paginated list of meetings for the authenticated user.
    Optionally filter by status: pending | processing | completed | failed
    """
    query = db.query(Meeting).filter(Meeting.user_id == current_user.id)

    if status_filter:
        query = query.filter(Meeting.status == status_filter)

    total = query.count()
    meetings = (
        query.order_by(Meeting.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return MeetingListResponse(
        meetings=[MeetingListItem.model_validate(m) for m in meetings],
        total=total,
    )


# Get single meeting

@router.get(
    "/{meeting_id}",
    response_model=MeetingResponse,
    summary="Get a meeting by ID",
)
def get_meeting(
    meeting_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return full meeting details including AI analysis fields (once processed).
    Returns 404 if the meeting doesn't exist or belongs to another user.
    """
    meeting = (
        db.query(Meeting)
        .filter(Meeting.id == meeting_id, Meeting.user_id == current_user.id)
        .first()
    )
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    return MeetingResponse.model_validate(meeting)


# Delete meeting


@router.delete(
    "/{meeting_id}",
    response_model=MessageResponse,
    summary="Delete a meeting",
)
def delete_meeting(
    meeting_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a meeting record, its associated jobs, and its audio file from storage.

    - Storage deletion is best-effort (won't fail the request if file is missing)
    - Database deletion cascades to Job records via FK
    """
    meeting = (
        db.query(Meeting)
        .filter(Meeting.id == meeting_id, Meeting.user_id == current_user.id)
        .first()
    )
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Delete audio from Supabase Storage (best-effort)
    if meeting.storage_path:
        deleted = delete_audio(meeting.storage_path)
        if not deleted:
            logger.warning(f"Could not delete storage file: {meeting.storage_path}")

    # Delete from DB (cascades to jobs via FK)
    db.delete(meeting)
    db.commit()

    logger.info(f"Meeting {meeting_id} deleted by user {current_user.id}")
    return MessageResponse(message="Meeting deleted successfully")
