"""Kiểm tra tường lửa Windows có cho phép kết nối vào cổng đang phục vụ hay không.

Vì sao cần: máy khách nằm ngoài (điện thoại, máy trong VPN) bị tường lửa chặn thì
gói tin bị *thả im lặng*, trình duyệt chỉ báo `ERR_CONNECTION_TIMED_OUT` sau vài chục
giây — không có lấy một manh mối nào chỉ về phía máy chủ. Đổi cổng trong console càng
dễ dính, vì rule cũ thường gắn cứng một số cổng cụ thể.

Chỉ dùng thư viện chuẩn để `run_demo.py` nhập được mà không cần cài thêm gì.
"""

from __future__ import annotations

import ipaddress
import locale
import os
import re
import subprocess
import sys
import time
from typing import Any

# Dải địa chỉ được phép trong lệnh gợi ý: CGNAT của Tailscale cộng ba dải mạng riêng.
ALLOWED_REMOTE = "100.64.0.0/10,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"

# Dải mà máy khách thật sự sẽ đi vào: VPN kiểu Tailscale và ba dải mạng riêng.
CLIENT_NETWORKS = [ipaddress.ip_network(cidr) for cidr in ALLOWED_REMOTE.split(",")]

RULE_NAME = "UAV Delivery Demo"

# Gọi netsh mất khoảng một giây nên nhớ đệm lại; console hỏi lại mỗi lần gõ số cổng.
CACHE_SECONDS = 30.0
_cache: dict[int, tuple[float, dict[str, Any]]] = {}

_DASHES = re.compile(r"^-{5,}$")
_FIELD = re.compile(r"^([A-Za-z][A-Za-z ]+):\s*(.*)$")


def suggest_command(port: int) -> str:
  """Lệnh PowerShell (cần quyền Administrator) mở đúng cổng cho VPN và mạng nội bộ."""
  return (
    f'New-NetFirewallRule -DisplayName "{RULE_NAME} ({port})" -Direction Inbound '
    f'-Protocol TCP -LocalPort {port} -Action Allow -Profile Any '
    f'-RemoteAddress {ALLOWED_REMOTE}'
  )


def _run_netsh() -> str | None:
  """Đọc toàn bộ rule inbound.

  Bắt buộc dùng `netsh`, KHÔNG dùng `Get-NetFirewallRule`: cmdlet đó đòi quyền
  Administrator và khi thiếu quyền nó trả về danh sách rỗng thay vì báo lỗi, khiến
  ta kết luận nhầm là "máy không có rule nào". `netsh` đọc được đầy đủ khi chạy
  bằng tài khoản thường.
  """
  try:
    result = subprocess.run(
      ["netsh", "advfirewall", "firewall", "show", "rule", "name=all", "dir=in", "verbose"],
      capture_output=True,
      timeout=20,
      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
  except (OSError, subprocess.SubprocessError):
    return None
  if result.returncode != 0:
    return None
  encoding = locale.getpreferredencoding(False) or "utf-8"
  return result.stdout.decode(encoding, errors="replace")


def _blocks(text: str) -> list[tuple[str, dict[str, str]]]:
  """Tách đầu ra netsh thành từng rule: tên rule nằm ngay trên dòng gạch ngang."""
  lines = text.splitlines()
  starts = [index for index, line in enumerate(lines) if _DASHES.match(line.strip())]
  blocks: list[tuple[str, dict[str, str]]] = []

  for order, index in enumerate(starts):
    if index == 0:
      continue
    name = lines[index - 1].split(":", 1)[-1].strip()
    end = starts[order + 1] - 1 if order + 1 < len(starts) else len(lines)
    fields: dict[str, str] = {}
    for line in lines[index + 1:end]:
      match = _FIELD.match(line.strip())
      if match:
        fields[match.group(1).strip()] = match.group(2).strip()
    blocks.append((name, fields))
  return blocks


def _ports_of(value: str) -> set[str]:
  return {part.strip() for part in value.split(",") if part.strip()}


def _covers_client(value: str) -> bool:
  """Rule có nhận kết nối từ dải mà máy khách sẽ đi vào không.

  Một rule giới hạn RemoteIP vào đúng một máy trong LAN thì vô dụng với máy trong
  VPN, nên không được tính là đã mở. Token nào không hiểu được (`LocalSubnet`,
  khoảng địa chỉ dạng a-b) thì coi như có thể phủ, để không kết luận quá tay.
  """
  value = value.strip()
  if not value or value == "Any":
    return True
  for token in value.split(","):
    token = token.strip()
    try:
      network = ipaddress.ip_network(token, strict=False)
    except ValueError:
      return True
    if any(network.overlaps(client) for client in CLIENT_NETWORKS):
      return True
  return False


def _matches(fields: dict[str, str], port: int, program: str) -> bool:
  if fields.get("Enabled") != "Yes" or fields.get("Action") != "Allow":
    return False
  if fields.get("Protocol") not in {"TCP", "Any"}:
    return False
  if not _covers_client(fields.get("RemoteIP", "Any")):
    return False

  ports = _ports_of(fields.get("LocalPort", ""))
  if str(port) in ports:
    return True
  # Rule gắn theo chương trình mở mọi cổng cho đúng file thực thi đang chạy server.
  rule_program = fields.get("Program", "")
  return bool(rule_program) and "Any" in ports and os.path.normcase(rule_program) == program


def check_port(port: int, *, refresh: bool = False) -> dict[str, Any]:
  """Trả về trạng thái tường lửa cho một cổng TCP.

  `state` là "allowed", "missing" hoặc "unknown". Khi không chắc thì luôn trả
  "unknown" — báo nhầm "missing" sẽ đẩy người dùng đi mở tường lửa một cách vô ích,
  và tệ hơn là che mất nguyên nhân thật.
  """
  cached = _cache.get(port)
  if cached and not refresh and time.monotonic() - cached[0] < CACHE_SECONDS:
    return cached[1]

  result = _inspect(port)
  _cache[port] = (time.monotonic(), result)
  return result


def _inspect(port: int) -> dict[str, Any]:
  base = {"port": port, "platform": sys.platform, "rules": [], "command": suggest_command(port)}

  if sys.platform != "win32":
    return {**base, "state": "unknown",
            "hint": "Chỉ kiểm tra được trên Windows. Trên Linux hãy xem ufw hoặc firewalld."}

  text = _run_netsh()
  if text is None:
    return {**base, "state": "unknown", "hint": "Không chạy được netsh để đọc cấu hình tường lửa."}

  blocks = _blocks(text)
  # Đầu ra netsh bị dịch theo ngôn ngữ Windows. Không thấy các nhãn tiếng Anh quen
  # thuộc nghĩa là không đọc hiểu được, chứ không phải máy thiếu rule.
  if not any("Action" in fields and "LocalPort" in fields for _, fields in blocks):
    return {**base, "state": "unknown",
            "hint": "Không đọc được kết quả netsh trên ngôn ngữ Windows này."}

  program = os.path.normcase(sys.executable)
  # Kèm profile để điều phối viên tự thấy rule có áp cho card mạng đang dùng hay không.
  matched = [
    f"{name} ({fields.get('Profiles', 'Any')})"
    for name, fields in blocks if _matches(fields, port, program)
  ]

  if matched:
    return {**base, "state": "allowed", "rules": matched,
            "hint": f"Cổng {port} đã được tường lửa cho phép."}
  return {**base, "state": "missing",
          "hint": f"Chưa có rule nào cho phép kết nối vào cổng {port}. "
                  "Máy ngoài sẽ bị timeout mà không có thông báo lỗi."}
