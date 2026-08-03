from __future__ import annotations

import json
import secrets
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from ..db import DB_LOCK, connect, get_settings, log_event, new_order_id, row_to_order, utc_now
from ..models import AddressRequest, CreateOrderRequest, RateRequest, VerifyRequest
from ..realtime import manager
from ..security import current_user, require_role

router = APIRouter(prefix="/api", tags=["orders"])

ACTIVE_STATUSES = ("PENDING", "CONFIRMED", "ASSIGNED", "DISPATCHED", "IN_FLIGHT", "ARRIVED", "DELIVERED", "RETURNING")


@router.post("/orders")
async def create_order(
  request: CreateOrderRequest,
  user: dict[str, str] = Depends(require_role("customer")),
) -> dict[str, Any]:
  if not request.items:
    raise HTTPException(status_code=400, detail="Giỏ hàng đang trống")

  async with DB_LOCK:
    with connect() as conn:
      max_payload = float(get_settings(conn).get("max_payload_kg", 2.5))
      product_ids = [item.product_id for item in request.items]
      placeholders = ",".join("?" for _ in product_ids)
      rows = conn.execute(f"SELECT * FROM products WHERE id IN ({placeholders}) AND active = 1", product_ids).fetchall()
      product_map = {row["id"]: row for row in rows}

      items: list[dict[str, Any]] = []
      total_price = 0
      total_weight = 0.0
      for requested in request.items:
        product = product_map.get(requested.product_id)
        if not product:
          raise HTTPException(status_code=400, detail=f"Sản phẩm {requested.product_id} không còn bán")
        line_price = product["price"] * requested.quantity
        line_weight = product["weight_kg"] * requested.quantity
        total_price += line_price
        total_weight += line_weight
        items.append({
          "product_id": product["id"],
          "name": product["name"],
          "icon": product["icon"],
          "quantity": requested.quantity,
          "unit_price": product["price"],
          "unit_weight_kg": product["weight_kg"],
          "line_price": line_price,
          "line_weight_kg": round(line_weight, 3),
        })

      if total_weight > max_payload:
        raise HTTPException(status_code=400, detail=f"Tổng khối lượng vượt tải trọng {max_payload} kg")

      order_id = new_order_id()
      now = utc_now()
      conn.execute(
        """INSERT INTO orders
        (id, customer_username, items_json, total_price, total_weight_kg, delivery_lat, delivery_lon,
         delivery_address, note, status, assigned_uav, verification_code, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', NULL, ?, ?, ?)""",
        (
          order_id, user["username"], json.dumps(items, ensure_ascii=False), total_price, round(total_weight, 3),
          request.delivery_lat, request.delivery_lon, request.delivery_address, request.note,
          f"{secrets.randbelow(9000) + 1000}", now, now,
        ),
      )
      log_event(conn, order_id, "PENDING", user["username"], "Khách hàng đặt đơn")
      conn.commit()
      order = row_to_order(conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone())

  await manager.broadcast({"type": "order_created", "order": order}, user["username"])
  return order


@router.get("/orders/mine")
def my_orders(
  status: str = Query(default=""),
  scope: str = Query(default="", description="active | history"),
  user: dict[str, str] = Depends(require_role("customer")),
) -> list[dict[str, Any]]:
  sql = "SELECT * FROM orders WHERE customer_username = ?"
  params: list[Any] = [user["username"]]
  if status:
    sql += " AND status = ?"
    params.append(status)
  elif scope == "active":
    sql += f" AND status IN ({','.join('?' for _ in ACTIVE_STATUSES)})"
    params += list(ACTIVE_STATUSES)
  elif scope == "history":
    sql += " AND status IN ('COMPLETED', 'CANCELLED')"
  sql += " ORDER BY created_at DESC"
  with connect() as conn:
    rows = conn.execute(sql, params).fetchall()
  return [row_to_order(row) for row in rows]


@router.get("/orders/{order_id}")
def get_order(order_id: str, user: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
  with connect() as conn:
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not row:
      raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")
    if user["role"] == "customer" and row["customer_username"] != user["username"]:
      raise HTTPException(status_code=403, detail="Không được xem đơn hàng này")
    events = conn.execute(
      "SELECT status, actor, note, created_at FROM order_events WHERE order_id = ? ORDER BY id", (order_id,)
    ).fetchall()
  order = row_to_order(row)
  order["events"] = [dict(event) for event in events]
  return order


@router.post("/orders/{order_id}/verify")
async def verify_delivery(
  order_id: str,
  request: VerifyRequest,
  user: dict[str, str] = Depends(require_role("customer")),
) -> dict[str, Any]:
  async with DB_LOCK:
    with connect() as conn:
      row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
      if not row or row["customer_username"] != user["username"]:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")
      if row["status"] != "ARRIVED":
        raise HTTPException(status_code=400, detail="UAV chưa đến điểm giao")
      if request.code.strip() != row["verification_code"]:
        raise HTTPException(status_code=400, detail="Mã PIN không đúng")
      conn.execute("UPDATE orders SET status = 'DELIVERED', updated_at = ? WHERE id = ?", (utc_now(), order_id))
      log_event(conn, order_id, "DELIVERED", user["username"], "Khách xác nhận đã nhận hàng")
      conn.commit()
      order = row_to_order(conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone())

  await manager.broadcast({"type": "order_updated", "order": order}, user["username"])
  return order


@router.post("/orders/{order_id}/rate")
async def rate_order(
  order_id: str,
  request: RateRequest,
  user: dict[str, str] = Depends(require_role("customer")),
) -> dict[str, Any]:
  async with DB_LOCK:
    with connect() as conn:
      row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
      if not row or row["customer_username"] != user["username"]:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")
      if row["status"] != "COMPLETED":
        raise HTTPException(status_code=400, detail="Chỉ đánh giá được đơn đã hoàn thành")
      conn.execute(
        "UPDATE orders SET rating = ?, review = ?, updated_at = ? WHERE id = ?",
        (request.rating, request.review, utc_now(), order_id),
      )
      conn.commit()
      order = row_to_order(conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone())

  await manager.broadcast({"type": "order_rated", "order": order}, user["username"])
  return order


# ---------- Sổ địa chỉ ----------

@router.get("/addresses")
def list_addresses(user: dict[str, str] = Depends(require_role("customer"))) -> list[dict[str, Any]]:
  with connect() as conn:
    rows = conn.execute("SELECT * FROM addresses WHERE username = ? ORDER BY id DESC", (user["username"],)).fetchall()
  return [dict(row) for row in rows]


@router.post("/addresses")
def create_address(
  request: AddressRequest,
  user: dict[str, str] = Depends(require_role("customer")),
) -> dict[str, Any]:
  with connect() as conn:
    cursor = conn.execute(
      "INSERT INTO addresses (username, label, address, lat, lon, created_at) VALUES (?, ?, ?, ?, ?, ?)",
      (user["username"], request.label, request.address, request.lat, request.lon, utc_now()),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM addresses WHERE id = ?", (cursor.lastrowid,)).fetchone()
  return dict(row)


@router.delete("/addresses/{address_id}")
def delete_address(address_id: int, user: dict[str, str] = Depends(require_role("customer"))) -> dict[str, bool]:
  with connect() as conn:
    cursor = conn.execute("DELETE FROM addresses WHERE id = ? AND username = ?", (address_id, user["username"]))
    conn.commit()
  if cursor.rowcount == 0:
    raise HTTPException(status_code=404, detail="Không tìm thấy địa chỉ")
  return {"ok": True}


# ---------- Tìm địa chỉ theo tên ----------

@router.get("/geocode")
async def geocode(q: str = Query(min_length=2), user: dict[str, str] = Depends(current_user)) -> list[dict[str, Any]]:
  """Tìm toạ độ từ tên địa điểm qua Nominatim.

  Gọi qua backend thay vì gọi thẳng từ trình duyệt để tránh CORS và để tuân thủ
  yêu cầu User-Agent của Nominatim.
  """
  try:
    async with httpx.AsyncClient(timeout=8.0, headers={"User-Agent": "uav-delivery-demo/1.0"}) as client:
      response = await client.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": q, "format": "json", "limit": 6, "countrycodes": "vn", "accept-language": "vi"},
      )
      response.raise_for_status()
      results = response.json()
  except Exception:
    raise HTTPException(status_code=503, detail="Không kết nối được dịch vụ tìm địa chỉ")

  return [
    {"name": item.get("display_name", ""), "lat": float(item["lat"]), "lon": float(item["lon"])}
    for item in results
  ]
