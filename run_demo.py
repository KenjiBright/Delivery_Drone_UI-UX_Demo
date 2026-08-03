#!/usr/bin/env python3
"""Khởi động toàn bộ UAV Delivery Demo bằng một lệnh duy nhất.

Chạy backend (FastAPI, kèm luôn giao diện web) và UAV simulator như hai tiến
trình con, rồi in ra địa chỉ để điện thoại cùng Wi-Fi truy cập. Dừng bằng Ctrl+C.

    python run_demo.py
"""

from __future__ import annotations

import argparse
import atexit
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
SIMULATOR_DIR = ROOT / "uav_simulator"
DEFAULT_DB = ROOT / "data" / "uav_demo.db"

SIMULATOR_API_KEY = "demo-sim-key"
HOME_LAT = "21.0278"
HOME_LON = "105.8342"

processes: list[subprocess.Popen] = []


# ---------- Chuẩn bị môi trường ----------

def check_python() -> None:
  if sys.version_info < (3, 10):
    sys.exit(f"Cần Python 3.10 trở lên. Bản đang dùng: {sys.version.split()[0]}")


def missing_packages() -> list[str]:
  import importlib.util
  return [name for name in ("fastapi", "uvicorn", "httpx") if importlib.util.find_spec(name) is None]


def ensure_dependencies(auto_install: bool) -> None:
  missing = missing_packages()
  if not missing:
    return
  print(f"Thiếu thư viện: {', '.join(missing)}")
  if not auto_install:
    sys.exit(f"Hãy chạy: {sys.executable} -m pip install -r requirements.txt")
  print("Đang cài đặt từ requirements.txt ...")
  result = subprocess.run(
    [sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")],
  )
  if result.returncode != 0:
    sys.exit("Cài đặt thư viện thất bại. Hãy kiểm tra kết nối mạng rồi thử lại.")
  if missing_packages():
    sys.exit("Cài xong nhưng vẫn thiếu thư viện. Hãy kiểm tra lại môi trường Python.")


def lan_ip() -> str | None:
  """Tìm IPv4 của máy trong mạng LAN.

  Mở một UDP socket tới địa chỉ ngoài để hệ điều hành tự chọn card mạng mặc
  định. Không gửi gói tin nào nên không cần Internet thật.
  """
  probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  try:
    probe.connect(("8.8.8.8", 80))
    return probe.getsockname()[0]
  except OSError:
    return None
  finally:
    probe.close()


# ---------- Quản lý tiến trình con ----------

def spawn(command: list[str], cwd: Path, env: dict[str, str], label: str) -> subprocess.Popen:
  print(f"Khởi động {label} ...")
  process = subprocess.Popen(command, cwd=str(cwd), env=env)
  processes.append(process)
  return process


def shutdown() -> None:
  for process in processes:
    if process.poll() is None:
      process.terminate()
  for process in processes:
    try:
      process.wait(timeout=5)
    except subprocess.TimeoutExpired:
      process.kill()
  processes.clear()


def wait_for_health(url: str, timeout: float = 30.0) -> bool:
  """Chờ backend sẵn sàng trước khi bật simulator.

  Thay cho healthcheck của Docker Compose trong kiến trúc cũ.
  """
  deadline = time.monotonic() + timeout
  while time.monotonic() < deadline:
    if processes and processes[0].poll() is not None:
      return False
    try:
      with urllib.request.urlopen(url, timeout=2) as response:
        if response.status == 200:
          return True
    except (urllib.error.URLError, OSError):
      pass
    time.sleep(0.4)
  return False


# ---------- In hướng dẫn ----------

def print_links(port: int, ip: str | None) -> None:
  line = "=" * 60
  print(f"\n{line}\n UAV DELIVERY DEMO\n{line}")
  print(f"PC  - Dashboard điều phối : http://localhost:{port}/operator")
  print(f"PC  - App khách hàng      : http://localhost:{port}/")
  if ip:
    print(f"Điện thoại cùng Wi-Fi     : http://{ip}:{port}/")
    print(f"Dashboard qua mạng LAN    : http://{ip}:{port}/operator")
  else:
    print("Không tự tìm được IP LAN. Chạy ipconfig (Windows) hoặc ip addr (Linux).")
  print(f"Tài liệu API (Swagger)    : http://localhost:{port}/docs")
  print(f"\nKhách hàng : customer / khachhang123")
  print(f"Điều phối  : operator / dieuphoi123")
  print(f"\nChỉ cần mở cổng {port} trên tường lửa.")
  print(f"Nhấn Ctrl+C để dừng toàn bộ demo.\n{line}\n")


# ---------- Điểm vào ----------

def main() -> None:
  parser = argparse.ArgumentParser(description="Khởi động UAV Delivery Demo (không cần Docker).")
  parser.add_argument("--port", type=int, default=8000, help="Cổng phục vụ (mặc định 8000)")
  parser.add_argument("--host", default="0.0.0.0", help="Địa chỉ lắng nghe (mặc định 0.0.0.0)")
  parser.add_argument("--no-browser", action="store_true", help="Không tự mở trình duyệt")
  parser.add_argument("--no-simulator", action="store_true", help="Không chạy UAV simulator")
  parser.add_argument("--uavs", type=int, default=3, choices=range(1, 10), metavar="1-9",
                      help="Số UAV mô phỏng chạy song song (mặc định 3)")
  parser.add_argument("--no-install", action="store_true", help="Không tự cài thư viện còn thiếu")
  parser.add_argument("--reset", action="store_true", help="Xoá dữ liệu cũ trước khi chạy")
  args = parser.parse_args()

  check_python()
  ensure_dependencies(auto_install=not args.no_install)

  if args.reset and DEFAULT_DB.parent.exists():
    shutil.rmtree(DEFAULT_DB.parent)
    print("Đã xoá dữ liệu demo cũ.")
  DEFAULT_DB.parent.mkdir(parents=True, exist_ok=True)

  atexit.register(shutdown)
  signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
  if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

  backend_env = {
    **os.environ,
    "DATABASE_PATH": str(DEFAULT_DB),
    "SIMULATOR_API_KEY": SIMULATOR_API_KEY,
    "HOME_LAT": HOME_LAT,
    "HOME_LON": HOME_LON,
    "PYTHONUNBUFFERED": "1",
  }
  spawn(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", args.host, "--port", str(args.port)],
    BACKEND_DIR, backend_env, "backend",
  )

  health_url = f"http://127.0.0.1:{args.port}/health"
  if not wait_for_health(health_url):
    shutdown()
    sys.exit("Backend không khởi động được. Xem thông báo lỗi phía trên.")
  print("Backend đã sẵn sàng.")

  if not args.no_simulator:
    # Mỗi UAV là một tiến trình riêng, đúng như khi thay bằng thiết bị bay thật.
    for index in range(1, args.uavs + 1):
      uav_id = f"UAV-{index:02d}"
      simulator_env = {
        **os.environ,
        "BACKEND_URL": f"http://127.0.0.1:{args.port}",
        "SIMULATOR_API_KEY": SIMULATOR_API_KEY,
        "UAV_ID": uav_id,
        "HOME_LAT": HOME_LAT,
        "HOME_LON": HOME_LON,
        "FLIGHT_STEPS": "35",
        "STEP_SECONDS": "1.0",
        "PYTHONUNBUFFERED": "1",
      }
      spawn([sys.executable, "simulator.py"], SIMULATOR_DIR, simulator_env, uav_id)

  print_links(args.port, lan_ip())
  if not args.no_browser:
    webbrowser.open(f"http://localhost:{args.port}/operator")

  # Giữ tiến trình chính sống; thoát nếu một tiến trình con chết bất thường.
  try:
    while True:
      for process in processes:
        if process.poll() is not None:
          print("Một tiến trình con đã dừng. Đang tắt demo.")
          return
      time.sleep(1)
  except KeyboardInterrupt:
    print("\nĐang dừng demo ...")


if __name__ == "__main__":
  main()
