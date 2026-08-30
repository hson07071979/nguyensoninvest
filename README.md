# Nguyễn Sơn Invest — trang web

Repo này chứa **trang web công khai**. Không chứa mã nguồn bot.

| File | Là gì | Ai tạo ra |
|---|---|---|
| `index.html` | toàn bộ trang web | repo riêng `nsi-bot`, mỗi tối 19h30 |
| `thresholds.json` | ngưỡng giá và khối lượng của từng mã cho phiên kế tiếp | repo riêng `nsi-bot`, mỗi tối 19h30 |
| `live.json` | kết quả quét trong phiên | workflow trong chính repo này, mỗi 20 phút |
| `portfolio.json` | **sổ lệnh thật** — bot ra tín hiệu mua là vào sổ | workflow trong repo này, sau 14h50 mỗi phiên |
| `live_scan.py` | bộ quét nhẹ: so giá hôm nay với ngưỡng | — |
| `portfolio.py` | ghi sổ lệnh: vào lệnh theo tín hiệu, ra lệnh theo bộ thoát | — |
| `manual.json` | **sổ tay anh Sơn** — mã anh theo dõi và lệnh anh tự vào | trang web, khi anh bấm "Đăng lên trang" |
| `config.json` | địa chỉ cầu nối real-time + tên repo | anh sửa tay, một lần |
| `worker.js` | mã nguồn cầu nối real-time (dán vào Cloudflare, **không chạy ở đây**) | — |
| `loai.txt`, `ghim.txt` | bản sao hai danh sách thủ công (sửa ở repo riêng, **đừng sửa ở đây** — mỗi tối bị ghi đè) | repo riêng `nsi-bot` |
| `.nojekyll` | bắt buộc để GitHub Pages không xử lý sai | — |

## Ba nguồn nói về "hệ thống đang nắm giữ cái gì"

Trang gộp cả ba thành **một** danh mục, mỗi dòng dán nhãn nguồn — không có chuyện
trang này nói khác trang kia.

| Nguồn | Ai ghi | Chảy vào đâu |
|---|---|---|
| `portfolio.json` | máy chủ, tự động sau 14h50 mỗi phiên | Danh mục hệ thống |
| `manual.json` → `trades` | anh Sơn nhập ở Sổ tay rồi bấm Đăng | Danh mục hệ thống (nhãn "Anh Sơn nhập") |
| `manual.json` → `watch` | anh Sơn nhập ở Sổ tay rồi bấm Đăng | Watchlist → Ghim thủ công |

Mọi con số lãi/lỗ trên trang đều đã trừ **0,15% mua** và **0,25% bán (gồm thuế)** —
một công thức duy nhất, dùng chung cho cả sổ tự động lẫn sổ tay.

## Real-time — không cần dựng gì cả nữa

**Trước đây** trang phải nhờ GitHub Actions quét hộ vì FireAnt không gửi nhãn CORS,
nên trình duyệt bị chặn không đọc được. GitHub chạy theo lịch nên luôn trễ 10–20 phút.
Cách chữa cũ là dựng một Cloudflare Worker đứng giữa (`worker.js`).

**Bây giờ không cần nữa.** Bảng giá của VPS *có* gửi nhãn
`Access-Control-Allow-Origin: *`, và nhận cả trăm mã trong **một** lần gọi:

```
GET https://bgapidatafeed.vps.com.vn/getliststockdata/ACB,BAF,BCM,...
```

Nên trang tự hỏi giá được, **15 giây một nhịp**, không qua máy chủ nào, không tốn
một đồng nào. Anh không phải làm gì cả — mở trang là nó chạy.

Bật/tắt, chỉnh nhịp, bật thông báo hệ điều hành: ở đầu tab **Chuông báo**.

### Ba mức chuông

| Kêu ở đâu | Khi nào | Cần gì |
|---|---|---|
| Toast trên trang + tiếng chuông | tab đang mở | không cần gì |
| Nhấp nháy tiêu đề tab | anh đang ở tab khác | không cần gì |
| Thông báo hệ điều hành | anh đang ở app khác | bấm **Bật** một lần |

### Một chỗ phải nói thẳng

Bảng giá VPS **không có** `BuyCount/SellCount`, nên **điều kiện 7 — cỡ lệnh mua so
cỡ lệnh bán** không tính được từ nguồn này. Nó lấy từ `live.json` (GitHub Actions
đọc FireAnt, làm mới 10–20 phút một lần). Tỷ lệ cỡ lệnh đổi chậm nên trễ chừng ấy
chấp nhận được, và trang luôn ghi rõ số đó cũ bao lâu.

Hệ quả: **mã nào chưa có số điều kiện 7 thì không được lên mức "đủ điểm mua" —
chỉ đứng ở mức "sắp đủ".** Thà báo thiếu còn hơn báo mua một phiên mà bộ máy chín
lớp vốn không đụng vào.

Bù lại, VPS cho một thứ FireAnt không có: **ba mức dư mua và ba mức dư bán ngay lúc
này**. Trang tính thêm tỷ lệ dư mua/dư bán từ đó — một chỉ báo **khác**, dán nhãn
riêng, **không** dùng thay điều kiện 7.

### `worker.js` còn dùng làm gì?

Chỉ còn một việc: lấy **nến ngày** cho trang Chi tiết mã của những mã chưa nhúng
sẵn trong trang. Không dựng cũng không sao — tab **TradingView** ở trang đó vẽ được
mọi mã mà không cần cầu nối nào.

## Sổ lệnh — vì sao nó quan trọng hơn backtest

Backtest là chuyện đã rồi: ai cũng có thể vặn tham số cho quá khứ đẹp lên.
`portfolio.json` thì ghi về **phía trước**. Mỗi phiên, sau khi thị trường đóng cửa,
`portfolio.py` mở lệnh cho mọi tín hiệu MUA của phiên đó với giá vốn bằng giá đóng cửa —
đúng bằng giả thiết khớp lệnh của backtest — rồi chạy lại bộ thoát chín lớp trên các
vị thế đang mở. Kết quả được commit vào chính repo này, nên **lịch sử git là sổ cái**:
có dấu thời gian, không sửa lùi được.

Sau vài tháng, đem đường vốn của sổ so với đường backtest là biết ngay hệ thống có thật
hay không. Trang web hiển thị nó ở tab **Danh mục bot**.

`portfolio.py` cố ý chạy lại từ ngày mua mỗi lần thay vì cộng dồn: workflow có thể
trượt một phiên (GitHub trễ, mạng lỗi, ngày lễ), cộng dồn thì một lần trượt là sai
vĩnh viễn, chạy lại thì lần sau tự đúng lại.

## Vì sao bộ quét nằm ở đây mà không nằm trong repo riêng

Repo public được chạy GitHub Actions **miễn phí không giới hạn**; repo private thì
tính phút. Quét mỗi 20 phút suốt phiên là rất nhiều lượt chạy.

`live_scan.py` **không chứa luật giao dịch nào**. Nó chỉ so giá và khối lượng hôm nay
với hai con số đã tính sẵn trong `thresholds.json`. Hai con số đó vốn đã hiện công khai
trên thanh tra cứu của trang web rồi. Toàn bộ hệ thống — cách chấm điểm, cổng rủi ro,
luật vào ra — nằm trong repo riêng.

## Cài đặt

Không cần làm gì thêm nếu repo riêng đã cấu hình xong. Chỉ cần bật GitHub Pages:
**Settings → Pages → Source: Deploy from a branch → main / (root)**.

Muốn chạy thử ngay: tab **Actions** → **Quét trong phiên** → **Run workflow**.

## Chuông Telegram — báo cả khi đóng trình duyệt

Lớp real-time trong trình duyệt chỉ kêu khi **tab đang mở**. Đóng trình duyệt là
không biết gì. `live_scan.py` giờ bắn tin Telegram mỗi khi có **mã MỚI** lên mức
đủ điểm mua.

**Cài (3 phút, miễn phí vĩnh viễn):**

1. Telegram → tìm **@BotFather** → `/newbot` → đặt tên. Nhận chuỗi
   `7712345678:AAH...` → đó là `TELEGRAM_TOKEN`.
2. Tìm **@userinfobot** → Start. Nhận `Id: 123456789` → đó là `TELEGRAM_CHAT`.
3. **Nhắn một câu cho bot vừa tạo.** Bắt buộc — Telegram không cho bot nhắn trước
   cho người lạ.
4. Repo này → **Settings → Secrets and variables → Actions → Secrets** → thêm hai
   secret tên `TELEGRAM_TOKEN` và `TELEGRAM_CHAT`.

Không khai báo thì bộ quét vẫn chạy bình thường, chỉ là không có tin nhắn.

**Chống kêu trùng:** so với `live.json` của lần quét trước (đã commit vào git), nên
cùng một mã trong cùng một phiên chỉ kêu **đúng một lần**. Sang phiên mới thì reset.

**Lịch quét đã dày lên ở cửa sổ quyết định:** 09h00–13h59 mỗi 20 phút · **14h00–14h59
mỗi 5 phút** · 15h05 và 15h25 chốt lại.
