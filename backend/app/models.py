"""Schema request/response dùng chung cho các router."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
  username: str
  password: str
  expected_role: str | None = None


class ProfilePatch(BaseModel):
  """Hồ sơ tài khoản. Mỗi vai trò chỉ được sửa phần dành cho mình, lọc ở router."""

  display_name: str | None = Field(default=None, min_length=1, max_length=60)
  full_name: str | None = Field(default=None, max_length=80)
  email: str | None = Field(default=None, max_length=120)
  phone: str | None = Field(default=None, max_length=20)
  gender: str | None = None
  date_of_birth: str | None = Field(default=None, max_length=10)

  # Chỉ dành cho điều phối viên.
  employee_code: str | None = Field(default=None, max_length=32)
  job_title: str | None = Field(default=None, max_length=60)
  department: str | None = Field(default=None, max_length=80)
  duty_status: str | None = None

  # Chỉ dành cho khách hàng.
  default_note: str | None = Field(default=None, max_length=250)
  default_address_id: int | None = None
  notify_orders: bool | None = None


class PasswordChange(BaseModel):
  current_password: str = Field(min_length=1)
  new_password: str = Field(min_length=6, max_length=100)


class OrderItemRequest(BaseModel):
  product_id: str
  quantity: int = Field(ge=1, le=20)


class CreateOrderRequest(BaseModel):
  items: list[OrderItemRequest]
  delivery_lat: float = Field(ge=-90, le=90)
  delivery_lon: float = Field(ge=-180, le=180)
  delivery_address: str = Field(min_length=3, max_length=250)
  note: str = Field(default="", max_length=250)


class AssignRequest(BaseModel):
  # Bỏ trống để hệ thống tự chọn UAV rảnh có pin cao nhất.
  uav_id: str | None = None


class VerifyRequest(BaseModel):
  code: str


class CancelRequest(BaseModel):
  reason: str = Field(default="", max_length=250)


class RateRequest(BaseModel):
  rating: int = Field(ge=1, le=5)
  review: str = Field(default="", max_length=500)


class AddressRequest(BaseModel):
  label: str = Field(min_length=1, max_length=60)
  address: str = Field(min_length=3, max_length=250)
  lat: float = Field(ge=-90, le=90)
  lon: float = Field(ge=-180, le=180)


class ProductRequest(BaseModel):
  id: str = Field(min_length=2, max_length=32)
  name: str = Field(min_length=1, max_length=120)
  description: str = Field(default="", max_length=250)
  price: int = Field(ge=0)
  weight_kg: float = Field(gt=0, le=50)
  icon: str = Field(default="package", max_length=32)
  category: str = Field(default="Khác", max_length=60)
  active: bool = True


class ProductPatch(BaseModel):
  name: str | None = Field(default=None, min_length=1, max_length=120)
  description: str | None = Field(default=None, max_length=250)
  price: int | None = Field(default=None, ge=0)
  weight_kg: float | None = Field(default=None, gt=0, le=50)
  icon: str | None = Field(default=None, max_length=32)
  category: str | None = Field(default=None, max_length=60)
  active: bool | None = None


class UavRequest(BaseModel):
  id: str = Field(min_length=2, max_length=32)
  model: str = Field(default="Demo Quad X4", max_length=80)
  max_payload_kg: float = Field(default=2.5, gt=0, le=50)
  note: str = Field(default="", max_length=250)


class UavPatch(BaseModel):
  model: str | None = Field(default=None, max_length=80)
  max_payload_kg: float | None = Field(default=None, gt=0, le=50)
  note: str | None = Field(default=None, max_length=250)
  status: str | None = None


class SettingsPatch(BaseModel):
  home_lat: float | None = Field(default=None, ge=-90, le=90)
  home_lon: float | None = Field(default=None, ge=-180, le=180)
  max_payload_kg: float | None = Field(default=None, gt=0, le=50)
  low_battery_threshold: int | None = Field(default=None, ge=0, le=100)
  service_name: str | None = Field(default=None, max_length=60)
  # Địa chỉ công bố cho máy khách. Để trống nghĩa là dùng đúng host trên trình duyệt.
  access_host: str | None = Field(default=None, max_length=120)
  access_port: int | None = Field(default=None, ge=1, le=65535)

  @field_validator("access_host")
  @classmethod
  def clean_access_host(cls, value: str | None) -> str | None:
    """Nhận cả IP trần lẫn origin đầy đủ dạng https://x.trycloudflare.com.

    Link tunnel người dùng copy về thường kèm dấu / cuối hoặc cả đường dẫn; giữ nguyên
    thì lúc ghép link sẽ ra https://x.trycloudflare.com//operator. Chỉ giữ lại origin.
    """
    if value is None:
      return None
    value = value.strip().rstrip("/")
    if "://" not in value:
      return value

    scheme, _, rest = value.partition("://")
    if scheme.lower() not in {"http", "https"}:
      raise ValueError("Địa chỉ chỉ hỗ trợ http hoặc https")
    origin = rest.split("/")[0].split("?")[0]
    if not origin:
      raise ValueError("Địa chỉ thiếu tên miền")
    return f"{scheme.lower()}://{origin}"


class TelemetryRequest(BaseModel):
  uav_id: str
  lat: float
  lon: float
  altitude: float = 0.0
  speed: float = 0.0
  heading: float = 0.0
  battery: float = 100.0
  uav_status: str
  order_id: str | None = None
  order_status: str | None = None
