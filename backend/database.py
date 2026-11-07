"""
Single source of truth for the database connection.
We use SQLAlchemy's synchronous engine with a connection pool sized for
Supabase's free tier (max 15 connections). The session is injected into
route handlers via FastAPI's Depends() — no globals, no hidden state.
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from .config import settings



# Engine

# pool_pre_ping=True  → SQLAlchemy checks the connection is alive before use.
#                       Prevents "connection closed" errors after idle periods.
# pool_size / max_overflow → conservative values for Supabase free tier.

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    echo=settings.DEBUG,  # logs SQL in development; silent in production
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """All ORM models inherit from this base."""
    pass



# FastAPI dependency

def get_db():
    """
    Yield a database session per request, always closing it afterwards.
    Use as: db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables that don't yet exist. Called once on app startup."""
    from . import models  # noqa: F401 — import triggers model registration
    Base.metadata.create_all(bind=engine)


def check_db_connection() -> bool:
    """Ping the database. Used by the /health endpoint."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
