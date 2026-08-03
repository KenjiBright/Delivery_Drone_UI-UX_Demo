# UAV Delivery Demo

Demo giao hàng bằng UAV, chạy hoàn toàn bằng Python. Không cần Docker, không cần Flutter.

- **App khách hàng** (`/`) — giao diện mobile kiểu Grab/Be: tìm kiếm, danh mục, giỏ hàng, sổ địa chỉ, theo dõi drone thời gian thực, đánh giá sau khi nhận hàng.
- **Console điều phối** (`/operator`) — giao diện tối nhiều mật độ: điều phối đơn, quản lý đội UAV, thống kê, quản lý sản phẩm và khách hàng, cấu hình vận hành.
- **UAV simulator** — mỗi UAV là một tiến trình riêng, bay từ trạm tới điểm giao rồi quay về.

Tất cả phục vụ trên **một cổng duy nhất: 8000**.

## Chạy demo

**Yêu cầu:** Python 3.10+, PC và điện thoại cùng Wi-Fi, mở cổng TCP `8000` trên tường lửa.

```bash
python run_demo.py
```

Trên Windows có thể nhấp đúp `start_demo.bat`. Dừng bằng `Ctrl+C`.

Lần chạy đầu script tự cài thư viện thiếu, khởi động backend, chờ sẵn sàng, bật 3 UAV mô phỏng, in địa chỉ truy cập và mở console.

### Địa chỉ

| | |
|---|---|
| Console điều phối (PC) | `http://localhost:8000/operator` |
| App khách hàng (PC) | `http://localhost:8000/` |
| App khách hàng (điện thoại) | `http://IP_MAY_TINH:8000/` |
| Tài liệu API | `http://localhost:8000/docs` |

Script tự tìm và in ra IP LAN khi khởi động.

### Tài khoản demo

| Vai trò | Tên đăng nhập | Mật khẩu |
|---|---|---|
| Khách hàng | `customer` | `khachhang123` |
| Điều phối | `operator` | `dieuphoi123` |

### Tuỳ chọn dòng lệnh

| Cờ | Tác dụng |
|---|---|
| `--uavs 5` | Số UAV mô phỏng chạy song song (mặc định 3) |
| `--port 9000` | Đổi cổng phục vụ |
| `--reset` | Xoá toàn bộ dữ liệu demo trước khi chạy |
| `--no-browser` | Không tự mở trình duyệt |
| `--no-simulator` | Chỉ chạy backend |
| `--no-install` | Không tự cài thư viện còn thiếu |

## Tính năng

### App khách hàng

- Tìm kiếm sản phẩm, lọc theo danh mục, giỏ hàng sửa số lượng trực tiếp.
- Chọn điểm giao bằng ba cách: tìm địa chỉ theo tên (OpenStreetMap), chạm bản đồ, hoặc lấy vị trí GPS hiện tại.
- Sổ địa chỉ lưu sẵn (Nhà, Cơ quan…) để đặt lại nhanh.
- Thanh tiến trình 5 bước, ETA đếm ngược tính từ khoảng cách và tốc độ thực của UAV.
- Thẻ đơn đang giao nổi trên mọi màn hình, chạm vào mở thẳng màn theo dõi.
- Nhập PIN khi UAV đến nơi, chấm sao và nhận xét sau khi hoàn thành.
- Lịch sử đơn kèm nhật ký từng mốc trạng thái.

### Console điều phối

- **Tổng quan** — chỉ số chính, bản đồ toàn đội bay, hàng đợi đơn cần xử lý, cảnh báo pin yếu / hết UAV rảnh / đơn tồn.
- **Đơn hàng** — lọc theo trạng thái và nhóm, tìm kiếm, sắp xếp theo cột, phân trang, xuất CSV. Xác nhận → gán UAV (tự động hoặc chọn tay) → cho xuất phát, huỷ đơn kèm lý do, xem nhật ký đầy đủ.
- **Đội UAV** — thêm/sửa/xoá UAV, đặt bảo trì, theo dõi pin và tín hiệu từng thiết bị.
- **Thống kê** — đơn theo ngày, doanh thu, phân bổ trạng thái, sản phẩm bán chạy, thời gian giao trung bình, điểm hài lòng. Biểu đồ vẽ bằng SVG thuần, kèm bảng dữ liệu cho trình đọc màn hình.
- **Sản phẩm** — thêm/sửa/xoá, đổi giá và khối lượng, ẩn khỏi danh mục mà không cần xoá.
- **Khách hàng** — số đơn, tổng chi tiêu, điểm đánh giá trung bình, đơn gần nhất.
- **Cấu hình** — toạ độ trạm xuất phát, tải trọng tối đa, ngưỡng cảnh báo pin.

## Kiến trúc

```
run_demo.py              Launcher: backend + N simulator
backend/app/
  main.py                Lắp ráp router, WebSocket, phục vụ web tĩnh
  db.py                  Khai báo bảng, dữ liệu mẫu, tiện ích SQLite
  security.py            Băm mật khẩu, phiên đăng nhập, phân quyền
  models.py              Schema request/response
  realtime.py            Quản lý kết nối WebSocket
  routes/                auth · catalog · orders · fleet · admin
backend/web/
  css/                   base (token dùng chung) · app · console
  js/                    api · ui · icons (sprite SVG)
  js/customer/           store · home · cart · orders · address · main
  js/console/            store · charts · views/* · main
uav_simulator/simulator.py
```

## Kiểm thử

```bash
cd backend
python -m pytest tests/ -v
```

## Lưu ý kỹ thuật

- Xác thực là cơ chế demo: token phiên lưu trong RAM, khởi động lại backend là phải đăng nhập lại. Chưa phù hợp vận hành thương mại.
- Giao diện dùng icon SVG (không emoji), hỗ trợ bàn phím, vùng chạm tối thiểu 44px và tôn trọng `prefers-reduced-motion`.
- Bản đồ dùng Leaflet + OpenStreetMap nên không cần API key, nhưng cần Internet để tải tile và để tìm địa chỉ theo tên.
- Không có bước build: sửa file trong `backend/web` rồi tải lại trang là thấy ngay.
- Mỗi UAV mô phỏng là một tiến trình riêng gọi API qua `X-API-Key`. Thay bằng UAV thật chỉ cần viết cầu nối Pymavlink/MAVSDK nói chuyện với cùng bộ endpoint `/api/simulator/*`, backend và hai giao diện không đổi.
- Trạng thái bảo trì do điều phối viên đặt sẽ không bị telemetry của UAV ghi đè.
- Bộ mã tối ưu cho demo trong mạng LAN. Muốn dùng qua Internet cần triển khai lên tên miền có HTTPS/WSS.
