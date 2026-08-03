"""Điểm vào của backend: lắp ráp router, WebSocket và giao diện web tĩnh."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import init_db, utc_now
from .realtime import manager
from .routes import admin, auth, catalog, fleet, orders
from .security import SESSIONS

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
  init_db()
  yield


app = FastAPI(title="UAV Delivery Demo API", version="2.0.0", lifespan=lifespan)
app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],
  allow_credentials=False,
  allow_methods=["*"],
  allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(catalog.router)
app.include_router(orders.router)
app.include_router(fleet.router)
app.include_router(admin.router)


@app.get("/health")
def health() -> dict[str, Any]:
  return {"status": "ok", "time": utc_now()}


@app.websocket("/ws/operator")
async def operator_ws(websocket: WebSocket, token: str = Query(default="")) -> None:
  session = SESSIONS.get(token)
  if not session or session["role"] != "operator":
    await websocket.close(code=4401)
    return
  await manager.connect_operator(websocket)
  try:
    await websocket.send_json({"type": "connected", "role": "operator"})
    while True:
      await websocket.receive_text()
  except WebSocketDisconnect:
    manager.disconnect(websocket)


@app.websocket("/ws/customer")
async def customer_ws(websocket: WebSocket, token: str = Query(default="")) -> None:
  session = SESSIONS.get(token)
  if not session or session["role"] != "customer":
    await websocket.close(code=4401)
    return
  await manager.connect_customer(session["username"], websocket)
  try:
    await websocket.send_json({"type": "connected", "role": "customer"})
    while True:
      await websocket.receive_text()
  except WebSocketDisconnect:
    manager.disconnect(websocket)


class RevalidatingStatics(StaticFiles):
  """Buộc trình duyệt kiểm tra lại mọi file tĩnh trước khi dùng bản cache.

  Không có header này, sửa một file JS rồi tải lại trang sẽ trộn lẫn bản mới với
  bản cũ trong cache và làm hỏng cả cây ES module. Vẫn trả 304 nên rất nhẹ.
  """

  def file_response(self, *args, **kwargs) -> Response:
    response = super().file_response(*args, **kwargs)
    response.headers["Cache-Control"] = "no-cache"
    return response


# Giao diện web tĩnh. Khai báo sau toàn bộ route API để không che mất chúng.
@app.get("/", include_in_schema=False)
def customer_page() -> FileResponse:
  return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/operator", include_in_schema=False)
def operator_page() -> FileResponse:
  return FileResponse(WEB_DIR / "operator.html", headers={"Cache-Control": "no-cache"})


app.mount("/static", RevalidatingStatics(directory=WEB_DIR), name="static")
