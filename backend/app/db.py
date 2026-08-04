"""Kết nối SQLite, khai báo bảng và dữ liệu mẫu."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .security import make_password

# Ghi vào SQLite được tuần tự hoá để tránh tranh chấp giữa các request đồng thời.
DB_LOCK = asyncio.Lock()

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "./uav_demo.db"))
DEFAULT_HOME_LAT = float(os.getenv("HOME_LAT", "21.0278"))
DEFAULT_HOME_LON = float(os.getenv("HOME_LON", "105.8342"))

# Vòng đời đơn hàng, dùng để kiểm tra chuyển trạng thái hợp lệ.
ORDER_FLOW = ["PENDING", "CONFIRMED", "ASSIGNED", "DISPATCHED", "IN_FLIGHT", "ARRIVED", "DELIVERED", "RETURNING", "COMPLETED"]
ORDER_CLOSED = {"COMPLETED", "CANCELLED"}


def utc_now() -> str:
  return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
  DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
  conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
  conn.row_factory = sqlite3.Row
  conn.execute("PRAGMA foreign_keys = ON")
  return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  username TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  role TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  phone TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  price INTEGER NOT NULL,
  weight_kg REAL NOT NULL,
  icon TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'Khác',
  active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS orders (
  id TEXT PRIMARY KEY,
  customer_username TEXT NOT NULL,
  items_json TEXT NOT NULL,
  total_price INTEGER NOT NULL,
  total_weight_kg REAL NOT NULL,
  delivery_lat REAL NOT NULL,
  delivery_lon REAL NOT NULL,
  delivery_address TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL,
  assigned_uav TEXT,
  verification_code TEXT NOT NULL,
  rating INTEGER,
  review TEXT,
  cancel_reason TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  dispatched_at TEXT,
  completed_at TEXT
);

CREATE TABLE IF NOT EXISTS uavs (
  id TEXT PRIMARY KEY,
  model TEXT NOT NULL DEFAULT 'Demo Quad',
  status TEXT NOT NULL,
  battery REAL NOT NULL,
  lat REAL NOT NULL,
  lon REAL NOT NULL,
  altitude REAL NOT NULL,
  speed REAL NOT NULL,
  heading REAL NOT NULL,
  active_order_id TEXT,
  max_payload_kg REAL NOT NULL DEFAULT 2.5,
  note TEXT NOT NULL DEFAULT '',
  last_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id TEXT NOT NULL,
  status TEXT NOT NULL,
  actor TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_order ON order_events(order_id);

CREATE TABLE IF NOT EXISTS addresses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL,
  label TEXT NOT NULL,
  address TEXT NOT NULL,
  lat REAL NOT NULL,
  lon REAL NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_addresses_user ON addresses(username);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""

SEED_USERS = [
  ("customer", "Nguyễn Văn An", "customer", "khachhang123", "0901234567"),
  ("operator", "Trần Thị Điều Phối", "operator", "dieuphoi123", "0907654321"),
]

SEED_PRODUCTS = [
  ("MED001", "Hộp sơ cứu", "Bộ sơ cứu nhỏ gọn, băng gạc và sát trùng", 250_000, 0.80, "medkit", "Y tế"),
  ("MED002", "Thuốc kê đơn", "Túi thuốc niêm phong từ nhà thuốc", 180_000, 0.30, "pill", "Y tế"),
  ("DOC001", "Phong bì tài liệu", "Phong bì A4 chống thấm", 80_000, 0.35, "document", "Tài liệu"),
  ("DOC002", "Hợp đồng hoả tốc", "Kẹp tài liệu ký gấp trong ngày", 150_000, 0.50, "document", "Tài liệu"),
  ("FOOD001", "Suất ăn nóng", "Suất cơm đóng hộp giữ nhiệt", 120_000, 1.10, "food", "Đồ ăn"),
  ("FOOD002", "Cà phê mang đi", "Hai ly cà phê có nắp chống tràn", 70_000, 0.60, "coffee", "Đồ ăn"),
  ("PART001", "Linh kiện IoT", "Hộp cảm biến và mạch nhúng", 450_000, 0.65, "chip", "Linh kiện"),
  ("PART002", "Pin dự phòng", "Pin Li-Po đóng gói an toàn", 320_000, 0.90, "battery", "Linh kiện"),
]

SEED_UAVS = ["UAV-01", "UAV-02", "UAV-03"]

DEFAULT_SETTINGS = {
  "home_lat": str(DEFAULT_HOME_LAT),
  "home_lon": str(DEFAULT_HOME_LON),
  "max_payload_kg": "2.5",
  "low_battery_threshold": "30",
  "service_name": "UAV Delivery",
  # Đường truy cập công bố cho máy khách. Trống = dùng đúng host trình duyệt đang mở.
  "access_host": "",
  "access_port": "",
}


def init_db() -> None:
  with connect() as conn:
    conn.executescript(SCHEMA)
    now = utc_now()

    for username, display_name, role, password, phone in SEED_USERS:
      conn.execute(
        "INSERT OR IGNORE INTO users (username, display_name, role, password_hash, phone, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (username, display_name, role, make_password(password), phone, now),
      )

    for product_id, name, description, price, weight, icon, category in SEED_PRODUCTS:
      conn.execute(
        "INSERT OR IGNORE INTO products (id, name, description, price, weight_kg, icon, category, active) VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
        (product_id, name, description, price, weight, icon, category),
      )

    for uav_id in SEED_UAVS:
      conn.execute(
        """INSERT OR IGNORE INTO uavs (id, model, status, battery, lat, lon, altitude, speed, heading, active_order_id, max_payload_kg, note, last_seen)
        VALUES (?, 'Demo Quad X4', 'AVAILABLE', 96.0, ?, ?, 0.0, 0.0, 0.0, NULL, 2.5, '', ?)""",
        (uav_id, DEFAULT_HOME_LAT, DEFAULT_HOME_LON, now),
      )

    for key, value in DEFAULT_SETTINGS.items():
      conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))

    conn.commit()


# ---------- Đọc/ghi cấu hình ----------

def get_settings(conn: sqlite3.Connection) -> dict[str, str]:
  return {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM settings")}


def home_position(conn: sqlite3.Connection) -> tuple[float, float]:
  settings = get_settings(conn)
  return float(settings.get("home_lat", DEFAULT_HOME_LAT)), float(settings.get("home_lon", DEFAULT_HOME_LON))


# ---------- Chuyển đổi bản ghi ----------

def row_to_order(row: sqlite3.Row) -> dict[str, Any]:
  result = dict(row)
  result["items"] = json.loads(result.pop("items_json"))
  return result


def new_order_id() -> str:
  # Bốn chữ số ngẫu nhiên chứ không phải hai: phần thời gian chỉ tới giây, mà hai chữ
  # số chỉ cho 90 khả năng nên hai đơn đặt trong cùng một giây đã đủ đụng khoá chính.
  return f"OD{datetime.now().strftime('%y%m%d%H%M%S')}{secrets.randbelow(9000) + 1000}"


def log_event(conn: sqlite3.Connection, order_id: str, status: str, actor: str, note: str = "") -> None:
  """Ghi lại mọi lần đổi trạng thái để console có nhật ký truy vết."""
  conn.execute(
    "INSERT INTO order_events (order_id, status, actor, note, created_at) VALUES (?, ?, ?, ?, ?)",
    (order_id, status, actor, note, utc_now()),
  )
