"""
Centralised configuration loaded from environment variables.

Pydantic-settings validates types and raises clear errors at startup
if required variables are missing — far better than silent None values.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    
    # App
    
    APP_NAME: str = "MeetingMind API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    
    # Database  (Supabase PostgreSQL connection string)
    # Format: postgresql://user:password@host:port/dbname
    
    DATABASE_URL: str

    
    # JWT
    
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    
    # Supabase Storage  (Phase 2)
    # Get from: Supabase Dashboard → Settings → API
    
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""   # service_role key (bypasses RLS)
    SUPABASE_BUCKET: str = "meeting-audio"

    
    # Redis  (Phase 2)
    # Format: redis://[:password@]host:port/db
    
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_JOB_TTL: int = 60 * 60 * 24  # keep job status for 24 hours

    
    # Upload limits
    
    MAX_UPLOAD_SIZE_MB: int = 100

    
    # AI — Groq (transcription via Whisper)
    # Get from: https://console.groq.com/keys
    
    GROQ_API_KEY: str = ""
    GROQ_WHISPER_MODEL: str = "whisper-large-v3"

    
    # AI — Google Gemini (analysis)
    # Get from: https://aistudio.google.com/app/apikey
    
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash-preview-05-20"

    
    # AI — Rate limiting (requests per user per minute for Q&A)
    
    QA_RATE_LIMIT_PER_MINUTE: int = 10

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Cached settings — evaluated once, reused everywhere."""
    return Settings()


# Module-level singleton for convenience: `from .config import settings`
settings = get_settings()
