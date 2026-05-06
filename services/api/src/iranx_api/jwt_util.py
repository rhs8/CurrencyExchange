from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

ALGO = "HS256"
COOKIE_NAME = "access_token"


def _secret() -> str:
    s = os.environ.get("JWT_SECRET", "").strip()
    if not s:
        raise RuntimeError("JWT_SECRET is required for auth")
    return s


def create_token(*, user_id: uuid.UUID, days: int = 30) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=days)).timestamp()),
    }
    return jwt.encode(payload, _secret(), algorithm=ALGO)


def decode_user_id(token: str) -> uuid.UUID | None:
    try:
        payload = jwt.decode(token, _secret(), algorithms=[ALGO])
        sub = payload.get("sub")
        if not sub:
            return None
        return uuid.UUID(str(sub))
    except (JWTError, ValueError):
        return None
