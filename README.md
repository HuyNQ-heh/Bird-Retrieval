# Phần 3 · Mặt nạ và đặc trưng ảnh chim

Từ một JPG, chương trình xác định cá thể chim, lưu mặt nạ PNG và ghi ba vector màu sắc, kết cấu, hình dạng vào MySQL. Hai hàm xử lý ảnh trong bộ nhớ dùng chung được cho ảnh truy vấn ở phần 4.

## Chạy trên Windows PowerShell

Mở PowerShell tại thư mục chứa `cli.py`. Lần bàn giao dùng Python 3.14.3 64-bit và MySQL Community Server 8.0.46. Dùng MySQL **từ 8.0.17** để máy chủ thực thi `CHECK (JSON_SCHEMA_VALID(...))` cho từng vector. [Tài liệu MySQL](https://dev.mysql.com/doc/refman/8.0/en/json-validation-functions.html)

```powershell
py -3.14 -m venv .venv
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install -r requirements.txt
& $py cli.py setup-models
if (!(Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Điền thông tin kết nối thật vào `.env` và lưu. Với mật khẩu chứa khoảng trắng hoặc dấu `#`, dùng dấu nháy đơn bao quanh giá trị. Tài khoản cần quyền đọc, thêm và cập nhật trên database đã chọn, cùng quyền tạo bảng ở lần khởi tạo. Nếu database chưa tồn tại, `init-db` sẽ tạo khi tài khoản có quyền. Khi mở cửa sổ PowerShell mới, gán lại `$py` như trên.

```powershell
& $py cli.py inspect
& $py cli.py init-db
# Một JPG → một PNG, một ảnh đối chiếu và một hàng đặc trưng
& $py cli.py run --image data/images/American_Crow_0004_25819.jpg --preview --check-background
& $py cli.py verify-db
# Ba ví dụ gồm nền cát, nền cành cây và nền cỏ
& $py cli.py run --image data/images/California_Gull_0009_40662.jpg --image data/images/Black_And_White_Warbler_0002_160376.jpg --image data/images/American_Pipit_0029_99667.jpg --preview --check-background
# Năm ảnh đầu theo thứ tự tên
& $py cli.py run --limit 5 --preview
# Toàn bộ dataset và kiểm tra lại sau commit từ JPG, PNG và JSON trong MySQL
& $py cli.py run --check-background
& $py cli.py verify-db
& $py -m unittest discover -s tests -v
```

Mỗi lần `run` in đường dẫn đến một thư mục mới trong `runs/`. `results.jsonl` có một dòng cho từng ảnh, gồm đường dẫn, ID, đường dẫn PNG và tổng histogram khi thành công, hoặc công đoạn và lý do khi lỗi. `summary.json` thống kê lần chạy. Một ảnh lỗi cho phép vòng lặp tiếp tục và lệnh trả mã 1 khi kết thúc. Với `--preview`, mỗi ảnh đối chiếu trong `previews/` hiển thị lần lượt JPG gốc, PNG nhị phân và đường viền hồng trên JPG.

```powershell
# Lọc lỗi của lần chạy gần nhất
$run = Get-ChildItem runs -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'summary.json') } | Sort-Object Name -Descending | Select-Object -First 1
Get-Content (Join-Path $run.FullName 'results.jsonl') -Encoding UTF8 | ForEach-Object { $_ | ConvertFrom-Json } | Where-Object error | Select-Object image,stage,error
# Khi chưa có kết nối MySQL, vẫn lưu PNG và cả ba vector trong results.jsonl
& $py cli.py run --offline --limit 3 --preview --check-background
```

## Ảnh đầu vào và mặt nạ

Đã giải mã toàn bộ 1.000 JPG trong `data/images/`. Tất cả là JPEG RGB 224 × 224. Có 70 nhãn, từ 8 đến 25 ảnh mỗi nhãn. Tên file có dạng `<tên_loài>_<4 chữ số>_<mã số>.jpg`. Chỉ tách hai cụm số cuối, rồi thay gạch dưới trong tên bằng khoảng trắng. Ví dụ `Black_And_White_Warbler_0002_160376.jpg` cho nhãn `Black And White Warbler`. Nhãn chỉ dùng để đăng ký ảnh. `inspect` in số lượng cho từng loài.

`masking.py` nạp một bộ MobileNet-SSD và Silueta cho mỗi tiến trình xử lý. Cả hai chạy trên CPU. Lệnh `setup-models` tải ba tệp của hai mô hình vào `models/`, kiểm SHA-256 và dùng lại bản đã khớp. OpenCV 4.x có bộ đọc mạng Caffe cho SSD. ONNX Runtime chạy Silueta. [MobileNet-SSD và danh sách lớp VOC](https://github.com/chuanqi305/MobileNet-SSD/blob/master/demo.py) · [Trọng số và tiền xử lý Silueta](https://github.com/danielgatis/rembg/blob/main/rembg/sessions/silueta.py)

1. SSD đọc toàn ảnh ở 300 × 300. Giữ phát hiện lớp `bird` đạt điểm từ 0,35 và chọn con có điểm cao nhất. Nếu thiếu phát hiện, thử ảnh lật ngang một lần rồi ánh xạ hộp về tọa độ gốc. Không có con đạt ngưỡng ở cả hai lượt sẽ ghi lỗi công đoạn `mask`.
2. Nới hộp SSD thêm 15% chiều rộng và chiều cao ở mỗi bên. Silueta nhận RGB 320 × 320 đã chuẩn hóa, dự đoán vùng tiền cảnh và nội suy điểm số về kích thước vùng cắt. Ngưỡng 0,5 tạo mặt nạ. Trong các vùng liên thông 8 hướng, chọn vùng có nhiều pixel nằm trong hộp SSD nhất.
3. Loại dự đoán rỗng, phủ kín vùng cắt, hoặc không giao hộp. Vùng chọn phải phủ từ 3% đến 96% diện tích hộp, với ít nhất một nửa số pixel của vùng nằm trong hộp. Nếu chưa đạt, chạy lại Silueta với đệm 25%. Nếu cả hai lượt đều lỗi, giữ thông tin đăng ký và ghi lý do. Đây là các ngưỡng lọc hình học. Đánh giá mức bám sát mỏ, chân, đuôi cần xem đường viền chồng.
4. Đưa vùng chim về đúng tọa độ JPG. PNG một kênh có nền 0, chim 255, cùng kích thước với JPG. Bộ xử lý tự tạo thư mục mặt nạ khi cần. Dữ liệu đưa vào mô hình chỉ gồm pixel của ảnh đang xét.

## Ba vector theo phần II của báo cáo

Đầu vào là mảng NumPy RGB `uint8[H,W,3]`. API chấp nhận mặt nạ `bool[H,W]` hoặc `uint8[H,W]` chỉ có 0/255. `extract_features` trả về ba mảng `float64` theo thứ tự trong bảng, tổng cộng 678 giá trị.

| Mục báo cáo | Hàm trong features.py | Công cụ và tham số | Vị trí trong vector, đánh số từ 0 |
|---|---|---|---|
| 2.1.1 · HSV toàn vùng | `color_features` | OpenCV RGB→HSV, NumPy đếm 8 × 4 × 4 bin trên chim | Màu 0–127, 128 chiều |
| 2.1.2 · HSV theo ô | `color_features` | Hộp bao sát mặt nạ, lưới 2 × 2. Theo thứ tự trên trái, trên phải, dưới trái, dưới phải | Màu 128–639, 4 × 128 chiều |
| 2.2.1 · LBP | `texture_features` | scikit-image `uniform`, 8 điểm trên vòng tròn, bán kính 1. Co mặt nạ bằng cửa sổ 3 × 3 để lấy tâm hợp lệ | Kết cấu 0–9, 10 chiều |
| 2.2.2 · GLCM | `texture_features`, `_glcm` | NumPy đếm các cặp có cả hai đầu thuộc chim, 16 mức xám và bốn hướng | Kết cấu 10–25, 4 × 4 chiều |
| 2.3.1 · Hình học | `shape_features` | OpenCV, NumPy, scikit-image. Rộng/cao, extent, solidity, eccentricity, circularity | Hình dạng 0–4, 5 chiều |
| 2.3.2 · Hu Moments | `shape_features` | OpenCV moments nhị phân và Hu 1 đến 7, biến đổi log có dấu | Hình dạng 5–11, 7 chiều |

**Màu.** H của OpenCV thuộc [0,180), S và V thuộc [0,256). Tăng chỉ số V nhanh nhất, chỉ số bin bằng `(h_bin × 4 + s_bin) × 4 + v_bin`. Chiều lẻ dành pixel dư cho bên phải hoặc phía dưới. Mỗi histogram chia cho số pixel chim trong chính vùng đó. Vùng có chim có tổng 1. Ô trống có 128 số 0.

**Kết cấu.** Dùng ảnh xám 8-bit từ `COLOR_RGB2GRAY`. Nội suy các mẫu chéo của LBP có thể chạm bốn pixel, nên toàn cửa sổ 3 × 3 phải nằm trong chim, kể cả ở biên ảnh. Chín bin đầu đếm mẫu uniform theo số bit 1, từ 0 đến 8. Bin cuối đếm mẫu còn lại. Chia cho số tâm hợp lệ, hoặc trả 10 số 0 khi thiếu tâm. Với GLCM, mức xám bằng `gray // 16`. Thứ tự hướng theo (hàng, cột) là ngang (0,1), dọc (1,0), chéo xuống phải (1,1), chéo xuống trái (1,−1). Với từng hướng, cộng ma trận đếm và ma trận chuyển vị rồi chia cho tổng để được P. Lần lượt lấy contrast ΣP(i−j)², homogeneity ΣP/[1+(i−j)²], energy √ΣP², correlation từ hiệp phương sai chia cho phương sai biên chung của P đối xứng. Hướng thiếu cặp trả bốn số 0. Có cặp nhưng phương sai bằng 0 thì correlation bằng 1.

**Hình dạng.** Tính trên toàn bộ pixel chim của mặt nạ đầu vào, giữ nguyên lỗ và biên. Cắt phần nền ngoài hộp bao chỉ thay đổi gốc tọa độ. A là số pixel chim, w và h đếm cả hai đầu của hộp. Extent bằng A/(w×h). Solidity bằng A/số pixel trong bao lồi raster hóa bằng OpenCV. Eccentricity bằng √(1−λ_min/λ_max) từ ma trận hiệp phương sai tọa độ pixel chim, quy ước 0 khi λ_max bằng 0. P là ước lượng chu vi Crofton 4 hướng, tính cả biên lỗ. Circularity bằng 4πA/P², quy ước 0 khi P bằng 0. Ước lượng rời rạc có thể cho giá trị lớn hơn 1 ở hình rất nhỏ. Hu dùng −sign(h) × log10(|h|) cho h khác 0 và ghi 0 khi h bằng 0. Kích thước không khớp, mặt nạ rỗng hoặc không nhị phân, vector sai số chiều hoặc có NaN/∞ đều gây lỗi.

## Dùng lại cho phần 4

```python
import numpy as np
from PIL import Image
from masking import create_bird_mask
from features import extract_features

with Image.open("anh_truy_van.jpg") as source:
    rgb = np.asarray(source.convert("RGB"))
mask = create_bird_mask(rgb)
color, texture, shape = extract_features(rgb, mask)
```

Đầu vào của hai hàm ở trong bộ nhớ. Ảnh mới có thể khác kích thước, lệch tâm và có tên bất kỳ. Nếu thiếu phát hiện, `create_bird_mask` phát sinh `ValueError` để bên gọi báo lại. Bố cục bốn ô có hướng nên ảnh chim quay ngược chiều dữ liệu có thể cho histogram theo ô khác.

## Lưu trữ và kiểm tra MySQL

`database.py` dùng PyMySQL, lấy cấu hình từ `.env`. `images` giữ khóa chính `image_id`, khóa duy nhất `image_path`, nhãn loài và `mask_path` cho phép NULL. `image_features.image_id` vừa là khóa chính vừa tham chiếu `images`. Ba cột JSON bắt buộc là mảng số có đúng 640/26/12 phần tử. [Lược đồ](sql/schema.sql) · [Ba truy vấn quản trị](sql/queries.sql)

Đăng ký đường dẫn tương đối trước khi xử lý. Chạy lại tra cùng khóa duy nhất và giữ nguyên ID. PNG có tên chứa SHA-256 của nội dung. Chương trình viết xong tệp tạm rồi chuyển sang tên chính thức. Trong một giao dịch InnoDB, chương trình cập nhật đường dẫn PNG và cả ba vector, đọc lại từng giá trị với `rtol = atol = 1e-12`, rồi commit. Nếu bước này lỗi, rollback giữ nguyên bộ kết quả trước đó. PNG của phiên bản khác có thể còn trên đĩa. Đường dẫn hiện hành của mỗi ảnh nằm trong `images.mask_path`.

Để thay mặt nạ, lưu bản chỉnh sửa thành **một tệp mới**, ngoài các tệp có tên chứa SHA-256. Lệnh sau kiểm tra PNG một kênh, trích lại toàn bộ vector và công bố phiên bản mới. Thay đường dẫn cuối bằng tệp của nhóm.

```powershell
& $py cli.py run --image data/images/American_Crow_0004_25819.jpg --mask .\mat_na_da_sua.png --preview --check-background
```

`verify-db` mở kết nối mới, đọc lại JPG, PNG và ba mảng JSON của từng hàng rồi trích lại và so từng phần tử. Lệnh in số ảnh đăng ký, đủ đặc trưng, còn thiếu, đã đối chiếu và sai khác. Chạy [queries.sql](sql/queries.sql) trong MySQL Workbench sau khi chọn đúng schema để đếm ảnh đủ đặc trưng, liệt kê ảnh còn thiếu hoặc đọc các vector theo `@image_id`.

## Kiểm chứng trên ảnh thật

| Kết quả bàn giao | Số lượng |
|---|---:|
| JPG đã giải mã / số loài | 1.000 / 70 |
| PNG hiện hành trong `data/masks/`, đã kiểm kích thước, giá trị 0/255 và SHA-256 | 1.000 |
| Ảnh có đủ ba vector hữu hạn 640/26/12 | 1.000 |
| Bản ghi đã trích lại từ JPG + PNG và so từng giá trị với MySQL | 1.000 |
| Ảnh thiếu đặc trưng / bản ghi sai khác / lỗi xử lý trong lượt cuối | 0 / 0 / 0 |

Đổi toàn bộ pixel nền thành `255 − RGB` và giữ nguyên pixel chim, mặt nạ cho cả 1.000 ảnh. Sai khác tuyệt đối lớn nhất của từng vector màu, kết cấu và hình dạng đều bằng **0**. Tổng từng histogram HSV và LBP khớp quy tắc vùng có dữ liệu hoặc vùng trống với sai số tối đa 4,45 × 10⁻¹⁶. Các PNG thử nghiệm U²-NetP từ trước khi chốt Silueta nằm trong `runs/20261125-004519-0a4a80/superseded-masks/`. [Nhật ký từng JPG](runs/20261125-004837-613a30/results.jsonl) · [Tổng kết](runs/20261125-004837-613a30/summary.json) · [Đối chiếu đường dẫn và PNG](runs/20261125-004837-613a30/audit.json) · [Kiểm tra MySQL sau commit](runs/20261125-004837-613a30/verify-db.json)

Ảnh American Crow được chạy lại với cùng đường dẫn. MySQL giữ đúng một hàng có `image_id = 1`. Khi đọc lại ba mảng của phiên bản Silueta và so với giá trị Python vừa trích, sai khác tuyệt đối lớn nhất lần lượt là 2,78 × 10⁻¹⁷, 1,39 × 10⁻¹⁷ và 5,55 × 10⁻¹⁷. Thử cập nhật đồng thời đường dẫn PNG khác và vector hình dạng chỉ có 11 số làm MySQL từ chối giao dịch với mã 3819. Đọc lại xác nhận đường dẫn cũ và toàn bộ 678 giá trị còn nguyên.

Trên ảnh thử 640 × 360 ghép từ ảnh California Gull, con chim nằm hoàn toàn ở nửa phải. Hàm tạo được mặt nạ có hộp bao (x=429, y=63, w=184, h=120). Với ảnh ghép hai con, SSD phát hiện cả hai và trả mặt nạ của con có điểm cao nhất. Ảnh đen trơn được báo thiếu phát hiện.

Các ảnh đối chiếu dưới đây nằm trong workspace sau lần chạy. Có thể tái tạo bằng `run --image ... --preview`.

| Ảnh | Quan sát đường viền |
|---|---|
| [California Gull trên nền cát](runs/20261125-004828-3221b6/previews/California_Gull_0009_40662.png) | Nhìn rõ mỏ, thân và hai chân. Đường viền đi qua cả một phần bóng sát bàn chân. |
| [Black And White Warbler trên cành](runs/20261125-004828-3221b6/previews/Black_And_White_Warbler_0002_160376.png) | Thân và đuôi tách rõ. Các ngón bám cành bị mất một phần. |
| [American Pipit trong cỏ](runs/20261125-004828-3221b6/previews/American_Pipit_0029_99667.png) | Giữ được thân và đuôi, phần chân chìm trong cỏ. |
| [Bốn ảnh rà soát theo diện tích và độ lấp đầy hộp](runs/20261125-004837-613a30/review-extremes.png) | Hàng 1, `Golden_Winged_Warbler_0084_164541.jpg`, chỉ giữ một mảng bụng. Hàng 2, `Geococcyx_0067_104537.jpg`, dính một mảng nền lớn phía trên lưng. Hàng 4, `House_Sparrow_0002_112905.jpg`, bỏ mất phần đuôi. |

Các lỗi biên này ảnh hưởng cả histogram trong vùng chim lẫn đặc trưng hình dạng. Khi dùng dữ liệu cho phần 4, nhóm có thể nhận diện đúng các mẫu trên bằng tên JPG, xem bộ ba ảnh đối chiếu và dùng lệnh thay mặt nạ để cập nhật lại cả ba vector. Chưa có phép đo IoU với mặt nạ chuẩn cho bộ dữ liệu này.
