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


SIM = {"X-API-Key": "demo-sim-key"}


def telemetry(client: TestClient, uav_id: str, order_id: str | None, order_status: str | None, uav_status: str) -> None:
  response = client.post("/api/simulator/telemetry", headers=SIM, json={
    "uav_id": uav_id, "lat": 21.03, "lon": 105.84, "altitude": 0.0, "speed": 0.0,
    "heading": 0.0, "battery": 90.0, "uav_status": uav_status,
    "order_id": order_id, "order_status": order_status,
  })
  assert response.status_code == 200, response.text


def fly_to_customer(client: TestClient, customer: dict, operator: dict) -> tuple[str, str]:
  """Đưa một đơn tới lúc UAV đã hạ cánh và đang chờ khách nhập PIN."""
  order_id = make_order(client, customer)["id"]
  client.post(f"/api/admin/orders/{order_id}/confirm", headers=operator)
  uav_id = client.post(f"/api/admin/orders/{order_id}/assign", headers=operator, json={}).json()["assigned_uav"]
  client.post(f"/api/admin/orders/{order_id}/dispatch", headers=operator)
  telemetry(client, uav_id, order_id, "ARRIVED", "WAITING_CONFIRMATION")
  return order_id, uav_id


def release(client: TestClient, uav_id: str, order_id: str) -> None:
  """Trả UAV về trạng thái rảnh.

  Chỉ có ba UAV trong dữ liệu mẫu, test nào giữ UAV lại thì test sau sẽ không còn
  cái nào để gán và đổ với lỗi chẳng liên quan gì tới thứ nó đang kiểm tra.
  """
  telemetry(client, uav_id, order_id, "COMPLETED", "AVAILABLE")


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


# ---------- Luồng nhận hàng: mở thùng, đóng thùng, chờ lệnh quay về ----------

def test_pickup_flow(client: TestClient) -> None:
  customer = auth(client, "customer", "khachhang123", "customer")
  operator = auth(client, "operator", "dieuphoi123", "operator")
  order_id, uav_id = fly_to_customer(client, customer, operator)

  code = client.get(f"/api/orders/{order_id}", headers=customer).json()["verification_code"]

  # Chưa mở thùng thì không thể đóng.
  assert client.post(f"/api/orders/{order_id}/close-box", headers=customer).status_code == 400

  wrong = client.post(f"/api/orders/{order_id}/verify", headers=customer, json={"code": "0000" if code != "0000" else "1111"})
  assert wrong.status_code == 400

  opened = client.post(f"/api/orders/{order_id}/verify", headers=customer, json={"code": code}).json()
  assert opened["status"] == "UNLOCKED", "nhập đúng PIN chỉ mở thùng, chưa phải đã giao xong"
  assert opened["box_opened_at"]

  closed = client.post(f"/api/orders/{order_id}/close-box", headers=customer).json()
  assert closed["status"] == "DELIVERED"
  assert closed["box_closed_at"]
  assert closed["return_released_at"] is None, "UAV phải đợi lệnh của điều phối"

  # Simulator nhìn thấy đúng thứ nó cần để biết là chưa được về.
  seen = client.get(f"/api/simulator/order/{order_id}", headers=SIM).json()
  assert seen["status"] == "DELIVERED" and seen["return_released_at"] is None

  released = client.post(f"/api/admin/orders/{order_id}/recall", headers=operator).json()
  assert released["return_released_at"] and released["return_released_by"] == "operator"
  assert client.post(f"/api/admin/orders/{order_id}/recall", headers=operator).status_code == 400

  # Nhật ký ghi lệnh gọi về là RETURNING, nên khách không thấy "Đã nhận hàng" hai lần.
  events = [event["status"] for event in client.get(f"/api/admin/orders/{order_id}/events", headers=operator).json()]
  assert events.count("DELIVERED") == 1
  assert "RETURNING" in events

  telemetry(client, uav_id, order_id, "COMPLETED", "AVAILABLE")
  assert client.get(f"/api/orders/{order_id}", headers=customer).json()["status"] == "COMPLETED"


def test_recall_needs_closed_box(client: TestClient) -> None:
  customer = auth(client, "customer", "khachhang123", "customer")
  operator = auth(client, "operator", "dieuphoi123", "operator")
  order_id, uav_id = fly_to_customer(client, customer, operator)

  assert client.post(f"/api/admin/orders/{order_id}/recall", headers=operator).status_code == 400
  code = client.get(f"/api/orders/{order_id}", headers=customer).json()["verification_code"]
  client.post(f"/api/orders/{order_id}/verify", headers=customer, json={"code": code})
  assert client.post(f"/api/admin/orders/{order_id}/recall", headers=operator).status_code == 400, \
    "thùng mới mở, khách chưa lấy xong"
  release(client, uav_id, order_id)


def test_telemetry_does_not_reopen_the_box(client: TestClient) -> None:
  """UAV đậu tại chỗ vẫn gửi telemetry; nó không được kéo đơn ngược về ARRIVED."""
  customer = auth(client, "customer", "khachhang123", "customer")
  operator = auth(client, "operator", "dieuphoi123", "operator")
  order_id, uav_id = fly_to_customer(client, customer, operator)

  code = client.get(f"/api/orders/{order_id}", headers=customer).json()["verification_code"]
  client.post(f"/api/orders/{order_id}/verify", headers=customer, json={"code": code})

  telemetry(client, uav_id, order_id, None, "WAITING_CONFIRMATION")
  assert client.get(f"/api/orders/{order_id}", headers=customer).json()["status"] == "UNLOCKED"
  release(client, uav_id, order_id)


def test_customer_can_rate_right_after_closing_the_box(client: TestClient) -> None:
  """Khách không phải chờ UAV bay về kho mới được đánh giá."""
  customer = auth(client, "customer", "khachhang123", "customer")
  operator = auth(client, "operator", "dieuphoi123", "operator")
  order_id, uav_id = fly_to_customer(client, customer, operator)

  code = client.get(f"/api/orders/{order_id}", headers=customer).json()["verification_code"]
  client.post(f"/api/orders/{order_id}/verify", headers=customer, json={"code": code})
  client.post(f"/api/orders/{order_id}/close-box", headers=customer)

  rated = client.post(f"/api/orders/{order_id}/rate", headers=customer, json={"rating": 5, "review": "Nhanh"})
  assert rated.status_code == 200, rated.text
  assert rated.json()["rating"] == 5
  release(client, uav_id, order_id)


def test_delivered_order_leaves_customer_active_list(client: TestClient) -> None:
  """Với khách, đóng thùng là xong; chặng UAV bay về không còn hiện ở mục đang giao."""
  customer = auth(client, "customer", "khachhang123", "customer")
  operator = auth(client, "operator", "dieuphoi123", "operator")
  order_id, uav_id = fly_to_customer(client, customer, operator)

  code = client.get(f"/api/orders/{order_id}", headers=customer).json()["verification_code"]
  client.post(f"/api/orders/{order_id}/verify", headers=customer, json={"code": code})
  client.post(f"/api/orders/{order_id}/close-box", headers=customer)

  active = [item["id"] for item in client.get("/api/orders/mine?scope=active", headers=customer).json()]
  history = [item["id"] for item in client.get("/api/orders/mine?scope=history", headers=customer).json()]
  assert order_id not in active
  assert order_id in history
  release(client, uav_id, order_id)


def test_stats_flag_uavs_waiting_for_recall(client: TestClient) -> None:
  customer = auth(client, "customer", "khachhang123", "customer")
  operator = auth(client, "operator", "dieuphoi123", "operator")
  order_id, uav_id = fly_to_customer(client, customer, operator)

  code = client.get(f"/api/orders/{order_id}", headers=customer).json()["verification_code"]
  client.post(f"/api/orders/{order_id}/verify", headers=customer, json={"code": code})
  client.post(f"/api/orders/{order_id}/close-box", headers=customer)

  waiting = client.get("/api/admin/stats", headers=operator).json()["awaiting_recall"]
  assert order_id in [item["order_id"] for item in waiting]
  assert uav_id in [item["uav"] for item in waiting]

  client.post(f"/api/admin/orders/{order_id}/recall", headers=operator)
  waiting = client.get("/api/admin/stats", headers=operator).json()["awaiting_recall"]
  assert order_id not in [item["order_id"] for item in waiting]
  release(client, uav_id, order_id)


  release(client, uav_id, order_id)
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
    "/static/js/customer/main.js", "/static/js/console/main.js", "/static/js/theme.js",
  ):
    assert client.get(asset).status_code == 200, asset


def test_network_lists_addresses(client: TestClient) -> None:
  """Console cần biết máy chủ có những địa chỉ nào để công bố cho máy khách."""
  operator = auth(client, "operator", "dieuphoi123", "operator")
  data = client.get("/api/admin/network", headers=operator).json()

  assert data["hostname"]
  assert data["access_port"], "phải rơi về cổng đang phục vụ khi chưa cấu hình"
  for entry in data["addresses"]:
    assert entry["kind"] in {"vpn", "lan", "public"}
    assert not entry["address"].startswith("127."), "địa chỉ loopback không dùng cho máy khách"


def test_access_settings_round_trip(client: TestClient) -> None:
  operator = auth(client, "operator", "dieuphoi123", "operator")
  saved = client.patch(
    "/api/admin/settings",
    json={"access_host": "100.101.102.103", "access_port": 9100},
    headers=operator,
  ).json()
  assert saved["access_host"] == "100.101.102.103"
  assert saved["access_port"] == "9100"

  network = client.get("/api/admin/network", headers=operator).json()
  assert network["access_host"] == "100.101.102.103"
  assert network["access_port"] == "9100"


def test_access_host_accepts_tunnel_origin(client: TestClient) -> None:
  """Link tunnel copy về thường kèm dấu / cuối; phải cắt về đúng origin."""
  operator = auth(client, "operator", "dieuphoi123", "operator")
  saved = client.patch(
    "/api/admin/settings",
    json={"access_host": "https://abc-def-ghi.trycloudflare.com/"},
    headers=operator,
  ).json()
  assert saved["access_host"] == "https://abc-def-ghi.trycloudflare.com"

  # Dán cả đường dẫn thì chỉ giữ origin, nếu không sẽ ghép ra .../operator/operator.
  saved = client.patch(
    "/api/admin/settings",
    json={"access_host": "https://abc.trycloudflare.com/operator?x=1"},
    headers=operator,
  ).json()
  assert saved["access_host"] == "https://abc.trycloudflare.com"

  rejected = client.patch(
    "/api/admin/settings", json={"access_host": "ftp://abc.example.com"}, headers=operator,
  )
  assert rejected.status_code == 422


def test_tunnel_url_pattern_only_matches_ephemeral() -> None:
  """Địa chỉ trycloudflare chỉ sống một phiên nên phải dọn khi khởi động lại.

  Bước dọn lúc thoát không đủ: đóng cửa sổ console hay taskkill thì atexit không chạy.
  Nhưng mẫu nhận dạng phải hẹp, không được xoá nhầm cấu hình Tailscale hay tên miền riêng.
  """
  import sys
  sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
  from run_demo import TUNNEL_URL_PATTERN

  assert TUNNEL_URL_PATTERN.fullmatch("https://abc-def.trycloudflare.com")
  assert not TUNNEL_URL_PATTERN.fullmatch("100.68.116.20")
  assert not TUNNEL_URL_PATTERN.fullmatch("may-chu.tail1234.ts.net")
  assert not TUNNEL_URL_PATTERN.fullmatch("https://uav.example.com")


def test_build_base_url_skips_port_for_origin() -> None:
  """Tunnel phục vụ ở 443; ghép thêm cổng nội bộ vào là link hỏng."""
  from app.network import build_base_url

  assert build_base_url("https://abc.trycloudflare.com", 8000) == "https://abc.trycloudflare.com"
  assert build_base_url("https://abc.trycloudflare.com/", 8000) == "https://abc.trycloudflare.com"
  assert build_base_url("100.68.116.20", 8000) == "http://100.68.116.20:8000"
  assert build_base_url("may-chu.ts.net", "9100") == "http://may-chu.ts.net:9100"


# ---------- Tài khoản ----------

def test_profile_read_and_update(client: TestClient) -> None:
  customer = auth(client, "customer", "khachhang123", "customer")
  profile = client.get("/api/profile", headers=customer).json()
  assert profile["username"] == "customer"
  assert "password_hash" not in profile, "không được lộ mật khẩu băm"

  updated = client.patch("/api/profile", headers=customer, json={
    "full_name": "Nguyễn Văn An", "gender": "male", "date_of_birth": "1996-04-12",
    "email": "an@example.vn", "default_note": "Gọi trước khi tới",
  }).json()
  assert updated["full_name"] == "Nguyễn Văn An"
  assert updated["gender"] == "male"
  assert updated["default_note"] == "Gọi trước khi tới"

  assert client.patch("/api/profile", headers=customer, json={"gender": "khac"}).status_code == 400


def test_customer_cannot_grant_itself_staff_fields(client: TestClient) -> None:
  """Trường của điều phối viên bị lọc bỏ chứ không âm thầm ghi vào hồ sơ khách."""
  customer = auth(client, "customer", "khachhang123", "customer")
  response = client.patch("/api/profile", headers=customer, json={
    "employee_code": "DP-999", "job_title": "Giám đốc", "full_name": "Tên hợp lệ",
  })
  assert response.status_code == 200
  assert response.json()["employee_code"] == ""
  assert response.json()["full_name"] == "Tên hợp lệ"


def test_operator_duty_status(client: TestClient) -> None:
  operator = auth(client, "operator", "dieuphoi123", "operator")
  updated = client.patch("/api/profile", headers=operator, json={
    "employee_code": "DP-001", "job_title": "Điều phối viên", "duty_status": "BREAK",
  }).json()
  assert updated["employee_code"] == "DP-001"
  assert updated["duty_status"] == "BREAK"

  assert client.patch("/api/profile", headers=operator, json={"duty_status": "NGHI_TRUA"}).status_code == 400
  client.patch("/api/profile", headers=operator, json={"duty_status": "ON_DUTY"})


def test_display_name_change_reaches_session(client: TestClient) -> None:
  """Đổi tên hiển thị phải thấy ngay ở /auth/me, không đợi tới lần đăng nhập sau."""
  customer = auth(client, "customer", "khachhang123", "customer")
  client.patch("/api/profile", headers=customer, json={"display_name": "An Nguyễn"})
  assert client.get("/api/auth/me", headers=customer).json()["display_name"] == "An Nguyễn"
  client.patch("/api/profile", headers=customer, json={"display_name": "Nguyễn Văn An"})


def test_sessions_list_and_revoke(client: TestClient) -> None:
  first = auth(client, "customer", "khachhang123", "customer")
  second = auth(client, "customer", "khachhang123", "customer")

  sessions = client.get("/api/profile/sessions", headers=second).json()
  assert len(sessions) >= 2
  assert sum(1 for item in sessions if item["is_current"]) == 1
  assert all(item["device"] for item in sessions)

  current_id = next(item["session_id"] for item in sessions if item["is_current"])
  assert client.delete(f"/api/profile/sessions/{current_id}", headers=second).status_code == 404, \
    "không được tự đăng xuất mình bằng nút dành cho thiết bị khác"

  other_id = next(item["session_id"] for item in sessions if not item["is_current"])
  assert client.delete(f"/api/profile/sessions/{other_id}", headers=second).status_code == 200
  assert client.get("/api/profile", headers=first).status_code == 401, "phiên kia phải hết hiệu lực"


def test_password_change(client: TestClient) -> None:
  stale = auth(client, "customer", "khachhang123", "customer")
  active = auth(client, "customer", "khachhang123", "customer")

  assert client.post("/api/profile/password", headers=active, json={
    "current_password": "sai-mat-khau", "new_password": "matkhaumoi123",
  }).status_code == 400
  assert client.post("/api/profile/password", headers=active, json={
    "current_password": "khachhang123", "new_password": "khachhang123",
  }).status_code == 400, "mật khẩu mới phải khác mật khẩu cũ"
  assert client.post("/api/profile/password", headers=active, json={
    "current_password": "khachhang123", "new_password": "ngan",
  }).status_code == 422, "mật khẩu quá ngắn"

  changed = client.post("/api/profile/password", headers=active, json={
    "current_password": "khachhang123", "new_password": "matkhaumoi123",
  })
  assert changed.status_code == 200, changed.text
  assert changed.json()["signed_out_devices"] >= 1

  assert client.get("/api/profile", headers=active).status_code == 200, "thiết bị đang dùng vẫn giữ phiên"
  assert client.get("/api/profile", headers=stale).status_code == 401, "thiết bị khác phải đăng xuất"

  assert client.post("/api/auth/login", json={
    "username": "customer", "password": "khachhang123", "expected_role": "customer",
  }).status_code == 401
  # Trả lại mật khẩu gốc để các test khác và tài khoản demo vẫn dùng được.
  restored = auth(client, "customer", "matkhaumoi123", "customer")
  client.post("/api/profile/password", headers=restored, json={
    "current_password": "matkhaumoi123", "new_password": "khachhang123",
  })


def test_customer_cannot_read_network(client: TestClient) -> None:
  customer = auth(client, "customer", "khachhang123", "customer")
  assert client.get("/api/admin/network", headers=customer).status_code == 403
  assert client.get("/api/admin/firewall?port=8000", headers=customer).status_code == 403


def test_firewall_endpoint_shape(client: TestClient) -> None:
  operator = auth(client, "operator", "dieuphoi123", "operator")
  data = client.get("/api/admin/firewall?port=8000", headers=operator).json()

  assert data["state"] in {"allowed", "missing", "unknown"}
  assert data["port"] == 8000
  assert "8000" in data["command"], "lệnh gợi ý phải mở đúng cổng đang hỏi"
  assert "100.64.0.0/10" in data["command"], "phải phủ dải Tailscale"
  assert isinstance(data["rules"], list)

  assert client.get("/api/admin/firewall?port=0", headers=operator).status_code == 422


# ---------- Bộ tách kết quả netsh ----------

# Trích từ đầu ra thật của `netsh advfirewall firewall show rule name=all dir=in verbose`.
NETSH_SAMPLE = """
Rule Name:                            UAV UI
----------------------------------------------------------------------
Enabled:                              Yes
Direction:                            In
Profiles:                             Domain,Private,Public
LocalIP:                              Any
RemoteIP:                             Any
Protocol:                             TCP
LocalPort:                            8000
RemotePort:                           Any
Action:                               Allow

Rule Name:                            Chi cho mot may LAN
----------------------------------------------------------------------
Enabled:                              Yes
Direction:                            In
Profiles:                             Private
LocalIP:                              Any
RemoteIP:                             203.0.113.5/32
Protocol:                             TCP
LocalPort:                            9000
RemotePort:                           Any
Action:                               Allow

Rule Name:                            Da tat
----------------------------------------------------------------------
Enabled:                              No
Direction:                            In
Profiles:                             Private
RemoteIP:                             Any
Protocol:                             TCP
LocalPort:                            7000
Action:                               Allow
"""

# Windows tiếng Việt dịch cả nhãn lẫn giá trị nên không tài nào đọc hiểu được.
NETSH_LOCALIZED = """
Tên Quy tắc:                          UAV UI
----------------------------------------------------------------------
Đã bật:                               Có
Hành động:                            Cho phép
"""


def parse(text: str, port: int, monkeypatch, program: str = r"C:\python\python.exe") -> dict:
  from app import firewall
  firewall._cache.clear()
  monkeypatch.setattr(firewall.sys, "platform", "win32")
  monkeypatch.setattr(firewall.sys, "executable", program)
  monkeypatch.setattr(firewall, "_run_netsh", lambda: text)
  return firewall.check_port(port)


def test_netsh_parser_finds_matching_port(monkeypatch) -> None:
  result = parse(NETSH_SAMPLE, 8000, monkeypatch)
  assert result["state"] == "allowed"
  assert result["rules"] == ["UAV UI (Domain,Private,Public)"]


def test_netsh_parser_reports_missing_port(monkeypatch) -> None:
  """Cổng 7000 chỉ có rule đã tắt, còn 9000 bị giới hạn về một IP ngoài dải máy khách."""
  assert parse(NETSH_SAMPLE, 7000, monkeypatch)["state"] == "missing"
  assert parse(NETSH_SAMPLE, 9000, monkeypatch)["state"] == "missing"


def test_netsh_parser_matches_program_rule(monkeypatch) -> None:
  """Rule mở mọi cổng cho đúng file thực thi đang chạy server cũng được tính."""
  text = NETSH_SAMPLE + """
Rule Name:                            Python
----------------------------------------------------------------------
Enabled:                              Yes
Direction:                            In
Profiles:                             Private
RemoteIP:                             Any
Protocol:                             TCP
LocalPort:                            Any
Program:                              C:\\Python\\python.exe
Action:                               Allow
"""
  assert parse(text, 7000, monkeypatch)["state"] == "allowed"
  # Trình thông dịch khác thì rule đó không còn liên quan.
  assert parse(text, 7000, monkeypatch, program=r"D:\khac\python.exe")["state"] == "missing"


def test_netsh_parser_gives_up_on_other_languages(monkeypatch) -> None:
  """Không đọc hiểu được thì phải trả unknown, không được báo là thiếu rule."""
  assert parse(NETSH_LOCALIZED, 8000, monkeypatch)["state"] == "unknown"


def test_firewall_unknown_when_netsh_unavailable(monkeypatch) -> None:
  assert parse(None, 8000, monkeypatch)["state"] == "unknown"
