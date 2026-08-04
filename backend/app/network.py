"""Dò các địa chỉ IP mà máy chủ đang có, để console chọn đường truy cập.

Mục tiêu là chạy được cả khi máy nằm sau router phát DHCP tuỳ hứng lẫn khi máy
tham gia một VPN như Tailscale hay WireGuard. Chỉ dùng thư viện chuẩn: không đọc
được tên card mạng trên mọi hệ điều hành, nên phân loại dựa trên dải địa chỉ.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Any

# Địa chỉ dùng để hỏi hệ điều hành "đi tới đây thì ra bằng card nào".
# Không gói tin nào được gửi đi vì UDP connect() chỉ ghi nhận tuyến đường.
ROUTE_PROBES = [
  ("8.8.8.8", "default"),        # tuyến ra Internet — thường là Wi-Fi/LAN
  ("100.100.100.100", "tailscale"),  # DNS nội bộ của Tailscale
  ("10.0.0.1", "private-10"),
  ("192.168.1.1", "private-192"),
]

# CGNAT 100.64.0.0/10: Tailscale cấp địa chỉ trong dải này, gần như không dùng ở LAN nhà.
TAILSCALE_NET = ipaddress.ip_network("100.64.0.0/10")


def _probe(target: str) -> str | None:
  probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  try:
    probe.connect((target, 80))
    return probe.getsockname()[0]
  except OSError:
    return None
  finally:
    probe.close()


def _host_addresses() -> list[str]:
  """Mọi IPv4 mà tên máy phân giải ra — bắt được cả card VPN đang bật."""
  try:
    infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
  except OSError:
    return []
  return [info[4][0] for info in infos]


def _classify(address: str, via: str | None) -> dict[str, Any] | None:
  try:
    ip = ipaddress.ip_address(address)
  except ValueError:
    return None
  if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
    return None

  if ip in TAILSCALE_NET:
    kind, hint = "vpn", "Tailscale — dùng được ở mọi mạng, địa chỉ không đổi"
  elif via == "tailscale":
    kind, hint = "vpn", "Ra qua tuyến VPN"
  elif ip.is_private:
    kind, hint = "lan", "Mạng nội bộ hoặc VPN dạng WireGuard — phụ thuộc router"
  else:
    kind, hint = "public", "Địa chỉ công cộng — chỉ dùng khi bạn hiểu rủi ro"

  return {"address": address, "kind": kind, "hint": hint, "is_default": via == "default"}


def list_addresses() -> list[dict[str, Any]]:
  """Danh sách địa chỉ truy cập được, VPN xếp trước vì đó là lựa chọn ổn định nhất."""
  found: dict[str, dict[str, Any]] = {}

  for target, via in ROUTE_PROBES:
    address = _probe(target)
    if not address:
      continue
    entry = _classify(address, via)
    # Tuyến mặc định được ưu tiên ghi đè để giữ cờ is_default.
    if entry and (address not in found or entry["is_default"]):
      found[address] = entry

  for address in _host_addresses():
    if address not in found:
      entry = _classify(address, None)
      if entry:
        found[address] = entry

  order = {"vpn": 0, "lan": 1, "public": 2}
  return sorted(found.values(), key=lambda item: (order.get(item["kind"], 3), not item["is_default"], item["address"]))


def build_base_url(host: str, port: int | str) -> str:
  """Ghép link truy cập cho máy khách.

  Host dạng origin đầy đủ (https://x.trycloudflare.com) thì giữ nguyên và bỏ qua cổng:
  tunnel phục vụ ở 443, gắn thêm ":8000" vào là link hỏng. Host trần thì mới ghép cổng.
  """
  host = (host or "").strip().rstrip("/")
  if "://" in host:
    return host
  return f"http://{host}:{port}"


def hostname() -> str:
  try:
    return socket.gethostname()
  except OSError:
    return "localhost"
