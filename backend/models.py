"""
SQLAlchemy ORM models.

Design decisions:
- UUIDs as primary keys: collision-resistant, safe to expose in URLs.
- server_default=func.now(): timestamp set by the DB, not application code,
  so it's accurate even if the app server clock drifts.
- Passwords are NEVER stored; only the bcrypt hash lives in the DB.
- Job and Meeting are separate tables: jobs are transient (processing state),
  meetings are permanent (data). Different lifecycles, different concerns.
- All meeting/job queries are scoped to user_id — no cross-user data leakage.
"""

import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Float, Integer, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


class User(Base):
    __tablename__ = "users"

    
    # Identity
    
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,  # fast lookup by email on login
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    
    # Status
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    
    # Timestamps
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"



# Meeting


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    
    # Metadata supplied at upload time
    
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)

    
    # Audio file info (populated after successful Supabase Storage upload)
    
    file_name: Mapped[str] = mapped_column(String(500), nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=True)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=True)

    
    # Processing status
    # status flow: pending → processing → completed | failed
    
    status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False, index=True
    )
    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    
    # AI results (Phase 3 — columns exist now, populated later)
    
    transcript: Mapped[str] = mapped_column(Text, nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=True)
    action_items: Mapped[str] = mapped_column(Text, nullable=True)   # JSON string
    decisions: Mapped[str] = mapped_column(Text, nullable=True)       # JSON string
    risks: Mapped[str] = mapped_column(Text, nullable=True)           # JSON string
    follow_up_email: Mapped[str] = mapped_column(Text, nullable=True)
    participants: Mapped[str] = mapped_column(Text, nullable=True)    # JSON string
    language: Mapped[str] = mapped_column(String(10), nullable=True)

    
    # Timestamps
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationship back to user
    user: Mapped["User"] = relationship("User", backref="meetings")

    def __repr__(self) -> str:
        return f"<Meeting id={self.id} title={self.title!r} status={self.status}>"



# Job


class Job(Base):
    """
    Tracks the lifecycle of a background processing task.

    One job is created per meeting upload. The background thread updates
    the job status in the DB (source of truth) and in Redis (fast cache
    for polling). The job record is never deleted — it's the audit trail.
    """
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    
    # Status tracking
    # status flow: queued → processing → completed | failed
    # progress: 0–100 percentage
    
    status: Mapped[str] = mapped_column(
        String(50), default="queued", nullable=False
    )
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_step: Mapped[str] = mapped_column(
        String(200), default="Waiting to start", nullable=False
    )
    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    
    # Timestamps
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationship
    meeting: Mapped["Meeting"] = relationship("Meeting", backref="jobs")

    def __repr__(self) -> str:
        return f"<Job id={self.id} status={self.status} progress={self.progress}%>"
