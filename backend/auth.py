"""
Authentication utilities:

1. Password hashing (bcrypt via passlib)
2. JWT creation and verification (python-jose)
3. FastAPI dependency that extracts the current user from the Bearer token

The dependency `get_current_user` is the only entry point for protected
routes — inject it with Depends() and you get a fully validated User ORM
object back.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User


# Password hashing

# bcrypt is intentionally slow (work factor) — that's the point.
# deprecated="auto" silently upgrades old hashes on next login.

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

bearer_scheme = HTTPBearer()


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)



# JWT


def create_access_token(user_id: str, email: str) -> tuple[str, int]:
    """
    Returns (token_string, expires_in_seconds).
    Payload follows JWT best practices:
      sub  = subject (user id)
      email = convenience claim (avoids a DB lookup in simple cases)
      exp  = expiration (handled by python-jose on decode)
      iat  = issued at
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "email": email,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    expires_in = settings.JWT_EXPIRE_MINUTES * 60
    return token, expires_in


def decode_token(token: str) -> Optional[dict]:
    """
    Decode and validate a JWT. Returns the payload dict or None if invalid.
    python-jose raises JWTError for expired/malformed tokens.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError:
        return None



# FastAPI dependency


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Extract and validate the Bearer token, then return the matching User.
    Raises 401 for any authentication failure — never leaks the reason.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_token(credentials.credentials)
    if payload is None:
        raise credentials_exception

    user_id: str = payload.get("sub")
    if not user_id:
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise credentials_exception

    return user
