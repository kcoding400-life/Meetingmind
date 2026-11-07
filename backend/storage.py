"""
Supabase Storage integration for audio file management.
Design decisions:
- Files are stored at: {user_id}/{meeting_id}/{filename}
  → Namespaced by user, so there are no collisions and paths are auditable.
- We use the service_role key (bypasses RLS) because access control is
  enforced at the API layer via JWT, not at the storage layer.
- get_client() is called per-operation, not cached — the supabase client
  is lightweight and this avoids stale connection state.
- Public URLs are returned for file access; Supabase Storage handles
  the CDN and signing if the bucket is private.
"""

import io
from typing import Optional

from supabase import create_client, Client
from fastapi import UploadFile

from .config import settings


def get_client() -> Client:
    """Create a fresh Supabase client. Cheap — just constructs a wrapper."""
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set to use storage"
        )
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)


def build_storage_path(user_id: str, meeting_id: str, filename: str) -> str:
    """
    Deterministic storage path for a meeting audio file.
    Format: {user_id}/{meeting_id}/{original_filename}
    """
    # Sanitise filename: remove path traversal characters
    safe_name = filename.replace("/", "_").replace("..", "_")
    return f"{user_id}/{meeting_id}/{safe_name}"


def upload_audio(
    user_id: str,
    meeting_id: str,
    file: UploadFile,
    file_bytes: bytes,
) -> dict:
    """
    Upload audio bytes to Supabase Storage.

    Returns a dict with:
      - storage_path: the path within the bucket
      - public_url: accessible URL (if bucket is public)
      - file_size: bytes uploaded

    Raises RuntimeError on upload failure.
    """
    client = get_client()
    path = build_storage_path(user_id, meeting_id, file.filename)

    # Determine content type — default to audio/mpeg for unknown audio files
    content_type = file.content_type or _infer_content_type(file.filename)

    response = client.storage.from_(settings.SUPABASE_BUCKET).upload(
        path=path,
        file=file_bytes,
        file_options={"content-type": content_type, "upsert": "true"},
    )

    # supabase-py raises an exception on failure, but check just in case
    if hasattr(response, "error") and response.error:
        raise RuntimeError(f"Storage upload failed: {response.error}")

    # Build the public URL
    public_url_response = (
        client.storage.from_(settings.SUPABASE_BUCKET).get_public_url(path)
    )

    return {
        "storage_path": path,
        "public_url": public_url_response,
        "file_size": len(file_bytes),
    }


def download_audio(storage_path: str) -> bytes:
    """
    Download audio bytes from Supabase Storage.
    Used by the AI processing pipeline in Phase 3.

    Raises RuntimeError if the file cannot be retrieved.
    """
    client = get_client()

    response = client.storage.from_(settings.SUPABASE_BUCKET).download(storage_path)

    if isinstance(response, (bytes, bytearray)):
        return bytes(response)

    raise RuntimeError(f"Unexpected storage download response type: {type(response)}")


def delete_audio(storage_path: str) -> bool:
    """
    Delete an audio file from Supabase Storage.
    Returns True on success, False if the file didn't exist or on error.
    """
    try:
        client = get_client()
        client.storage.from_(settings.SUPABASE_BUCKET).remove([storage_path])
        return True
    except Exception:
        return False


def get_signed_url(storage_path: str, expires_in: int = 3600) -> Optional[str]:
    """
    Generate a time-limited signed URL for private bucket access.
    expires_in: seconds until the URL expires (default 1 hour).
    """
    try:
        client = get_client()
        response = client.storage.from_(settings.SUPABASE_BUCKET).create_signed_url(
            path=storage_path, expires_in=expires_in
        )
        if isinstance(response, dict):
            return response.get("signedURL") or response.get("signedUrl")
        return None
    except Exception:
        return None


def ensure_bucket_exists() -> bool:
    """
    Create the storage bucket if it doesn't exist.
    Called once on startup. Safe to call repeatedly.
    """
    try:
        client = get_client()
        buckets = client.storage.list_buckets()
        bucket_names = [b.name for b in buckets]

        if settings.SUPABASE_BUCKET not in bucket_names:
            client.storage.create_bucket(
                settings.SUPABASE_BUCKET,
                options={"public": True, "file_size_limit": "524288000"},  # 500MB
            )
        return True
    except Exception:
        return False



# Helpers


def _infer_content_type(filename: str) -> str:
    """Infer MIME type from file extension for common audio formats."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    types = {
        "mp3": "audio/mpeg",
        "mp4": "video/mp4",
        "m4a": "audio/mp4",
        "wav": "audio/wav",
        "webm": "audio/webm",
        "ogg": "audio/ogg",
        "flac": "audio/flac",
        "opus": "audio/opus",
    }
    return types.get(ext, "application/octet-stream")


# Allowed audio/video extensions for upload validation
ALLOWED_EXTENSIONS = {
    ".mp3", ".mp4", ".m4a", ".wav", ".webm",
    ".ogg", ".flac", ".opus", ".mpeg", ".mpga"
}


def validate_audio_file(filename: str, size_bytes: int) -> Optional[str]:
    """
    Validate file extension and size.
    Returns an error message string, or None if valid.
    """
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        return (
            f"File type '{ext}' is not supported. "
            f"Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if size_bytes > max_bytes:
        return f"File exceeds maximum size of {settings.MAX_UPLOAD_SIZE_MB}MB"
    return None
