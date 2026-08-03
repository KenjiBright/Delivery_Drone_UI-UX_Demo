import os
import tempfile
from pathlib import Path

DB_PATH = Path(tempfile.gettempdir()) / "uav_delivery_demo_test.db"
DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_PATH"] = str(DB_PATH)

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
  with TestClient(app) as test_client:
    yield test_client


def auth(client: TestClient, username: str, password: str, role: str) -> dict[str, str]:
  response = client.post("/api/auth/login", json={"username": username, "password": password, "expected_role": role})
  assert response.status_code == 200, response.text
  return {"Authorization": f"Bearer {response.json()['access_token']}"}


def make_order(client: TestClient, headers: dict[str, str], quantity: int = 1) -> dict:
  products = client.get("/api/products", headers=headers).json()
  response = client.post(
    "/api/orders",
    headers=headers,
    json={
      "items": [{"product_id": products[0]["id"], "quantity": quantity}],
      "delivery_lat": 21.0301,
      "delivery_lon": 105.8401,
      "delivery_address": "Điểm giao thử nghiệm",
      "note": "Giao giờ hành chính",
    },
  )
  assert response.status_code == 200, response.text
  return response.json()


def test_order_workflow(client: TestClient) -> None:
  """Luồng chính: đặt đơn, xác nhận, gán UAV, xuất phát, simulator nhận nhiệm vụ."""
  customer = auth(client, "customer", "khachhang123", "customer")
  operator = auth(client, "operator", "dieuphoi123", "operator")

  order_id = make_order(client, customer)["id"]

  assert client.post(f"/api/admin/orders/{order_id}/confirm", headers=operator).json()["status"] == "CONFIRMED"
  assigned = client.post(f"/api/admin/orders/{order_id}/assign", headers=operator, json={}).json()
  assert assigned["status"] == "ASSIGNED"
  assert assigned["assigned_uav"], "phải tự chọn được một UAV rảnh"
  assert client.post(f"/api/admin/orders/{order_id}/dispatch", headers=operator).json()["status"] == "DISPATCHED"

  mission = client.get(f"/api/simulator/mission/{assigned['assigned_uav']}", headers={"X-API-Key": "demo-sim-key"})
  assert mission.status_code == 200
  assert mission.json()["id"] == order_id


def test_status_history_is_recorded(client: TestClient) -> None:
  customer = auth(client, "customer", "khachhang123", "customer")
  operator = auth(client, "operator", "dieuphoi123", "operator")

  order_id = make_order(client, customer)["id"]
  client.post(f"/api/admin/orders/{order_id}/confirm", headers=operator)

  events = client.get(f"/api/admin/orders/{order_id}/events", headers=operator).json()
  assert [event["status"] for event in events] == ["PENDING", "CONFIRMED"]


def test_cancel_frees_the_uav(client: TestClient) -> None:
  customer = auth(client, "customer", "khachhang123", "customer")
  operator = auth(client, "operator", "dieuphoi123", "operator")

  order_id = make_order(client, customer)["id"]
  client.post(f"/api/admin/orders/{order_id}/confirm", headers=operator)
  uav_id = client.post(f"/api/admin/orders/{order_id}/assign", headers=operator, json={}).json()["assigned_uav"]

  cancelled = client.post(f"/api/admin/orders/{order_id}/cancel", headers=operator, json={"reason": "Khách đổi ý"})
  assert cancelled.json()["status"] == "CANCELLED"

  uav = next(item for item in client.get("/api/uavs", headers=operator).json() if item["id"] == uav_id)
  assert uav["status"] == "AVAILABLE", "huỷ đơn phải trả UAV về trạng thái rảnh"
  assert uav["active_order_id"] is None


def test_dispatched_order_cannot_be_cancelled(client: TestClient) -> None:
  customer = auth(client, "customer", "khachhang123", "customer")
  operator = auth(client, "operator", "dieuphoi123", "operator")

  order_id = make_order(client, customer)["id"]
  client.post(f"/api/admin/orders/{order_id}/confirm", headers=operator)
  client.post(f"/api/admin/orders/{order_id}/assign", headers=operator, json={})
  client.post(f"/api/admin/orders/{order_id}/dispatch", headers=operator)

  response = client.post(f"/api/admin/orders/{order_id}/cancel", headers=operator, json={"reason": "muộn"})
  assert response.status_code == 400


def free_uav_id(client: TestClient, headers: dict[str, str]) -> str:
  uav = next(item for item in client.get("/api/uavs", headers=headers).json() if item["status"] == "AVAILABLE")
  return uav["id"]


def telemetry_beat(client: TestClient, uav_id: str, status: str = "AVAILABLE"):
  return client.post(
    "/api/simulator/telemetry",
    headers={"X-API-Key": "demo-sim-key"},
    json={"uav_id": uav_id, "lat": 21.0278, "lon": 105.8342, "battery": 90.0, "uav_status": status},
  )


def test_maintenance_survives_telemetry(client: TestClient) -> None:
  """Telemetry của simulator không được ghi đè trạng thái bảo trì do điều phối đặt."""
  operator = auth(client, "operator", "dieuphoi123", "operator")
  uav_id = free_uav_id(client, operator)

  patched = client.patch(f"/api/admin/uavs/{uav_id}", headers=operator, json={"status": "MAINTENANCE"})
  assert patched.status_code == 200, patched.text

  # Simulator vẫn đều đặn báo "AVAILABLE" mỗi hai giây.
  beat = telemetry_beat(client, uav_id)
  assert beat.status_code == 200
  assert beat.json()["uav"]["status"] == "MAINTENANCE"

  # Điều phối cho hoạt động lại thì telemetry mới được phép cập nhật tiếp.
  client.patch(f"/api/admin/uavs/{uav_id}", headers=operator, json={"status": "AVAILABLE"})
  assert telemetry_beat(client, uav_id).json()["uav"]["status"] == "AVAILABLE"


def test_uav_in_maintenance_is_not_auto_assigned(client: TestClient) -> None:
  customer = auth(client, "customer", "khachhang123", "customer")
  operator = auth(client, "operator", "dieuphoi123", "operator")

  for uav in client.get("/api/uavs", headers=operator).json():
    client.patch(f"/api/admin/uavs/{uav['id']}", headers=operator, json={"status": "MAINTENANCE"})

  order_id = make_order(client, customer)["id"]
  client.post(f"/api/admin/orders/{order_id}/confirm", headers=operator)
  response = client.post(f"/api/admin/orders/{order_id}/assign", headers=operator, json={})
  assert response.status_code == 409

  for uav in client.get("/api/uavs", headers=operator).json():
    client.patch(f"/api/admin/uavs/{uav['id']}", headers=operator, json={"status": "AVAILABLE"})


def test_order_rejected_when_over_payload(client: TestClient) -> None:
  customer = auth(client, "customer", "khachhang123", "customer")
  products = client.get("/api/products", headers=customer).json()
  heaviest = max(products, key=lambda product: product["weight_kg"])

  response = client.post(
    "/api/orders",
    headers=customer,
    json={
      "items": [{"product_id": heaviest["id"], "quantity": 20}],
      "delivery_lat": 21.03, "delivery_lon": 105.84, "delivery_address": "Quá tải",
    },
  )
  assert response.status_code == 400
  assert "tải trọng" in response.json()["detail"].lower()


def test_orders_are_filtered_and_paginated(client: TestClient) -> None:
  customer = auth(client, "customer", "khachhang123", "customer")
  operator = auth(client, "operator", "dieuphoi123", "operator")
  make_order(client, customer)

  page = client.get("/api/admin/orders?status=PENDING&page_size=1", headers=operator).json()
  assert page["page_size"] == 1
  assert len(page["items"]) <= 1
  assert all(order["status"] == "PENDING" for order in page["items"])


def test_customer_cannot_reach_admin_routes(client: TestClient) -> None:
  customer = auth(client, "customer", "khachhang123", "customer")
  assert client.get("/api/admin/orders", headers=customer).status_code == 403
  assert client.get("/api/admin/stats", headers=customer).status_code == 403


def test_address_book_roundtrip(client: TestClient) -> None:
  customer = auth(client, "customer", "khachhang123", "customer")
  created = client.post(
    "/api/addresses",
    headers=customer,
    json={"label": "Nhà", "address": "Số 1 Trần Phú", "lat": 21.03, "lon": 105.84},
  ).json()

  assert any(item["id"] == created["id"] for item in client.get("/api/addresses", headers=customer).json())
  assert client.delete(f"/api/addresses/{created['id']}", headers=customer).status_code == 200
  assert not any(item["id"] == created["id"] for item in client.get("/api/addresses", headers=customer).json())


def test_product_crud(client: TestClient) -> None:
  operator = auth(client, "operator", "dieuphoi123", "operator")

  created = client.post(
    "/api/admin/products",
    headers=operator,
    json={"id": "TEST01", "name": "Hàng thử", "description": "mô tả", "price": 1000,
          "weight_kg": 0.2, "icon": "package", "category": "Thử nghiệm"},
  )
  assert created.status_code == 200

  patched = client.patch("/api/admin/products/TEST01", headers=operator, json={"price": 2000, "active": False})
  assert patched.json()["price"] == 2000
  assert patched.json()["active"] == 0

  customer = auth(client, "customer", "khachhang123", "customer")
  assert not any(p["id"] == "TEST01" for p in client.get("/api/products", headers=customer).json()), \
    "sản phẩm đã ẩn không được xuất hiện với khách hàng"

  assert client.delete("/api/admin/products/TEST01", headers=operator).status_code == 200


def test_stats_shape(client: TestClient) -> None:
  operator = auth(client, "operator", "dieuphoi123", "operator")
  stats = client.get("/api/admin/stats?days=7", headers=operator).json()

  assert len(stats["timeline"]) == 7
  assert {"orders", "pending", "completed", "revenue"} <= stats["totals"].keys()
  assert {"total", "available", "low_battery_threshold"} <= stats["fleet"].keys()


def test_csv_export(client: TestClient) -> None:
  operator = auth(client, "operator", "dieuphoi123", "operator")
  response = client.get("/api/admin/orders.csv", headers=operator)
  assert response.status_code == 200
  assert "text/csv" in response.headers["content-type"]
  assert "Mã đơn" in response.text


def test_web_pages_are_served(client: TestClient) -> None:
  """Backend phục vụ luôn hai giao diện, không cần server tĩnh riêng."""
  for path in ("/", "/operator"):
    response = client.get(path)
    assert response.status_code == 200, path
    assert response.headers["content-type"].startswith("text/html"), path

  for asset in (
    "/static/css/base.css", "/static/css/app.css", "/static/css/console.css",
    "/static/js/api.js", "/static/js/ui.js", "/static/js/icons.js",
    "/static/js/customer/main.js", "/static/js/console/main.js",
  ):
    assert client.get(asset).status_code == 200, asset
