from __future__ import annotations

import os
import re
import uuid

import bcrypt
import psycopg
from psycopg import errors as pg_errors
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field

from .deps import current_user_id
from .jwt_util import COOKIE_NAME, create_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _hash_password(password: str) -> str:
    pw = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("ascii")


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("ascii"))
    except ValueError:
        return False


def _conn() -> psycopg.Connection:
    return psycopg.connect(os.environ["DATABASE_URL"])


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


def _set_auth_cookie(response: Response, user_id: uuid.UUID) -> None:
    token = create_token(user_id=user_id)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
        secure=os.environ.get("COOKIE_SECURE", "false").lower() in {"1", "true", "yes"},
        path="/",
    )


@router.post("/register")
def register(body: RegisterIn, response: Response) -> dict:
    email = body.email.lower().strip()
    if not re.fullmatch(r"[^@]+@[^@]+\.[^@]+", email):
        raise HTTPException(status_code=400, detail="Invalid email")

    pw_hash = _hash_password(body.password)
    with _conn() as c, c.cursor() as cur:
        try:
            cur.execute(
                "INSERT INTO users (email, password_hash) VALUES (%(e)s, %(p)s) RETURNING id",
                {"e": email, "p": pw_hash},
            )
            row = cur.fetchone()
        except pg_errors.UniqueViolation:
            raise HTTPException(status_code=409, detail="Email already registered") from None
    uid = row[0]
    _set_auth_cookie(response, uid)
    return {"id": str(uid), "email": email}


@router.post("/login")
def login(body: LoginIn, response: Response) -> dict:
    email = body.email.lower().strip()
    with _conn() as c, c.cursor() as cur:
        cur.execute("SELECT id, password_hash FROM users WHERE email=%(e)s", {"e": email})
        row = cur.fetchone()
    if not row or not _verify_password(body.password, row[1]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    uid = row[0]
    _set_auth_cookie(response, uid)
    return {"id": str(uid), "email": email}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(user_id: uuid.UUID = Depends(current_user_id)) -> dict:
    with _conn() as c, c.cursor() as cur:
        cur.execute("SELECT email, created_at FROM users WHERE id=%(id)s", {"id": user_id})
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="User not found")
    return {"id": str(user_id), "email": row[0], "created_at": row[1].isoformat()}
