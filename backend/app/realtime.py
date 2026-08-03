"""Đẩy sự kiện thời gian thực tới console điều phối và app khách hàng."""

from __future__ import annotations

import json
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
  def __init__(self) -> None:
    self.operator_connections: set[WebSocket] = set()
    self.customer_connections: dict[str, set[WebSocket]] = {}

  async def connect_operator(self, websocket: WebSocket) -> None:
    await websocket.accept()
    self.operator_connections.add(websocket)

  async def connect_customer(self, username: str, websocket: WebSocket) -> None:
    await websocket.accept()
    self.customer_connections.setdefault(username, set()).add(websocket)

  def disconnect(self, websocket: WebSocket) -> None:
    self.operator_connections.discard(websocket)
    for connections in self.customer_connections.values():
      connections.discard(websocket)

  async def broadcast(self, event: dict[str, Any], customer_username: str | None = None) -> None:
    """Điều phối luôn nhận mọi sự kiện; khách hàng chỉ nhận sự kiện của mình."""
    text = json.dumps(event, ensure_ascii=False)
    stale: list[WebSocket] = []
    targets = list(self.operator_connections)
    if customer_username:
      targets += list(self.customer_connections.get(customer_username, set()))
    for socket in targets:
      try:
        await socket.send_text(text)
      except Exception:
        stale.append(socket)
    for socket in stale:
      self.disconnect(socket)


manager = ConnectionManager()
