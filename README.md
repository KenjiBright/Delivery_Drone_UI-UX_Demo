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

Script tự tìm và in ra IP LAN khi khởi động. Máy chủ lắng nghe trên mọi card mạng,
nên địa chỉ VPN (Tailscale, WireGuard) cũng dùng được ngay mà không cần cấu hình thêm.

### Chạy qua VPN thay vì phụ thuộc router

Mỗi lần đổi router, IP LAN lại đổi và phải đi dò lại. Nếu máy chủ và máy khách cùng
nằm trong một VPN thì địa chỉ đó cố định. Vào **Console → Cấu hình → Đường truy cập
cho máy khách**: console liệt kê mọi địa chỉ máy đang có, tự nhận diện dải Tailscale
(`100.64.0.0/10`), cho chọn địa chỉ và cổng, rồi dựng sẵn liên kết để sao chép gửi cho
máy khách. Cũng có thể tự nhập tên miền VPN, ví dụ `may-chu.tail1234.ts.net`.

Lựa chọn được lưu vào cơ sở dữ liệu. Lần sau chạy `python run_demo.py` không kèm
`--port`, script đọc lại cổng đã lưu và in đúng liên kết đó. Đổi địa chỉ có hiệu lực
ngay; đổi cổng thì phải khởi động lại script.

### Máy khác không vào được (timeout)

`ERR_CONNECTION_TIMED_OUT` nghĩa là gói tin bị **thả im lặng**, không phải bị từ chối,
nên rất khó đoán nguyên nhân. Kiểm tra theo đúng thứ tự này:

1. **Script còn chạy không.** Cửa sổ chạy `run_demo.py` phải còn mở. Kiểm tra nhanh:
   `curl http://localhost:8000/health`.
2. **Hai máy có thấy nhau qua VPN không.** `tailscale status` phải thấy máy kia là
   `active` hoặc `idle`; `tailscale ping <ip-may-kia>` phải có `pong`.
3. **Tường lửa có mở đúng cổng đang dùng không.** Đây là chỗ dễ sập nhất: rule tường
   lửa gắn với **một số cổng cụ thể**, nên đổi cổng trong console mà quên mở rule cho
   cổng mới thì máy ngoài lại timeout y hệt. Console tự kiểm tra và báo ngay tại mục
   **Cấu hình → Đường truy cập**, `run_demo.py` cũng cảnh báo lúc khởi động.

Nếu console báo tường lửa chưa mở, mở PowerShell bằng **quyền Administrator** rồi chạy
lệnh mà console đưa (có nút sao chép), dạng:

```bash
New-NetFirewallRule -DisplayName "UAV Delivery Demo (8000)" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Any -RemoteAddress 100.64.0.0/10,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16
```

Rule này chỉ nhận kết nối từ dải Tailscale và ba dải mạng riêng, không mở cổng ra
Internet.

### Tài khoản demo

| Vai trò | Tên đăng nhập | Mật khẩu |
|---|---|---|
| Khách hàng | `customer` | `khachhang123` |
| Điều phối | `operator` | `dieuphoi123` |

### Tuỳ chọn dòng lệnh

| Cờ | Tác dụng |
|---|---|
| `--uavs 5` | Số UAV mô phỏng chạy song song (mặc định 3) |
| `--port 9000` | Đổi cổng phục vụ. Bỏ trống thì dùng cổng đã lưu trong console, mặc định 8000 |
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
- Nền sáng / nền tối / theo cài đặt máy, chọn trong tab Tài khoản và được nhớ lại.

### Console điều phối

- **Tổng quan** — chỉ số chính, bản đồ toàn đội bay, hàng đợi đơn cần xử lý, cảnh báo pin yếu / hết UAV rảnh / đơn tồn.
- **Đơn hàng** — lọc theo trạng thái và nhóm, tìm kiếm, sắp xếp theo cột, phân trang, xuất CSV. Xác nhận → gán UAV (tự động hoặc chọn tay) → cho xuất phát, huỷ đơn kèm lý do, xem nhật ký đầy đủ.
- **Đội UAV** — thêm/sửa/xoá UAV, đặt bảo trì, theo dõi pin và tín hiệu từng thiết bị.
- **Thống kê** — đơn theo ngày, doanh thu, phân bổ trạng thái, sản phẩm bán chạy, thời gian giao trung bình, điểm hài lòng. Biểu đồ vẽ bằng SVG thuần, kèm bảng dữ liệu cho trình đọc màn hình.
- **Sản phẩm** — thêm/sửa/xoá, đổi giá và khối lượng, ẩn khỏi danh mục mà không cần xoá.
- **Khách hàng** — số đơn, tổng chi tiêu, điểm đánh giá trung bình, đơn gần nhất.
- **Cấu hình** — toạ độ trạm xuất phát, tải trọng tối đa, ngưỡng cảnh báo pin, và đường truy cập (địa chỉ VPN/LAN + cổng) công bố cho máy khách.

## Kiến trúc

```
run_demo.py              Launcher: backend + N simulator
backend/app/
  main.py                Lắp ráp router, WebSocket, phục vụ web tĩnh
  db.py                  Khai báo bảng, dữ liệu mẫu, tiện ích SQLite
  security.py            Băm mật khẩu, phiên đăng nhập, phân quyền
  models.py              Schema request/response
  realtime.py            Quản lý kết nối WebSocket
  network.py             Dò địa chỉ IP của máy chủ, nhận diện VPN
  firewall.py            Kiểm tra tường lửa có mở cổng đang phục vụ không
  routes/                auth · catalog · orders · fleet · admin
backend/web/
  css/                   base (token dùng chung) · app · console
  js/                    api · ui · icons (sprite SVG) · theme (sáng/tối)
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
- Phần kiểm tra tường lửa đọc rule bằng `netsh`, **không dùng `Get-NetFirewallRule`**: cmdlet đó đòi quyền Administrator và khi thiếu quyền nó trả danh sách rỗng thay vì báo lỗi, rất dễ kết luận nhầm là máy không có rule nào. Đầu ra `netsh` bị dịch theo ngôn ngữ Windows; không đọc hiểu được thì báo "không rõ" chứ không báo là thiếu rule.
- Việc dò địa chỉ chỉ dùng thư viện chuẩn: mở UDP socket tới vài đích mẫu để hỏi hệ điều hành ra bằng card nào (không gửi gói tin nào), cộng với phân giải tên máy. Vì không đọc được tên card mạng trên mọi hệ điều hành nên VPN được nhận diện theo dải địa chỉ; WireGuard dùng dải 10.x sẽ hiện chung nhóm với mạng nội bộ.
- Bộ mã tối ưu cho demo trong mạng LAN. Muốn dùng qua Internet cần triển khai lên tên miền có HTTPS/WSS.
