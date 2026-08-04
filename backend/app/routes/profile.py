"""Hồ sơ tài khoản, đổi mật khẩu và quản lý thiết bị đăng nhập."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from ..db import connect, utc_now
from ..models import PasswordChange, ProfilePatch
from ..security import (
  SESSIONS, bearer_token, current_user, make_password, revoke_other_sessions,
  revoke_session, sessions_of, verify_password,
)

router = APIRouter(prefix="/api/profile", tags=["profile"])

# Không bao giờ trả mật khẩu băm ra ngoài.
HIDDEN_COLUMNS = {"password_hash"}

GENDERS = {"", "male", "female", "other"}
DUTY_STATUSES = {"ON_DUTY", "BREAK", "OFF_DUTY"}

# Mỗi vai trò chỉ sửa được phần hồ sơ của mình. Khách hàng không thể tự phong
# mã nhân viên cho bản thân, điều phối viên không có tuỳ chọn giao hàng.
COMMON_FIELDS = {"display_name", "full_name", "email", "phone", "gender", "date_of_birth"}
ROLE_FIELDS = {
  "operator": COMMON_FIELDS | {"employee_code", "job_title", "department", "duty_status"},
  "customer": COMMON_FIELDS | {"default_note", "default_address_id", "notify_orders"},
}


def read_profile(username: str) -> dict[str, Any]:
  with connect() as conn:
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
  if not row:
    raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")
  return {key: value for key, value in dict(row).items() if key not in HIDDEN_COLUMNS}


@router.get("")
def get_profile(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
  return read_profile(user["username"])


@router.patch("")
def patch_profile(
  request: ProfilePatch,
  user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
  allowed = ROLE_FIELDS.get(user["role"], COMMON_FIELDS)
  updates = {key: value for key, value in request.model_dump(exclude_none=True).items() if key in allowed}
  if not updates:
    raise HTTPException(status_code=400, detail="Không có thay đổi nào")

  if "gender" in updates and updates["gender"] not in GENDERS:
    raise HTTPException(status_code=400, detail="Giới tính không hợp lệ")
  if "duty_status" in updates and updates["duty_status"] not in DUTY_STATUSES:
    raise HTTPException(status_code=400, detail="Trạng thái trực không hợp lệ")
  if "notify_orders" in updates:
    updates["notify_orders"] = int(updates["notify_orders"])

  updates["updated_at"] = utc_now()
  assignments = ", ".join(f"{key} = ?" for key in updates)
  with connect() as conn:
    conn.execute(f"UPDATE users SET {assignments} WHERE username = ?", list(updates.values()) + [user["username"]])
    conn.commit()

  # Tên hiển thị nằm sẵn trong phiên đăng nhập nên phải cập nhật theo, nếu không
  # thanh trên vẫn hiện tên cũ tới khi đăng nhập lại.
  if "display_name" in updates:
    for session in SESSIONS.values():
      if session["username"] == user["username"]:
        session["display_name"] = updates["display_name"]

  return read_profile(user["username"])


@router.post("/password")
def change_password(
  request: PasswordChange,
  user: dict[str, Any] = Depends(current_user),
  authorization: str | None = Header(default=None),
) -> dict[str, Any]:
  with connect() as conn:
    row = conn.execute("SELECT password_hash FROM users WHERE username = ?", (user["username"],)).fetchone()
    if not row or not verify_password(request.current_password, row["password_hash"]):
      raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không đúng")
    if request.current_password == request.new_password:
      raise HTTPException(status_code=400, detail="Mật khẩu mới phải khác mật khẩu cũ")
    conn.execute(
      "UPDATE users SET password_hash = ?, updated_at = ? WHERE username = ?",
      (make_password(request.new_password), utc_now(), user["username"]),
    )
    conn.commit()

  # Đổi mật khẩu thì mọi thiết bị khác phải đăng nhập lại; giữ đúng phiên hiện tại.
  signed_out = revoke_other_sessions(user["username"], bearer_token(authorization))
  return {"ok": True, "signed_out_devices": signed_out}


@router.get("/sessions")
def list_sessions(
  user: dict[str, Any] = Depends(current_user),
  authorization: str | None = Header(default=None),
) -> list[dict[str, Any]]:
  current = SESSIONS.get(bearer_token(authorization), {}).get("session_id")
  return [
    {**session, "is_current": session["session_id"] == current}
    for session in sorted(sessions_of(user["username"]), key=lambda item: item["created_at"], reverse=True)
  ]


@router.delete("/sessions/{session_id}")
def delete_session(
  session_id: str,
  user: dict[str, Any] = Depends(current_user),
  authorization: str | None = Header(default=None),
) -> dict[str, bool]:
  # keep_token chặn việc tự đăng xuất chính mình bằng nút dành cho thiết bị khác.
  if not revoke_session(user["username"], session_id, keep_token=bearer_token(authorization)):
    raise HTTPException(status_code=404, detail="Không tìm thấy phiên đăng nhập này")
  return {"ok": True}
