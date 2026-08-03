from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..db import connect
from ..models import LoginRequest
from ..security import create_session, current_user, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(request: LoginRequest) -> dict[str, Any]:
  with connect() as conn:
    row = conn.execute("SELECT * FROM users WHERE username = ?", (request.username,)).fetchone()
  if not row or not verify_password(request.password, row["password_hash"]):
    raise HTTPException(status_code=401, detail="Sai tên đăng nhập hoặc mật khẩu")
  if request.expected_role and row["role"] != request.expected_role:
    raise HTTPException(status_code=403, detail="Tài khoản không đúng vai trò")
  token = create_session(row["username"], row["display_name"], row["role"])
  user = {
    "username": row["username"],
    "display_name": row["display_name"],
    "role": row["role"],
    "phone": row["phone"],
  }
  return {"access_token": token, "user": user}


@router.get("/me")
def me(user: dict[str, str] = Depends(current_user)) -> dict[str, str]:
  return user
