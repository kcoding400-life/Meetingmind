"""
HTTP client layer for the MeetingMind backend.
"""

import os
import json
from typing import Any, Optional, Tuple
import requests

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
TIMEOUT = 15
UPLOAD_TIMEOUT = 60


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _handle(response: requests.Response) -> Tuple[Optional[Any], Optional[str]]:
    """Parse response into (data, error). Never raises."""
    try:
        body = response.json()
    except Exception:
        body = {}

    if response.ok:
        return body, None

    # Extract the most useful error message
    if isinstance(body, dict):
        detail = body.get("detail", "")
        if isinstance(detail, list):  # Pydantic validation errors
            msgs = [e.get("msg", str(e)) for e in detail]
            return None, " | ".join(msgs)
        return None, str(detail) or f"HTTP {response.status_code}"

    return None, f"HTTP {response.status_code}"


# Auth

def register(email: str, full_name: str, password: str) -> Tuple[Optional[dict], Optional[str]]:
    try:
        r = requests.post(
            f"{API_BASE}/auth/register",
            json={"email": email, "full_name": full_name, "password": password},
            timeout=TIMEOUT,
        )
        return _handle(r)
    except requests.exceptions.ConnectionError:
        return None, "Cannot connect to API. Is the backend running?"
    except Exception as e:
        return None, str(e)


def login(email: str, password: str) -> Tuple[Optional[dict], Optional[str]]:
    try:
        r = requests.post(
            f"{API_BASE}/auth/login",
            json={"email": email, "password": password},
            timeout=TIMEOUT,
        )
        return _handle(r)
    except requests.exceptions.ConnectionError:
        return None, "Cannot connect to API. Is the backend running?"
    except Exception as e:
        return None, str(e)


def get_me(token: str) -> Tuple[Optional[dict], Optional[str]]:
    try:
        r = requests.get(f"{API_BASE}/auth/me", headers=_headers(token), timeout=TIMEOUT)
        return _handle(r)
    except Exception as e:
        return None, str(e)


# Meetings

def upload_meeting(
    token: str, title: str, description: str, file_bytes: bytes, filename: str, content_type: str
) -> Tuple[Optional[dict], Optional[str]]:
    try:
        r = requests.post(
            f"{API_BASE}/meetings/upload",
            headers=_headers(token),
            data={"title": title, "description": description},
            files={"file": (filename, file_bytes, content_type)},
            timeout=UPLOAD_TIMEOUT,
        )
        return _handle(r)
    except requests.exceptions.ConnectionError:
        return None, "Cannot connect to API."
    except Exception as e:
        return None, str(e)


def list_meetings(token: str, limit: int = 100) -> Tuple[Optional[dict], Optional[str]]:
    try:
        r = requests.get(
            f"{API_BASE}/meetings",
            headers=_headers(token),
            params={"limit": limit},
            timeout=TIMEOUT,
        )
        return _handle(r)
    except Exception as e:
        return None, str(e)


def get_meeting(token: str, meeting_id: str) -> Tuple[Optional[dict], Optional[str]]:
    try:
        r = requests.get(
            f"{API_BASE}/meetings/{meeting_id}",
            headers=_headers(token),
            timeout=TIMEOUT,
        )
        return _handle(r)
    except Exception as e:
        return None, str(e)


def delete_meeting(token: str, meeting_id: str) -> Tuple[Optional[dict], Optional[str]]:
    try:
        r = requests.delete(
            f"{API_BASE}/meetings/{meeting_id}",
            headers=_headers(token),
            timeout=TIMEOUT,
        )
        return _handle(r)
    except Exception as e:
        return None, str(e)


# Jobs

def get_job_status(token: str, job_id: str) -> Tuple[Optional[dict], Optional[str]]:
    try:
        r = requests.get(
            f"{API_BASE}/jobs/{job_id}",
            headers=_headers(token),
            timeout=TIMEOUT,
        )
        return _handle(r)
    except Exception as e:
        return None, str(e)


# Q&A

def ask_question(token: str, meeting_id: str, question: str) -> Tuple[Optional[dict], Optional[str]]:
    try:
        r = requests.post(
            f"{API_BASE}/meetings/{meeting_id}/ask",
            headers=_headers(token),
            json={"question": question},
            timeout=30,
        )
        return _handle(r)
    except Exception as e:
        return None, str(e)

# Health

def health_check() -> Tuple[Optional[dict], Optional[str]]:
    base = API_BASE.replace("/api/v1", "")
    try:
        r = requests.get(f"{base}/health", timeout=5)
        return _handle(r)
    except Exception as e:
        return None, str(e)


# Helpers used by pages

def parse_json_field(value: Optional[str]) -> list:
    """Safely parse a JSON string field from a meeting record."""
    if not value:
        return []
    try:
        result = json.loads(value)
        return result if isinstance(result, list) else []
    except Exception:
        return []


def format_duration(seconds: Optional[float]) -> str:
    """Format seconds into human-readable duration."""
    if not seconds:
        return "Unknown"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    secs = seconds % 60
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins}m"


def format_file_size(size_bytes: Optional[int]) -> str:
    """Format bytes into human-readable file size."""
    if not size_bytes:
        return "Unknown"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def status_color(status: str) -> str:
    """Return a CSS color for a meeting/job status."""
    return {
        "completed": "#22c55e",
        "processing": "#f59e0b",
        "pending": "#6366f1",
        "queued": "#6366f1",
        "failed": "#ef4444",
    }.get(status, "#94a3b8")


def priority_color(priority: str) -> str:
    """Return a CSS color for an action item priority."""
    return {
        "High": "#ef4444",
        "Medium": "#f59e0b",
        "Low": "#22c55e",
    }.get(priority, "#94a3b8")
