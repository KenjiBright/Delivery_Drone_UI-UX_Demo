from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from ..db import connect, get_settings
from ..security import current_user

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/products")
def products(
  q: str = Query(default=""),
  category: str = Query(default=""),
  user: dict[str, str] = Depends(current_user),
) -> list[dict[str, Any]]:
  """Danh sách sản phẩm đang bán, có thể lọc theo từ khoá và danh mục."""
  sql = "SELECT * FROM products WHERE active = 1"
  params: list[Any] = []
  if q:
    sql += " AND (LOWER(name) LIKE ? OR LOWER(description) LIKE ?)"
    needle = f"%{q.lower()}%"
    params += [needle, needle]
  if category:
    sql += " AND category = ?"
    params.append(category)
  sql += " ORDER BY category, name"
  with connect() as conn:
    rows = conn.execute(sql, params).fetchall()
  return [dict(row) for row in rows]


@router.get("/categories")
def categories(user: dict[str, str] = Depends(current_user)) -> list[str]:
  with connect() as conn:
    rows = conn.execute("SELECT DISTINCT category FROM products WHERE active = 1 ORDER BY category").fetchall()
  return [row["category"] for row in rows]


@router.get("/config")
def config(user: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
  """Thông số vận hành mà giao diện cần biết (điểm xuất phát, tải trọng tối đa)."""
  with connect() as conn:
    settings = get_settings(conn)
  return {
    "home_lat": float(settings.get("home_lat", 21.0278)),
    "home_lon": float(settings.get("home_lon", 105.8342)),
    "max_payload_kg": float(settings.get("max_payload_kg", 2.5)),
    "service_name": settings.get("service_name", "UAV Delivery"),
  }
