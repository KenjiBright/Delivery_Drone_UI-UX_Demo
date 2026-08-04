from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from ..db import connect
from ..models import LoginRequest
from ..security import create_session, current_user, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Những trường giao diện cần ngay sau khi đăng nhập. Hồ sơ đầy đủ nằm ở /api/profile.
SESSION_FIELDS = ("username", "display_name", "full_name", "role", "phone", "email", "duty_status")


def public_user(row) -> dict[str, Any]:
  data = dict(row)
  return {key: data.get(key) for key in SESSION_FIELDS}


@router.post("/login")
def login(request: LoginRequest, user_agent: str | None = Header(default=None)) -> dict[str, Any]:
  with connect() as conn:
    row = conn.execute("SELECT * FROM users WHERE username = ?", (request.username,)).fetchone()
  if not row or not verify_password(request.password, row["password_hash"]):
    raise HTTPException(status_code=401, detail="Sai tên đăng nhập hoặc mật khẩu")
  if request.expected_role and row["role"] != request.expected_role:
    raise HTTPException(status_code=403, detail="Tài khoản không đúng vai trò")
  token = create_session(row["username"], row["display_name"], row["role"], user_agent or "")
  return {"access_token": token, "user": public_user(row)}


@router.get("/me")
def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
  """Đọc lại từ CSDL chứ không trả thẳng phiên đăng nhập.

  Phiên chỉ giữ vài trường tối thiểu; sửa hồ sơ xong mà đọc từ phiên thì giao diện
  vẫn hiện thông tin cũ cho tới lần đăng nhập sau.
  """
  with connect() as conn:
    row = conn.execute("SELECT * FROM users WHERE username = ?", (user["username"],)).fetchone()
  if not row:
    raise HTTPException(status_code=401, detail="Tài khoản không còn tồn tại")
  return public_user(row)
