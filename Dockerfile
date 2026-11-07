# =============================================================================
# MeetingMind Backend — Dockerfile
# =============================================================================
# Multi-stage build keeps the final image lean.
# Stage 1: install dependencies
# Stage 2: copy app + run

FROM python:3.11-slim AS base

# Prevents Python from writing .pyc files and buffers stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies required by psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Dependencies layer (cached unless requirements.txt changes)
# ---------------------------------------------------------------------------
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# Application layer
# ---------------------------------------------------------------------------
COPY backend/ ./backend/

# Non-root user for security
RUN adduser --disabled-password --gecos "" appuser \
    && chown -R appuser:appuser /app
USER appuser

# Expose the port Uvicorn will listen on
EXPOSE 8000

# Start the application
# - workers=1 for Render free tier (single CPU)
# - host=0.0.0.0 to accept external connections inside Docker
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
