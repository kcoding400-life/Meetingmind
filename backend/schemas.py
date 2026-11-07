"""
Pydantic v2 schemas for request validation and response serialisation.

Separation from ORM models is intentional:
- ORM models = database shape
- Schemas = API contract

This lets them evolve independently and keeps sensitive fields
(hashed_password) from accidentally leaking into responses.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator
import re



# Auth schemas


class UserRegisterRequest(BaseModel):
    email: EmailStr
    full_name: str
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v

    @field_validator("full_name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Full name cannot be blank")
        return v.strip()


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds



# User response (safe — no password fields)


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class RegisterResponse(BaseModel):
    message: str
    user: UserResponse



# Generic


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    redis: str = "not configured"
    ai_pipeline: str = "not configured"


class MessageResponse(BaseModel):
    message: str



# Meeting schemas


class MeetingUploadResponse(BaseModel):
    """Returned immediately after a file upload — before processing completes."""
    meeting_id: str
    job_id: str
    message: str


class MeetingResponse(BaseModel):
    """Full meeting record returned from GET /meetings/{id}."""
    id: str
    user_id: str
    title: str
    description: Optional[str]
    file_name: Optional[str]
    file_size_bytes: Optional[int]
    duration_seconds: Optional[float]
    storage_path: Optional[str]
    status: str
    error_message: Optional[str]
    # AI fields (None until Phase 3 processing completes)
    transcript: Optional[str]
    summary: Optional[str]
    action_items: Optional[str]   # JSON string
    decisions: Optional[str]      # JSON string
    risks: Optional[str]          # JSON string
    follow_up_email: Optional[str]
    participants: Optional[str]   # JSON string
    language: Optional[str]
    created_at: datetime
    updated_at: datetime
    processed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class MeetingListItem(BaseModel):
    """Lightweight meeting summary for list views."""
    id: str
    title: str
    status: str
    file_name: Optional[str]
    duration_seconds: Optional[float]
    created_at: datetime
    processed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class MeetingListResponse(BaseModel):
    meetings: list[MeetingListItem]
    total: int



# Job schemas


class JobStatusResponse(BaseModel):
    """Returned by GET /jobs/{id} — used for polling processing progress."""
    job_id: str
    meeting_id: str
    status: str           # queued | processing | completed | failed
    progress: int         # 0–100
    current_step: str
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    # Indicates whether this response came from cache or DB
    source: str = "db"   # "cache" | "db"

    model_config = {"from_attributes": True}



# Q&A schemas


class QARequest(BaseModel):
    """Request body for POST /meetings/{id}/ask."""
    question: str

    @field_validator("question")
    @classmethod
    def question_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Question cannot be empty")
        if len(v) > 2000:
            raise ValueError("Question must be under 2000 characters")
        return v


class QAResponse(BaseModel):
    """Response from the Q&A endpoint."""
    meeting_id: str
    question: str
    answer: str
    model: str = "gemini-2.5-flash"



