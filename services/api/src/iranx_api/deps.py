from __future__ import annotations

import uuid

from fastapi import Cookie, Depends, HTTPException, status

from .jwt_util import COOKIE_NAME, decode_user_id


def current_user_id(access_token: str | None = Cookie(default=None, alias=COOKIE_NAME)) -> uuid.UUID:
    if not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in")
    uid = decode_user_id(access_token)
    if uid is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    return uid

