"""Băm mật khẩu và phiên đăng nhập.

Đây là cơ chế demo: token phiên nằm trong RAM và mất khi backend khởi động lại.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, Header, HTTPException

SIMULATOR_API_KEY = os.getenv("SIMULATOR_API_KEY", "demo-sim-key")

SESSIONS: dict[str, dict[str, Any]] = {}


def make_password(password: str) -> str:
  salt = secrets.token_bytes(16)
  digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
  return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
  salt_hex, digest_hex = stored.split("$", 1)
  digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 200_000)
  return hmac.compare_digest(digest.hex(), digest_hex)


def describe_device(user_agent: str) -> str:
  """Rút gọn User-Agent thành thứ người dùng nhận ra được trong danh sách thiết bị."""
  agent = user_agent or ""
  if "Android" in agent:
    platform = "Android"
  elif "iPhone" in agent or "iPad" in agent:
    platform = "iPhone / iPad"
  elif "Windows" in agent:
    platform = "Windows"
  elif "Mac OS" in agent or "Macintosh" in agent:
    platform = "macOS"
  elif "Linux" in agent:
    platform = "Linux"
  else:
    platform = "Thiết bị khác"

  # Thứ tự quan trọng: Edge và Chrome đều tự nhận là Chrome trong User-Agent.
  for marker, name in (("Edg/", "Edge"), ("OPR/", "Opera"), ("Chrome/", "Chrome"), ("Firefox/", "Firefox"), ("Safari/", "Safari")):
    if marker in agent:
      return f"{name} trên {platform}"
  return platform


def create_session(username: str, display_name: str, role: str, user_agent: str = "") -> str:
  token = secrets.token_urlsafe(32)
  SESSIONS[token] = {
    "username": username,
    "display_name": display_name,
    "role": role,
    # Mã ngắn để hiển thị và thu hồi phiên mà không phải lộ token ra ngoài.
    "session_id": secrets.token_hex(8),
    "device": describe_device(user_agent),
    "created_at": datetime.now(timezone.utc).isoformat(),
  }
  return token


def sessions_of(username: str) -> list[dict[str, Any]]:
  return [
    {"session_id": data["session_id"], "device": data["device"], "created_at": data["created_at"]}
    for data in SESSIONS.values() if data["username"] == username
  ]


def revoke_session(username: str, session_id: str, keep_token: str | None = None) -> bool:
  for token, data in list(SESSIONS.items()):
    if data["username"] == username and data["session_id"] == session_id and token != keep_token:
      del SESSIONS[token]
      return True
  return False


def revoke_other_sessions(username: str, keep_token: str) -> int:
  removed = 0
  for token, data in list(SESSIONS.items()):
    if data["username"] == username and token != keep_token:
      del SESSIONS[token]
      removed += 1
  return removed


def bearer_token(authorization: str | None) -> str:
  return authorization[7:] if authorization and authorization.startswith("Bearer ") else ""


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
