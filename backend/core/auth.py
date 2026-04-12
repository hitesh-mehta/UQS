"""
JWT Authentication for UQS.
Handles token creation, verification, and FastAPI dependency injection.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from backend.config import settings

security = HTTPBearer()


# ── Data Models ───────────────────────────────────────────────────────────────

class TokenPayload(BaseModel):
    sub: str               # user_id
    role: str              # e.g. admin | analyst | regional_manager
    email: str
    exp: datetime


class UserContext(BaseModel):
    user_id: str
    role: str
    email: str


# ── Token Operations ──────────────────────────────────────────────────────────

def create_access_token(
    user_id: str,
    role: str,
    email: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token carrying user identity + role."""
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload: dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "email": email,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenPayload:
    """Decode and validate a JWT. Raises HTTPException on failure."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        user_id: str = payload.get("sub")
        role: str = payload.get("role")
        email: str = payload.get("email", "")
        if user_id is None or role is None:
            raise credentials_exception
        exp = payload.get("exp")
        return TokenPayload(
            sub=user_id,
            role=role,
            email=email,
            exp=datetime.fromtimestamp(exp, tz=timezone.utc),
        )
    except JWTError:
        raise credentials_exception


# ── FastAPI Dependency ────────────────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserContext:
    """FastAPI dependency — extracts and validates the bearer token."""
    token_data = decode_access_token(credentials.credentials)
    return UserContext(
        user_id=token_data.sub,
        role=token_data.role,
        email=token_data.email,
    )


async def require_admin(user: UserContext = Depends(get_current_user)) -> UserContext:
    """FastAPI dependency — ensures the caller is an admin."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required for this operation.",
        )
    return user
