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
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
# Dùng chung phần dò địa chỉ và kiểm tra tường lửa với backend. Hai module này chỉ
# nhập thư viện chuẩn nên không kéo theo fastapi.
sys.path.insert(0, str(BACKEND_DIR))
SIMULATOR_DIR = ROOT / "uav_simulator"
DEFAULT_DB = ROOT / "data" / "uav_demo.db"

SIMULATOR_API_KEY = "demo-sim-key"
HOME_LAT = "21.0278"
HOME_LON = "105.8342"

processes: list[subprocess.Popen] = []
# Địa chỉ công bố trước khi tunnel ghi đè, để trả lại nguyên trạng lúc thoát.
previous_access_host: str | None = None


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


def write_access_host(value: str) -> None:
  """Ghi địa chỉ công bố thẳng vào SQLite.

  Backend đã chạy rồi nhưng gọi `PATCH /api/admin/settings` thì phải nhúng mật khẩu điều
  phối vào launcher — không đáng, trong khi đọc/ghi bảng settings ở đây vốn đã làm sẵn.
  """
  if not DEFAULT_DB.exists():
    return
  try:
    with sqlite3.connect(DEFAULT_DB) as conn:
      conn.execute("UPDATE settings SET value = ? WHERE key = 'access_host'", (value,))
  except sqlite3.Error:
    pass


def saved_access() -> tuple[str, str]:
  """Đọc host/cổng mà điều phối viên đã chọn trong console ở lần chạy trước.

  Đọc thẳng SQLite bằng thư viện chuẩn vì backend chưa khởi động ở thời điểm này.
  """
  if not DEFAULT_DB.exists():
    return "", ""
  try:
    import sqlite3
    with sqlite3.connect(DEFAULT_DB) as conn:
      rows = dict(conn.execute(
        "SELECT key, value FROM settings WHERE key IN ('access_host', 'access_port')"
      ).fetchall())
  except sqlite3.Error:
    return "", ""
  return rows.get("access_host", ""), rows.get("access_port", "")


# ---------- Quản lý tiến trình con ----------

def spawn(command: list[str], cwd: Path, env: dict[str, str], label: str) -> subprocess.Popen:
  print(f"Khởi động {label} ...")
  process = subprocess.Popen(command, cwd=str(cwd), env=env)
  processes.append(process)
  return process


def shutdown() -> None:
  # URL tunnel đổi mới mỗi lần chạy. Để nguyên trong cấu hình thì lần sau console phát ra
  # một liên kết đã chết mà không ai hiểu vì sao, nên phải trả lại giá trị cũ.
  global previous_access_host
  if previous_access_host is not None:
    write_access_host(previous_access_host)
    previous_access_host = None

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


# ---------- Đường truy cập công khai ----------

TUNNEL_URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def ensure_cloudflared(assume_yes: bool) -> str | None:
  """Tìm cloudflared, chưa có thì xin phép tải. Không có cũng không sao, chỉ mất tunnel."""
  try:
    from app import tunnel
  except Exception:
    return None

  found = tunnel.find_cloudflared()
  if found:
    return found

  url = tunnel.download_url()
  if not url:
    print(f"Chưa hỗ trợ tự tải cloudflared cho nền tảng này.\n{tunnel.MANUAL_HINT}")
    return None

  print("\nCần cloudflared để mở đường truy cập công khai. Máy này chưa có.")
  print(f"Tải từ trang phát hành chính thức của Cloudflare:\n  {url}")
  if not assume_yes:
    # Tải file thực thi về máy người khác thì phải hỏi, không bao giờ làm ngầm.
    try:
      answer = input("Tải về thư mục tools/ ? [y/N] ").strip().lower()
    except EOFError:
      answer = ""
    if answer not in {"y", "yes"}:
      print(f"Bỏ qua tunnel. {tunnel.MANUAL_HINT}")
      return None

  print("Đang tải cloudflared ...")
  try:
    path = tunnel.download_cloudflared()
  except RuntimeError as error:
    print(error)
    return None
  print(f"Đã tải xong: {path}")
  return path


def start_tunnel(binary: str, port: int) -> str | None:
  """Chạy cloudflared và trả về URL công khai, hoặc None nếu không dựng được."""
  print("Đang mở đường truy cập công khai qua Cloudflare ...")
  process = subprocess.Popen(
    [binary, "tunnel", "--url", f"http://127.0.0.1:{port}"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
    errors="replace",
  )
  processes.append(process)

  found: dict[str, str] = {}
  ready = threading.Event()

  def read_output() -> None:
    # Phải đọc tới hết stream kể cả sau khi đã tìm thấy URL: ngừng đọc thì pipe đầy và
    # cloudflared bị chặn ghi, tunnel đang chạy sẽ đứng hình giữa chừng.
    for line in process.stdout or []:
      if "url" not in found:
        match = TUNNEL_URL_PATTERN.search(line)
        if match:
          found["url"] = match.group(0)
          ready.set()
    ready.set()

  threading.Thread(target=read_output, daemon=True).start()

  if not ready.wait(timeout=30) or "url" not in found:
    print("Không lấy được địa chỉ công khai sau 30 giây. Bỏ qua tunnel.")
    return None
  return found["url"]


def verify_tunnel(url: str) -> bool:
  """Cloudflare cần vài giây để tuyến sẵn sàng.

  In link ra sớm quá thì người bấm vào gặp 502 rồi tưởng demo hỏng, nên xác minh bằng
  đúng đường công cộng trước khi công bố.
  """
  return wait_for_health(f"{url}/health", timeout=20.0)


# ---------- In hướng dẫn ----------

def print_links(port: int, access_host: str, tunnel_url: str = "") -> None:
  line = "=" * 60
  print(f"\n{line}\n UAV DELIVERY DEMO\n{line}")

  if tunnel_url:
    print(f"Qua Internet (tunnel)     : {tunnel_url}/")
    print(f"  Console điều phối       : {tunnel_url}/operator")
    print("  Ai có link này đều vào được — chỉ bật khi đang demo.")

  print(f"PC  - Dashboard điều phối : http://localhost:{port}/operator")
  print(f"PC  - App khách hàng      : http://localhost:{port}/")

  if access_host and access_host != tunnel_url:
    try:
      from app.network import build_base_url
      base = build_base_url(access_host, port)
    except Exception:
      base = f"http://{access_host}:{port}"
    print(f"Địa chỉ đã chọn           : {base}/")

  # Liệt kê mọi card mạng, không chỉ tuyến ra Internet: địa chỉ VPN phải hiện ra
  # ngay cả khi điều phối viên chưa lưu lựa chọn nào trong console.
  try:
    from app.network import list_addresses
    addresses = [item for item in list_addresses() if item["address"] != access_host]
  except Exception:
    addresses = []

  for item in addresses:
    nhan = {"vpn": "Qua VPN", "lan": "Cùng Wi-Fi/LAN", "public": "Địa chỉ công cộng"}.get(item["kind"], "Khác")
    print(f"{nhan:<26}: http://{item['address']}:{port}/")
  if not addresses and not access_host:
    print("Không tự tìm được địa chỉ mạng. Chạy ipconfig (Windows) hoặc ip addr (Linux).")

  print(f"Tài liệu API (Swagger)    : http://localhost:{port}/docs")
  print(f"\nKhách hàng : customer / khachhang123")
  print(f"Điều phối  : operator / dieuphoi123")
  print(f"\nNhấn Ctrl+C để dừng toàn bộ demo.\n{line}\n")


def warn_if_firewall_blocks(port: int) -> None:
  """Cảnh báo khi tường lửa chưa mở cổng đang dùng.

  Máy ngoài gặp trường hợp này chỉ thấy trình duyệt quay vòng rồi timeout, không có
  lấy một dòng lỗi nào chỉ về máy chủ — nên phải nói trước ở đây. Không chắc thì im
  lặng, tuyệt đối không doạ người dùng đi mở tường lửa một cách vô ích.
  """
  try:
    from app.firewall import check_port
    status = check_port(port)
  except Exception:
    return
  if status["state"] != "missing":
    return

  line = "!" * 60
  print(f"\n{line}")
  print(f"CẢNH BÁO: tường lửa chưa mở cổng {port}.")
  print("Máy khác trong VPN hoặc LAN sẽ bị timeout mà không hiện lỗi gì.")
  print("Mở PowerShell bằng quyền Administrator rồi chạy:\n")
  print(f"  {status['command']}\n")
  print(line)


# ---------- Điểm vào ----------

def main() -> None:
  global previous_access_host

  parser = argparse.ArgumentParser(description="Khởi động UAV Delivery Demo (không cần Docker).")
  parser.add_argument("--port", type=int, default=None,
                      help="Cổng phục vụ. Bỏ trống thì dùng cổng đã lưu trong console, mặc định 8000")
  parser.add_argument("--host", default="0.0.0.0", help="Địa chỉ lắng nghe (mặc định 0.0.0.0)")
  parser.add_argument("--no-browser", action="store_true", help="Không tự mở trình duyệt")
  parser.add_argument("--no-simulator", action="store_true", help="Không chạy UAV simulator")
  parser.add_argument("--uavs", type=int, default=3, choices=range(1, 10), metavar="1-9",
                      help="Số UAV mô phỏng chạy song song (mặc định 3)")
  parser.add_argument("--tunnel", action="store_true",
                      help="Mở đường truy cập công khai qua Cloudflare Tunnel (máy nào có link cũng vào được)")
  parser.add_argument("--yes", action="store_true",
                      help="Tự đồng ý tải cloudflared nếu máy chưa có, không hỏi lại")
  parser.add_argument("--no-install", action="store_true", help="Không tự cài thư viện còn thiếu")
  parser.add_argument("--reset", action="store_true", help="Xoá dữ liệu cũ trước khi chạy")
  args = parser.parse_args()

  check_python()
  ensure_dependencies(auto_install=not args.no_install)

  if args.reset and DEFAULT_DB.parent.exists():
    shutil.rmtree(DEFAULT_DB.parent)
    print("Đã xoá dữ liệu demo cũ.")
  DEFAULT_DB.parent.mkdir(parents=True, exist_ok=True)

  # Cờ dòng lệnh luôn thắng; sau đó tới lựa chọn đã lưu trong console; cuối cùng là mặc định.
  access_host, access_port = saved_access()

  # Địa chỉ trycloudflare.com chỉ sống trong một phiên chạy. Dọn ở đây chứ không chỉ
  # trông vào bước dọn lúc thoát: đóng cửa sổ console hay taskkill thì atexit không chạy,
  # và lần sau console sẽ phát ra một liên kết đã chết mà không ai hiểu vì sao.
  if access_host and TUNNEL_URL_PATTERN.fullmatch(access_host):
    print("Xoá địa chỉ tunnel của lần chạy trước (mỗi lần chạy được cấp địa chỉ mới).")
    write_access_host("")
    access_host = ""
  port = args.port if args.port is not None else (int(access_port) if access_port.isdigit() else 8000)
  if args.port is None and access_port.isdigit():
    print(f"Dùng cổng {port} theo cấu hình đã lưu trong console.")

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
    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", args.host, "--port", str(port)],
    BACKEND_DIR, backend_env, "backend",
  )

  health_url = f"http://127.0.0.1:{port}/health"
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
        "BACKEND_URL": f"http://127.0.0.1:{port}",
        "SIMULATOR_API_KEY": SIMULATOR_API_KEY,
        "UAV_ID": uav_id,
        "HOME_LAT": HOME_LAT,
        "HOME_LON": HOME_LON,
        "FLIGHT_STEPS": "35",
        "STEP_SECONDS": "1.0",
        "PYTHONUNBUFFERED": "1",
      }
      spawn([sys.executable, "simulator.py"], SIMULATOR_DIR, simulator_env, uav_id)

  tunnel_url = ""
  if args.tunnel:
    binary = ensure_cloudflared(args.yes)
    if binary:
      tunnel_url = start_tunnel(binary, port) or ""
    if tunnel_url:
      if verify_tunnel(tunnel_url):
        print("Đường truy cập công khai đã sẵn sàng.")
      else:
        print("Chưa xác minh được đường công khai — hãy thử lại sau vài giây.")
      # Console dùng địa chỉ này để phát liên kết cho máy khách.
      previous_access_host = access_host
      write_access_host(tunnel_url)

  print_links(port, access_host, tunnel_url)
  # Tunnel nối ra ngoài từ chính máy này nên không có kết nối đến để tường lửa chặn.
  if not tunnel_url:
    warn_if_firewall_blocks(port)
  if not args.no_browser:
    webbrowser.open(f"http://localhost:{port}/operator")

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
