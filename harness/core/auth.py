"""
Core Authentication and Authorization logic.
Handles password hashing, JWT encoding/decoding, and user management.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, UTC
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from harness.data.models import UserDB


# ── Password Hashing ──────────────────────────────────────────────────────────


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return f"pbkdf2_sha256$100000${salt.hex()}${key.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    try:
        parts = hashed.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        key = bytes.fromhex(parts[3])
        new_key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
        return hmac.compare_digest(key, new_key)
    except Exception:
        return False


# ── JWT (HS256) implementation ────────────────────────────────────────────────


def base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def base64url_decode(data: str) -> bytes:
    padding = "=" * (4 - (len(data) % 4))
    return base64.urlsafe_b64decode(data + padding)


def create_jwt(payload: dict[str, Any], secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = base64url_encode(json.dumps(header).encode("utf-8"))
    payload_b64 = base64url_encode(json.dumps(payload).encode("utf-8"))
    
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    signature_b64 = base64url_encode(signature)
    
    return f"{header_b64}.{payload_b64}.{signature_b64}"


def verify_jwt(token: str, secret: str) -> dict[str, Any] | None:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, signature_b64 = parts
        
        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
        expected_signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        expected_signature_b64 = base64url_encode(expected_signature)
        
        if not hmac.compare_digest(signature_b64, expected_signature_b64):
            return None
            
        payload = json.loads(base64url_decode(payload_b64).decode("utf-8"))
        if "exp" in payload and payload["exp"] < time.time():
            return None
            
        return payload
    except Exception:
        return None


# ── Schemas ───────────────────────────────────────────────────────────────────


class User(BaseModel):
    id: str
    username: str
    role: str
    is_active: bool = True
    created_at: datetime

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "user"


class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: str
    role: str


# ── Auth Manager ──────────────────────────────────────────────────────────────


class AuthManager:
    def __init__(self, secret_key: str) -> None:
        self.secret_key = secret_key
        self._revoked_tokens: set[str] = set()

    def verify_token(self, token: str) -> TokenData | None:
        if token in self._revoked_tokens:
            return None
        payload = verify_jwt(token, self.secret_key)
        if not payload:
            return None
        
        user_id = payload.get("sub")
        role = payload.get("role", "user")
        if not user_id:
            return None
            
        return TokenData(user_id=user_id, role=role)

    def create_token(self, user: UserDB, expires_delta_seconds: int = 86400) -> Token:
        payload = {
            "sub": user.id,
            "role": user.role,
            "exp": time.time() + expires_delta_seconds
        }
        token_str = create_jwt(payload, self.secret_key)
        return Token(access_token=token_str)

    def revoke_token(self, token: str) -> None:
        self._revoked_tokens.add(token)

    async def create_user(self, db: AsyncSession, user_create: UserCreate) -> UserDB:
        # Check if username exists
        stmt = select(UserDB).where(UserDB.username == user_create.username)
        res = await db.execute(stmt)
        if res.scalar_one_or_none():
            raise ValueError("Username already registered")

        pw_hash = hash_password(user_create.password)
        user = UserDB(
            username=user_create.username,
            password_hash=pw_hash,
            role=user_create.role,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    async def authenticate(self, db: AsyncSession, login: UserLogin) -> UserDB | None:
        stmt = select(UserDB).where(UserDB.username == login.username)
        res = await db.execute(stmt)
        user = res.scalar_one_or_none()
        if not user or not user.is_active:
            return None
        if verify_password(login.password, user.password_hash):
            return user
        return None

    async def get_user(self, db: AsyncSession, user_id: str) -> UserDB | None:
        return await db.get(UserDB, user_id)

    async def list_users(self, db: AsyncSession) -> list[UserDB]:
        stmt = select(UserDB).order_by(UserDB.created_at.desc())
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def update_user_role(self, db: AsyncSession, user_id: str, role: str) -> UserDB | None:
        user = await db.get(UserDB, user_id)
        if not user:
            return None
        user.role = role
        await db.commit()
        await db.refresh(user)
        return user

    async def deactivate_user(self, db: AsyncSession, user_id: str) -> UserDB | None:
        user = await db.get(UserDB, user_id)
        if not user:
            return None
        user.is_active = False
        await db.commit()
        await db.refresh(user)
        return user


# Singleton instance manager
_auth_manager: AuthManager | None = None


def get_auth_manager() -> AuthManager:
    global _auth_manager
    if _auth_manager is None:
        from os import getenv
        secret = getenv("JWT_SECRET", "vloop-super-secret-key-change-in-production")
        _auth_manager = AuthManager(secret)
    return _auth_manager
