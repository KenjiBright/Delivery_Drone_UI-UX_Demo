from __future__ import annotations

import csv
import io
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from ..db import DB_LOCK, connect, get_settings, home_position, log_event, row_to_order, utc_now
from ..models import AssignRequest, CancelRequest, ProductPatch, ProductRequest, SettingsPatch, UavPatch, UavRequest
from ..firewall import check_port
from ..network import hostname, list_addresses
from ..realtime import manager
from ..security import require_role

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_role("operator"))])

OPEN_STATUSES = ("PENDING", "CONFIRMED", "ASSIGNED", "DISPATCHED", "IN_FLIGHT", "ARRIVED", "UNLOCKED", "DELIVERED", "RETURNING")
SORT_COLUMNS = {"created_at": "created_at", "updated_at": "updated_at", "total_price": "total_price", "status": "status"}


# ---------- Đơn hàng ----------

@router.get("/orders")
def list_orders(
  status: str = Query(default=""),
  q: str = Query(default=""),
  scope: str = Query(default="", description="open | closed"),
  sort: str = Query(default="created_at"),
  direction: str = Query(default="desc"),
  page: int = Query(default=1, ge=1),
  page_size: int = Query(default=25, ge=1, le=200),
) -> dict[str, Any]:
  """Danh sách đơn có lọc, tìm kiếm, sắp xếp và phân trang."""
  where = "WHERE 1 = 1"
  params: list[Any] = []
  if status:
    where += " AND status = ?"
    params.append(status)
  elif scope == "open":
    where += f" AND status IN ({','.join('?' for _ in OPEN_STATUSES)})"
    params += list(OPEN_STATUSES)
  elif scope == "closed":
    where += " AND status IN ('COMPLETED', 'CANCELLED')"
  if q:
    where += " AND (LOWER(id) LIKE ? OR LOWER(delivery_address) LIKE ? OR LOWER(customer_username) LIKE ?)"
    needle = f"%{q.lower()}%"
    params += [needle, needle, needle]

  column = SORT_COLUMNS.get(sort, "created_at")
  order_by = f"ORDER BY {column} {'ASC' if direction.lower() == 'asc' else 'DESC'}"

  with connect() as conn:
    total = conn.execute(f"SELECT COUNT(*) AS n FROM orders {where}", params).fetchone()["n"]
    rows = conn.execute(
      f"SELECT * FROM orders {where} {order_by} LIMIT ? OFFSET ?",
      params + [page_size, (page - 1) * page_size],
    ).fetchall()

  return {
    "items": [row_to_order(row) for row in rows],
    "total": total,
    "page": page,
    "page_size": page_size,
    "pages": max(1, (total + page_size - 1) // page_size),
  }


@router.get("/orders/{order_id}/events")
def order_events(order_id: str) -> list[dict[str, Any]]:
  with connect() as conn:
    rows = conn.execute(
      "SELECT status, actor, note, created_at FROM order_events WHERE order_id = ? ORDER BY id", (order_id,)
    ).fetchall()
  return [dict(row) for row in rows]


async def _transition(order_id: str, status: str, actor: str, note: str) -> dict[str, Any]:
  async with DB_LOCK:
    with connect() as conn:
      row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
      if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")
      conn.execute("UPDATE orders SET status = ?, updated_at = ? WHERE id = ?", (status, utc_now(), order_id))
      log_event(conn, order_id, status, actor, note)
      conn.commit()
      order = row_to_order(conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone())
  await manager.broadcast({"type": "order_updated", "order": order}, order["customer_username"])
  return order


@router.post("/orders/{order_id}/confirm")
async def confirm_order(order_id: str, user: dict[str, str] = Depends(require_role("operator"))) -> dict[str, Any]:
  with connect() as conn:
    row = conn.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()
  if not row:
    raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")
  if row["status"] != "PENDING":
    raise HTTPException(status_code=400, detail="Chỉ xác nhận được đơn đang chờ")
  return await _transition(order_id, "CONFIRMED", user["username"], "Điều phối xác nhận đơn")


@router.post("/orders/{order_id}/assign")
async def assign_order(
  order_id: str,
  request: AssignRequest,
  user: dict[str, str] = Depends(require_role("operator")),
) -> dict[str, Any]:
  async with DB_LOCK:
    with connect() as conn:
      order_row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
      if not order_row:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")
      if order_row["status"] not in {"CONFIRMED", "ASSIGNED"}:
        raise HTTPException(status_code=400, detail="Đơn phải được xác nhận trước khi gán UAV")

      if request.uav_id:
        uav_row = conn.execute("SELECT * FROM uavs WHERE id = ?", (request.uav_id,)).fetchone()
        if not uav_row:
          raise HTTPException(status_code=404, detail="Không tìm thấy UAV")
      else:
        # Tự chọn UAV rảnh, đủ tải và còn nhiều pin nhất.
        uav_row = conn.execute(
          "SELECT * FROM uavs WHERE status = 'AVAILABLE' AND max_payload_kg >= ? ORDER BY battery DESC LIMIT 1",
          (order_row["total_weight_kg"],),
        ).fetchone()
        if not uav_row:
          raise HTTPException(status_code=409, detail="Không còn UAV rảnh phù hợp tải trọng")

      if uav_row["status"] not in {"AVAILABLE", "RESERVED"}:
        raise HTTPException(status_code=409, detail=f"{uav_row['id']} đang bận")
      if uav_row["max_payload_kg"] < order_row["total_weight_kg"]:
        raise HTTPException(status_code=400, detail=f"{uav_row['id']} không đủ tải trọng cho đơn này")

      now = utc_now()
      conn.execute(
        "UPDATE orders SET assigned_uav = ?, status = 'ASSIGNED', updated_at = ? WHERE id = ?",
        (uav_row["id"], now, order_id),
      )
      conn.execute(
        "UPDATE uavs SET status = 'RESERVED', active_order_id = ?, last_seen = ? WHERE id = ?",
        (order_id, now, uav_row["id"]),
      )
      log_event(conn, order_id, "ASSIGNED", user["username"], f"Gán {uav_row['id']}")
      conn.commit()
      order = row_to_order(conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone())

  await manager.broadcast({"type": "order_updated", "order": order}, order["customer_username"])
  return order


@router.post("/orders/{order_id}/dispatch")
async def dispatch_order(order_id: str, user: dict[str, str] = Depends(require_role("operator"))) -> dict[str, Any]:
  async with DB_LOCK:
    with connect() as conn:
      row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
      if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")
      if row["status"] != "ASSIGNED" or not row["assigned_uav"]:
        raise HTTPException(status_code=400, detail="Đơn phải được gán UAV trước khi xuất phát")
      now = utc_now()
      conn.execute("UPDATE orders SET status = 'DISPATCHED', dispatched_at = ?, updated_at = ? WHERE id = ?", (now, now, order_id))
      log_event(conn, order_id, "DISPATCHED", user["username"], "Cho phép xuất phát")
      conn.commit()
      order = row_to_order(conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone())

  await manager.broadcast({"type": "order_updated", "order": order}, order["customer_username"])
  return order


@router.post("/orders/{order_id}/recall")
async def recall_uav(order_id: str, user: dict[str, str] = Depends(require_role("operator"))) -> dict[str, Any]:
  """Cho phép UAV rời điểm giao và bay về kho.

  UAV đậu tại chỗ sau khi khách đóng thùng, chờ đúng lệnh này. Người điều phối giữ
  quyền quyết định vì họ mới là người nhìn được toàn cảnh đội bay.
  """
  async with DB_LOCK:
    with connect() as conn:
      row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
      if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")
      if row["status"] != "DELIVERED":
        raise HTTPException(status_code=400, detail="Chỉ gọi về được khi khách đã đóng thùng")
      if row["return_released_at"]:
        raise HTTPException(status_code=400, detail="Đã ra lệnh quay về rồi")
      now = utc_now()
      conn.execute(
        "UPDATE orders SET return_released_at = ?, return_released_by = ?, updated_at = ? WHERE id = ?",
        (now, user["username"], now, order_id),
      )
      # Ghi là RETURNING chứ không phải DELIVERED: đây là mốc bắt đầu chặng bay về,
      # và nhờ vậy nó nằm trong nhóm sự kiện nội bộ được ẩn khỏi nhật ký của khách —
      # nếu không khách sẽ thấy "Đã nhận hàng" hai lần liên tiếp.
      log_event(conn, order_id, "RETURNING", user["username"], "Điều phối cho UAV quay về")
      conn.commit()
      order = row_to_order(conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone())

  await manager.broadcast({"type": "order_updated", "order": order}, order["customer_username"])
  return order


@router.post("/orders/{order_id}/cancel")
async def cancel_order(
  order_id: str,
  request: CancelRequest,
  user: dict[str, str] = Depends(require_role("operator")),
) -> dict[str, Any]:
  async with DB_LOCK:
    with connect() as conn:
      row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
      if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")
      if row["status"] not in {"PENDING", "CONFIRMED", "ASSIGNED"}:
        raise HTTPException(status_code=400, detail="Đơn đã xuất phát, không thể huỷ")
      now = utc_now()
      conn.execute(
        "UPDATE orders SET status = 'CANCELLED', cancel_reason = ?, updated_at = ?, completed_at = ? WHERE id = ?",
        (request.reason, now, now, order_id),
      )
      if row["assigned_uav"]:
        conn.execute(
          "UPDATE uavs SET status = 'AVAILABLE', active_order_id = NULL, last_seen = ? WHERE id = ?",
          (now, row["assigned_uav"]),
        )
      log_event(conn, order_id, "CANCELLED", user["username"], request.reason or "Điều phối huỷ đơn")
      conn.commit()
      order = row_to_order(conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone())

  await manager.broadcast({"type": "order_updated", "order": order}, order["customer_username"])
  return order


@router.get("/orders.csv")
def export_orders() -> Response:
  with connect() as conn:
    rows = conn.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()

  buffer = io.StringIO()
  writer = csv.writer(buffer)
  writer.writerow([
    "Mã đơn", "Khách hàng", "Trạng thái", "UAV", "Địa chỉ giao",
    "Khối lượng (kg)", "Tổng tiền (đ)", "Đánh giá", "Tạo lúc", "Cập nhật lúc",
  ])
  for row in rows:
    writer.writerow([
      row["id"], row["customer_username"], row["status"], row["assigned_uav"] or "",
      row["delivery_address"], row["total_weight_kg"], row["total_price"],
      row["rating"] or "", row["created_at"], row["updated_at"],
    ])

  # BOM để Excel mở đúng tiếng Việt.
  return Response(
    content="﻿" + buffer.getvalue(),
    media_type="text/csv; charset=utf-8",
    headers={"Content-Disposition": 'attachment; filename="uav-orders.csv"'},
  )


# ---------- Thống kê ----------

@router.get("/stats")
def stats(days: int = Query(default=14, ge=1, le=90)) -> dict[str, Any]:
  with connect() as conn:
    orders = conn.execute("SELECT * FROM orders").fetchall()
    uavs = conn.execute("SELECT * FROM uavs").fetchall()
    low_battery = int(get_settings(conn).get("low_battery_threshold", 30))

  status_counts = Counter(row["status"] for row in orders)
  completed = [row for row in orders if row["status"] == "COMPLETED"]

  # Chuỗi ngày liên tục để biểu đồ không bị đứt đoạn khi có ngày trống.
  today = datetime.now(timezone.utc).date()
  timeline_keys = [(today - timedelta(days=offset)).isoformat() for offset in range(days - 1, -1, -1)]
  per_day = Counter(row["created_at"][:10] for row in orders)
  revenue_per_day = Counter()
  for row in completed:
    revenue_per_day[(row["completed_at"] or row["updated_at"])[:10]] += row["total_price"]

  durations: list[float] = []
  for row in completed:
    if row["dispatched_at"] and row["completed_at"]:
      try:
        start = datetime.fromisoformat(row["dispatched_at"])
        end = datetime.fromisoformat(row["completed_at"])
        durations.append((end - start).total_seconds())
      except ValueError:
        pass

  product_counter: Counter[str] = Counter()
  for row in orders:
    for item in json.loads(row["items_json"]):
      product_counter[item["name"]] += item["quantity"]

  ratings = [row["rating"] for row in orders if row["rating"]]

  return {
    "totals": {
      "orders": len(orders),
      "pending": status_counts.get("PENDING", 0),
      "active": sum(status_counts.get(status, 0) for status in ("CONFIRMED", "ASSIGNED", "DISPATCHED", "IN_FLIGHT", "ARRIVED", "UNLOCKED", "DELIVERED", "RETURNING")),
      "completed": status_counts.get("COMPLETED", 0),
      "cancelled": status_counts.get("CANCELLED", 0),
      "revenue": sum(row["total_price"] for row in completed),
      "avg_delivery_seconds": round(sum(durations) / len(durations)) if durations else None,
      "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
      "rating_count": len(ratings),
    },
    # UAV đã giao xong nhưng còn nằm ngoài hiện trường vì chưa ai ra lệnh quay về.
    "awaiting_recall": [
      {"order_id": row["id"], "uav": row["assigned_uav"], "since": row["box_closed_at"] or row["updated_at"]}
      for row in orders if row["status"] == "DELIVERED" and not row["return_released_at"]
    ],
    "status_breakdown": [{"status": status, "count": count} for status, count in status_counts.most_common()],
    "timeline": [
      {"date": key, "orders": per_day.get(key, 0), "revenue": revenue_per_day.get(key, 0)}
      for key in timeline_keys
    ],
    "top_products": [{"name": name, "quantity": quantity} for name, quantity in product_counter.most_common(5)],
    "fleet": {
      "total": len(uavs),
      "available": sum(1 for row in uavs if row["status"] == "AVAILABLE"),
      "busy": sum(1 for row in uavs if row["status"] not in ("AVAILABLE", "MAINTENANCE", "OFFLINE")),
      "maintenance": sum(1 for row in uavs if row["status"] == "MAINTENANCE"),
      "low_battery": [row["id"] for row in uavs if row["battery"] < low_battery],
      "low_battery_threshold": low_battery,
    },
  }


# ---------- Khách hàng ----------

@router.get("/customers")
def customers() -> list[dict[str, Any]]:
  with connect() as conn:
    rows = conn.execute(
      """SELECT u.username, u.display_name, u.phone, u.created_at,
                COUNT(o.id) AS order_count,
                COALESCE(SUM(CASE WHEN o.status = 'COMPLETED' THEN o.total_price ELSE 0 END), 0) AS total_spent,
                MAX(o.created_at) AS last_order_at,
                AVG(o.rating) AS avg_rating
         FROM users u LEFT JOIN orders o ON o.customer_username = u.username
         WHERE u.role = 'customer'
         GROUP BY u.username ORDER BY order_count DESC"""
    ).fetchall()
  return [dict(row) for row in rows]


# ---------- Sản phẩm ----------

@router.get("/products")
def admin_products() -> list[dict[str, Any]]:
  with connect() as conn:
    rows = conn.execute("SELECT * FROM products ORDER BY category, name").fetchall()
  return [dict(row) for row in rows]


@router.post("/products")
def create_product(request: ProductRequest) -> dict[str, Any]:
  with connect() as conn:
    if conn.execute("SELECT 1 FROM products WHERE id = ?", (request.id,)).fetchone():
      raise HTTPException(status_code=409, detail=f"Mã sản phẩm {request.id} đã tồn tại")
    conn.execute(
      "INSERT INTO products (id, name, description, price, weight_kg, icon, category, active) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
      (request.id, request.name, request.description, request.price, request.weight_kg, request.icon, request.category, int(request.active)),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM products WHERE id = ?", (request.id,)).fetchone()
  return dict(row)


@router.patch("/products/{product_id}")
def update_product(product_id: str, request: ProductPatch) -> dict[str, Any]:
  updates = request.model_dump(exclude_none=True)
  if not updates:
    raise HTTPException(status_code=400, detail="Không có thay đổi nào")
  if "active" in updates:
    updates["active"] = int(updates["active"])
  assignments = ", ".join(f"{key} = ?" for key in updates)
  with connect() as conn:
    cursor = conn.execute(f"UPDATE products SET {assignments} WHERE id = ?", list(updates.values()) + [product_id])
    conn.commit()
    if cursor.rowcount == 0:
      raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
  return dict(row)


@router.delete("/products/{product_id}")
def delete_product(product_id: str) -> dict[str, bool]:
  with connect() as conn:
    cursor = conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
  if cursor.rowcount == 0:
    raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
  return {"ok": True}


# ---------- Đội UAV ----------

@router.post("/uavs")
def create_uav(request: UavRequest) -> dict[str, Any]:
  with connect() as conn:
    if conn.execute("SELECT 1 FROM uavs WHERE id = ?", (request.id,)).fetchone():
      raise HTTPException(status_code=409, detail=f"UAV {request.id} đã tồn tại")
    lat, lon = home_position(conn)
    conn.execute(
      """INSERT INTO uavs (id, model, status, battery, lat, lon, altitude, speed, heading, active_order_id, max_payload_kg, note, last_seen)
      VALUES (?, ?, 'OFFLINE', 100.0, ?, ?, 0, 0, 0, NULL, ?, ?, ?)""",
      (request.id, request.model, lat, lon, request.max_payload_kg, request.note, utc_now()),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM uavs WHERE id = ?", (request.id,)).fetchone()
  return dict(row)


@router.patch("/uavs/{uav_id}")
def update_uav(uav_id: str, request: UavPatch) -> dict[str, Any]:
  updates = request.model_dump(exclude_none=True)
  if not updates:
    raise HTTPException(status_code=400, detail="Không có thay đổi nào")
  if "status" in updates and updates["status"] not in {"AVAILABLE", "MAINTENANCE", "OFFLINE"}:
    raise HTTPException(status_code=400, detail="Chỉ đổi được sang AVAILABLE, MAINTENANCE hoặc OFFLINE")
  assignments = ", ".join(f"{key} = ?" for key in updates)
  with connect() as conn:
    row = conn.execute("SELECT * FROM uavs WHERE id = ?", (uav_id,)).fetchone()
    if not row:
      raise HTTPException(status_code=404, detail="Không tìm thấy UAV")
    if "status" in updates and row["active_order_id"]:
      raise HTTPException(status_code=409, detail="UAV đang thực hiện nhiệm vụ")
    conn.execute(f"UPDATE uavs SET {assignments} WHERE id = ?", list(updates.values()) + [uav_id])
    conn.commit()
    updated = conn.execute("SELECT * FROM uavs WHERE id = ?", (uav_id,)).fetchone()
  return dict(updated)


@router.delete("/uavs/{uav_id}")
def delete_uav(uav_id: str) -> dict[str, bool]:
  with connect() as conn:
    row = conn.execute("SELECT * FROM uavs WHERE id = ?", (uav_id,)).fetchone()
    if not row:
      raise HTTPException(status_code=404, detail="Không tìm thấy UAV")
    if row["active_order_id"]:
      raise HTTPException(status_code=409, detail="UAV đang thực hiện nhiệm vụ, không thể xoá")
    conn.execute("DELETE FROM uavs WHERE id = ?", (uav_id,))
    conn.commit()
  return {"ok": True}


# ---------- Cấu hình ----------

@router.get("/settings")
def read_settings() -> dict[str, str]:
  with connect() as conn:
    return get_settings(conn)


@router.get("/network")
def network(request: Request) -> dict[str, Any]:
  """Địa chỉ máy chủ đang có + đường truy cập đã chọn, để console dựng link cho máy khách."""
  with connect() as conn:
    settings = get_settings(conn)

  served_port = request.url.port or (443 if request.url.scheme == "https" else 80)
  return {
    "hostname": hostname(),
    "addresses": list_addresses(),
    "served_host": request.url.hostname,
    "served_port": served_port,
    "access_host": settings.get("access_host", ""),
    "access_port": settings.get("access_port", "") or str(served_port),
  }


@router.get("/firewall")
def firewall(port: int = Query(ge=1, le=65535), refresh: bool = Query(default=False)) -> dict[str, Any]:
  """Tường lửa có cho máy ngoài vào cổng này không.

  Tách khỏi /network vì phải gọi netsh mất khoảng một giây, không nên bắt cả bảng
  địa chỉ chờ theo.
  """
  return check_port(port, refresh=refresh)


@router.patch("/settings")
def patch_settings(request: SettingsPatch) -> dict[str, str]:
  updates = request.model_dump(exclude_none=True)
  if not updates:
    raise HTTPException(status_code=400, detail="Không có thay đổi nào")
  with connect() as conn:
    for key, value in updates.items():
      conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
      )
    conn.commit()
    return get_settings(conn)
