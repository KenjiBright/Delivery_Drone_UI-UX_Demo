from __future__ import annotations

import math
import os
import time
from typing import Any

import httpx

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.getenv("SIMULATOR_API_KEY", "demo-sim-key")
UAV_ID = os.getenv("UAV_ID", "UAV-01")
HOME_LAT = float(os.getenv("HOME_LAT", "21.0278"))
HOME_LON = float(os.getenv("HOME_LON", "105.8342"))
STEP_SECONDS = float(os.getenv("STEP_SECONDS", "1.0"))
FLIGHT_STEPS = int(os.getenv("FLIGHT_STEPS", "35"))


def heading_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
  y = math.sin(math.radians(lon2 - lon1)) * math.cos(math.radians(lat2))
  x = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(math.radians(lon2 - lon1))
  return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


class Simulator:
  def __init__(self) -> None:
    self.client = httpx.Client(timeout=10.0, headers={"X-API-Key": API_KEY})
    self.battery = 96.0

  def post_telemetry(
    self,
    lat: float,
    lon: float,
    altitude: float,
    speed: float,
    heading: float,
    uav_status: str,
    order_id: str | None,
    order_status: str | None,
  ) -> None:
    payload = {
      "uav_id": UAV_ID,
      "lat": lat,
      "lon": lon,
      "altitude": altitude,
      "speed": speed,
      "heading": heading,
      "battery": self.battery,
      "uav_status": uav_status,
      "order_id": order_id,
      "order_status": order_status,
    }
    response = self.client.post(f"{BACKEND_URL}/api/simulator/telemetry", json=payload)
    response.raise_for_status()

  def get_mission(self) -> dict[str, Any] | None:
    response = self.client.get(f"{BACKEND_URL}/api/simulator/mission/{UAV_ID}")
    response.raise_for_status()
    return response.json()

  def get_order(self, order_id: str) -> dict[str, Any]:
    response = self.client.get(f"{BACKEND_URL}/api/simulator/order/{order_id}")
    response.raise_for_status()
    return response.json()

  def fly_leg(
    self,
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
    order_id: str,
    order_status: str,
    uav_status: str,
  ) -> None:
    heading = heading_between(start_lat, start_lon, end_lat, end_lon)
    for step in range(FLIGHT_STEPS + 1):
      ratio = step / FLIGHT_STEPS
      lat = start_lat + (end_lat - start_lat) * ratio
      lon = start_lon + (end_lon - start_lon) * ratio
      altitude = min(25.0, 25.0 * min(ratio * 4.0, (1.0 - ratio) * 4.0, 1.0))
      speed = 8.0 if 0 < step < FLIGHT_STEPS else 0.0
      self.battery = max(20.0, self.battery - 0.12)
      self.post_telemetry(lat, lon, altitude, speed, heading, uav_status, order_id, order_status)
      time.sleep(STEP_SECONDS)

  def execute_mission(self, mission: dict[str, Any]) -> None:
    order_id = mission["id"]
    target_lat = float(mission["delivery_lat"])
    target_lon = float(mission["delivery_lon"])
    print(f"[{UAV_ID}] Nhận nhiệm vụ {order_id}: {target_lat}, {target_lon}", flush=True)
    self.fly_leg(HOME_LAT, HOME_LON, target_lat, target_lon, order_id, "IN_FLIGHT", "DELIVERING")
    self.post_telemetry(target_lat, target_lon, 0.0, 0.0, 0.0, "WAITING_CONFIRMATION", order_id, "ARRIVED")
    print(f"[{UAV_ID}] Đã đến. Chờ khách xác nhận PIN cho {order_id}", flush=True)
    while True:
      order = self.get_order(order_id)
      if order["status"] == "DELIVERED":
        break
      time.sleep(2.0)
    print(f"[{UAV_ID}] Đã giao. Bay về Home", flush=True)
    self.fly_leg(target_lat, target_lon, HOME_LAT, HOME_LON, order_id, "RETURNING", "RETURNING")
    self.post_telemetry(HOME_LAT, HOME_LON, 0.0, 0.0, 0.0, "AVAILABLE", order_id, "COMPLETED")
    print(f"[{UAV_ID}] Hoàn thành {order_id}", flush=True)

  def run(self) -> None:
    print(f"UAV simulator kết nối {BACKEND_URL}", flush=True)
    while True:
      try:
        mission = self.get_mission()
        if mission:
          self.execute_mission(mission)
        else:
          self.post_telemetry(HOME_LAT, HOME_LON, 0.0, 0.0, 0.0, "AVAILABLE", None, None)
          time.sleep(2.0)
      except Exception as exc:
        print(f"Simulator lỗi: {exc}", flush=True)
        time.sleep(3.0)


if __name__ == "__main__":
  Simulator().run()
