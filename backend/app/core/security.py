from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import get_db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)

# ── Hardcoded team credentials ────────────────────────────────────────────────
# In production use a proper user table — for this project, fixed credentials are fine
TEAM_USERS = {
    "taahira": {
        "username": "taahira",
        "hashed_password": pwd_context.hash("backend2024"),
        "role": "admin",
    },
    "likhita": {
        "username": "likhita",
        "hashed_password": pwd_context.hash("cv2024"),
        "role": "writer",   # Can POST behavior data
    },
    "yashwanth": {
        "username": "yashwanth",
        "hashed_password": pwd_context.hash("hardware2024"),
        "role": "writer",   # Can POST sensor data
    },
    "viewer": {
        "username": "viewer",
        "hashed_password": pwd_context.hash("view2024"),
        "role": "reader",   # Read-only dashboard access
    },
}


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def authenticate_user(username: str, password: str) -> Optional[dict]:
    user = TEAM_USERS.get(username)
    if not user:
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return user


def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """
    Dependency — validates Bearer token from Authorization header.
    Use as: current_user = Depends(get_current_user)
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token. Please login again.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not credentials:
        raise credentials_exception
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = TEAM_USERS.get(username)
    if user is None:
        raise credentials_exception
    return user


async def require_writer(current_user: dict = Depends(get_current_user)) -> dict:
    """Only admin and writer roles can POST data."""
    if current_user["role"] not in ("admin", "writer"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access required."
        )
    return current_user


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Only admin role can do destructive operations."""
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required."
        )
    return current_user