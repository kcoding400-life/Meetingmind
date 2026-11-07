"""
FastAPI application entry point.

Responsibilities:
- Create the FastAPI app instance
- Register all routers
- Run database and storage initialisation on startup
- Expose /health for load-balancer checks (DB + Redis)
"""

import logging
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import init_db, check_db_connection
from .cache import check_redis_connection
from .storage import ensure_bucket_exists
from .schemas import HealthResponse, UserResponse
from .auth import get_current_user
from .models import User
from .routes.auth_routes import router as auth_router
from .routes.meeting_routes import router as meeting_router
from .routes.job_routes import router as job_router
from .routes.ai_routes import router as ai_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



# App creation

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "MeetingMind: AI-powered meeting intelligence platform. "
        "Transcribes, analyses, and extracts action items from your meetings."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)



# CORS

# In production, replace "*" with your Streamlit frontend origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# Startup

@app.on_event("startup")
def on_startup():
    """
    Initialise all external dependencies on boot.
    - Create DB tables (idempotent)
    - Create Supabase Storage bucket (idempotent)
    - Log Redis status
    """
    logger.info("Starting MeetingMind API...")
    init_db()
    logger.info("Database tables initialised")

    if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY:
        ok = ensure_bucket_exists()
        logger.info(f"Storage bucket '{settings.SUPABASE_BUCKET}': {'ready' if ok else 'check manually'}")
    else:
        logger.warning("SUPABASE_URL/SERVICE_KEY not set — storage disabled")

    redis_ok = check_redis_connection()
    logger.info(f"Redis: {'connected' if redis_ok else 'unavailable (degraded mode)'}")

    groq_ok = bool(settings.GROQ_API_KEY)
    gemini_ok = bool(settings.GEMINI_API_KEY)
    logger.info(f"AI pipeline: Groq={'✓' if groq_ok else '✗ (GROQ_API_KEY missing)'} | Gemini={'✓' if gemini_ok else '✗ (GEMINI_API_KEY missing)'}")



# Routers

app.include_router(auth_router, prefix="/api/v1")
app.include_router(meeting_router, prefix="/api/v1")
app.include_router(job_router, prefix="/api/v1")
app.include_router(ai_router, prefix="/api/v1")



# Health endpoint

@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["System"],
    summary="Health check",
)
def health():
    """
    Returns application health status for all dependencies.
    Used by Docker, Render, and load balancers.
    """
    db_ok = check_db_connection()
    redis_ok = check_redis_connection()
    groq_ok = bool(settings.GROQ_API_KEY)
    gemini_ok = bool(settings.GEMINI_API_KEY)
    ai_ok = groq_ok and gemini_ok

    all_ok = db_ok  # Redis + AI are degraded-mode acceptable
    return HealthResponse(
        status="healthy" if all_ok else "degraded",
        version=settings.APP_VERSION,
        database="connected" if db_ok else "unreachable",
        redis="connected" if redis_ok else "unavailable",
        ai_pipeline="ready" if ai_ok else (
            "partial (groq only)" if groq_ok else
            "partial (gemini only)" if gemini_ok else
            "not configured"
        ),
    )



# Root

@app.get("/", tags=["System"], summary="API root")
def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "auth": "/api/v1/auth",
            "meetings": "/api/v1/meetings",
            "jobs": "/api/v1/jobs",
        },
    }



# Protected route example (demonstrates auth works)

@app.get(
    "/api/v1/protected",
    response_model=UserResponse,
    tags=["System"],
    summary="Protected route demo",
)
def protected(current_user: User = Depends(get_current_user)):
    """Requires a valid Bearer token. Useful for integration testing."""
    return UserResponse.model_validate(current_user)
