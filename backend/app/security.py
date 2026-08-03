"""Băm mật khẩu và phiên đăng nhập.

Đây là cơ chế demo: token phiên nằm trong RAM và mất khi backend khởi động lại.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets

from fastapi import Depends, Header, HTTPException

SIMULATOR_API_KEY = os.getenv("SIMULATOR_API_KEY", "demo-sim-key")

SESSIONS: dict[str, dict[str, str]] = {}


def make_password(password: str) -> str:
  salt = secrets.token_bytes(16)
  digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
  return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
  salt_hex, digest_hex = stored.split("$", 1)
  digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 200_000)
  return hmac.compare_digest(digest.hex(), digest_hex)


def create_session(username: str, display_name: str, role: str) -> str:
  token = secrets.token_urlsafe(32)
  SESSIONS[token] = {"username": username, "display_name": display_name, "role": role}
  return token


def current_user(authorization: str | None = Header(default=None)) -> dict[str, str]:
  if not authorization or not authorization.startswith("Bearer "):
    raise HTTPException(status_code=401, detail="Thiếu access token")
  session = SESSIONS.get(authorization[7:])
  if not session:
    raise HTTPException(status_code=401, detail="Phiên đăng nhập không hợp lệ")
  return session


def require_role(role: str):
  def dependency(user: dict[str, str] = Depends(current_user)) -> dict[str, str]:
    if user["role"] != role:
      raise HTTPException(status_code=403, detail="Không đủ quyền")
    return user
  return dependency


def simulator_auth(x_api_key: str | None = Header(default=None)) -> None:
  if x_api_key != SIMULATOR_API_KEY:
    raise HTTPException(status_code=401, detail="Simulator API key không hợp lệ")
