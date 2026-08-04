"""Tìm và cài `cloudflared` để mở đường truy cập công khai cho demo.

Cloudflare Tunnel mở kết nối *đi ra* từ máy chủ nên máy khách ở bất kỳ mạng nào cũng vào
được chỉ bằng một đường link, không cần VPN, không phải mở cổng trên router.

Chỉ dùng thư viện chuẩn để `run_demo.py` nhập được mà không cần cài thêm gì.
"""

from __future__ import annotations

import os
import platform
import shutil
import stat
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS_DIR = ROOT / "tools"

RELEASE_BASE = "https://github.com/cloudflare/cloudflared/releases/latest/download"

# (hệ điều hành, kiến trúc) -> tên file trong bản phát hành chính thức của Cloudflare.
# Tên kiến trúc do platform.machine() trả về không thống nhất giữa các hệ nên phải liệt
# kê cả bí danh: Windows nói "AMD64", Linux nói "x86_64", macOS Apple Silicon nói "arm64".
ASSETS = {
  ("Windows", "amd64"): "cloudflared-windows-amd64.exe",
  ("Windows", "x86"): "cloudflared-windows-386.exe",
  ("Linux", "amd64"): "cloudflared-linux-amd64",
  ("Linux", "arm64"): "cloudflared-linux-arm64",
  ("Darwin", "amd64"): "cloudflared-darwin-amd64.tgz",
  ("Darwin", "arm64"): "cloudflared-darwin-arm64.tgz",
}

ARCH_ALIASES = {
  "amd64": "amd64", "x86_64": "amd64", "x64": "amd64",
  "arm64": "arm64", "aarch64": "arm64",
  "x86": "x86", "i386": "x86", "i686": "x86",
}

MANUAL_HINT = (
  "Cài thủ công rồi chạy lại:\n"
  "  Windows : winget install --id Cloudflare.cloudflared\n"
  "  macOS   : brew install cloudflared\n"
  "  Linux   : xem https://pkg.cloudflare.com/"
)


def binary_name() -> str:
  return "cloudflared.exe" if platform.system() == "Windows" else "cloudflared"


def find_cloudflared() -> str | None:
  """Ưu tiên bản đã cài trong PATH, sau đó mới tới bản script tự tải về `tools/`."""
  found = shutil.which("cloudflared")
  if found:
    return found
  local = TOOLS_DIR / binary_name()
  return str(local) if local.exists() else None


def asset_name() -> str | None:
  system = platform.system()
  arch = ARCH_ALIASES.get(platform.machine().lower())
  return ASSETS.get((system, arch)) if arch else None


def download_url() -> str | None:
  asset = asset_name()
  return f"{RELEASE_BASE}/{asset}" if asset else None


def download_cloudflared() -> str:
  """Tải bản chính thức về `tools/` và trả về đường dẫn.

  Ném RuntimeError kèm hướng dẫn cài tay nếu không nhận ra nền tảng hoặc tải hỏng.
  """
  url = download_url()
  if not url:
    raise RuntimeError(
      f"Chưa hỗ trợ tự tải cho {platform.system()}/{platform.machine()}.\n{MANUAL_HINT}"
    )

  TOOLS_DIR.mkdir(parents=True, exist_ok=True)
  target = TOOLS_DIR / binary_name()

  # Tải vào file tạm rồi mới đổi tên: đứt mạng giữa chừng sẽ không để lại một file
  # cloudflared cụt đầu mà lần chạy sau tưởng là bản dùng được.
  with tempfile.NamedTemporaryFile(delete=False, dir=TOOLS_DIR) as tmp:
    temp_path = Path(tmp.name)
  try:
    urllib.request.urlretrieve(url, temp_path)
    if url.endswith(".tgz"):
      _extract_tgz(temp_path, target)
    else:
      temp_path.replace(target)
  except Exception as error:
    raise RuntimeError(f"Tải cloudflared thất bại: {error}\n{MANUAL_HINT}") from error
  finally:
    temp_path.unlink(missing_ok=True)

  if os.name != "nt":
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
  return str(target)


def _extract_tgz(archive: Path, target: Path) -> None:
  """Bản macOS đóng gói .tgz, bên trong chỉ có đúng một file thực thi."""
  with tarfile.open(archive, "r:gz") as bundle:
    member = next((m for m in bundle.getmembers() if m.isfile()), None)
    if member is None:
      raise RuntimeError("Gói tải về không chứa file nào")
    extracted = bundle.extractfile(member)
    if extracted is None:
      raise RuntimeError("Không đọc được file trong gói tải về")
    with extracted, open(target, "wb") as out:
      shutil.copyfileobj(extracted, out)
