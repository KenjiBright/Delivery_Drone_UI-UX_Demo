from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..db import DB_LOCK, connect, log_event, row_to_order, utc_now
from ..models import TelemetryRequest
from ..realtime import manager
from ..security import current_user, simulator_auth

router = APIRouter(prefix="/api", tags=["fleet"])


@router.get("/uavs")
def list_uavs(user: dict[str, str] = Depends(current_user)) -> list[dict[str, Any]]:
  with connect() as conn:
    rows = conn.execute("SELECT * FROM uavs ORDER BY id").fetchall()
  return [dict(row) for row in rows]


# ---------- Kênh dành riêng cho simulator / UAV thật ----------

@router.get("/simulator/mission/{uav_id}", dependencies=[Depends(simulator_auth)])
def simulator_mission(uav_id: str) -> dict[str, Any] | None:
  with connect() as conn:
    row = conn.execute(
      "SELECT * FROM orders WHERE assigned_uav = ? AND status = 'DISPATCHED' ORDER BY created_at LIMIT 1",
      (uav_id,),
    ).fetchone()
  return row_to_order(row) if row else None


@router.get("/simulator/order/{order_id}", dependencies=[Depends(simulator_auth)])
def simulator_order(order_id: str) -> dict[str, Any]:
  with connect() as conn:
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
  if not row:
    raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")
  return row_to_order(row)


@router.post("/simulator/telemetry", dependencies=[Depends(simulator_auth)])
async def simulator_telemetry(request: TelemetryRequest) -> dict[str, Any]:
  customer_username: str | None = None
  order: dict[str, Any] | None = None

  async with DB_LOCK:
    with connect() as conn:
      existing = conn.execute("SELECT status FROM uavs WHERE id = ?", (request.uav_id,)).fetchone()
      if not existing:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy {request.uav_id}")

      # Trạng thái do điều phối viên đặt (bảo trì / ngoại tuyến) không được telemetry
      # ghi đè, nếu không UAV vừa cho bảo trì sẽ tự nhảy về AVAILABLE sau vài giây.
      operator_locked = existing["status"] in {"MAINTENANCE", "OFFLINE"} and not request.order_id
      next_status = existing["status"] if operator_locked else request.uav_status

      now = utc_now()
      conn.execute(
        """UPDATE uavs SET status = ?, battery = ?, lat = ?, lon = ?, altitude = ?, speed = ?, heading = ?,
        active_order_id = ?, last_seen = ? WHERE id = ?""",
        (
          next_status,
          max(0.0, min(100.0, request.battery)),
          request.lat, request.lon, request.altitude, request.speed, request.heading,
          None if next_status in {"AVAILABLE", "MAINTENANCE", "OFFLINE"} else request.order_id,
          now, request.uav_id,
        ),
      )

      if request.order_id and request.order_status:
        previous = conn.execute("SELECT status FROM orders WHERE id = ?", (request.order_id,)).fetchone()
        if previous:
          completed_at = now if request.order_status == "COMPLETED" else None
          conn.execute(
            "UPDATE orders SET status = ?, updated_at = ?, completed_at = COALESCE(?, completed_at) WHERE id = ?",
            (request.order_status, now, completed_at, request.order_id),
          )
          # Chỉ ghi nhật ký khi trạng thái thực sự đổi, tránh spam mỗi bước telemetry.
          if previous["status"] != request.order_status:
            log_event(conn, request.order_id, request.order_status, request.uav_id, "Cập nhật từ UAV")
          order_row = conn.execute("SELECT * FROM orders WHERE id = ?", (request.order_id,)).fetchone()
          order = row_to_order(order_row)
          customer_username = order["customer_username"]

      conn.commit()
      uav = dict(conn.execute("SELECT * FROM uavs WHERE id = ?", (request.uav_id,)).fetchone())

  event: dict[str, Any] = {"type": "telemetry", "uav": uav}
  if order:
    event["order"] = order
  await manager.broadcast(event, customer_username)
  return {"ok": True, "uav": uav, "order": order}
