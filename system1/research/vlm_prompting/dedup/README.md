# dedup/ — Khử trùng lặp keyframe

## ⚠️ Đây là GIẢI PHÁP TẠM, không phải shot boundary detection thật

Repo hiện **chưa có phát hiện shot chính thức** — `system1/src/system1/shots/builder.py`
gán CẢ VIDEO = 1 shot (`detection_method="single_shot_fallback"`). Phát hiện shot
boundary thật là việc của code lõi (Phần 1), **không phải việc của module này**.

Module `dedup/` chỉ làm một việc hẹp: gom các keyframe **liền kề** (theo thứ tự tên
file) trông gần giống hệt nhau bằng heuristic rẻ (pHash / histogram màu), để tránh
phải caption lặp lại ảnh gần như y hệt trong cùng một cảnh. Khi code lõi có shot
boundary thật, module này nên bị thay thế bằng danh sách shot chính thức.

## Vì sao cần

`Keyframes_L25.zip` = 37.445 ảnh, batch 1 ước tính 300k–1M keyframe. Ở tốc độ VLM
hiện tại (~8,51s/ảnh) → hàng trăm giờ GPU, vượt xa ngân sách Kaggle 30h/tuần. Keyframe
cắt từ video có nhiều ảnh gần giống hệt nhau trong cùng cảnh → khử trùng lặp là cách
rẻ nhất để giảm số ảnh phải caption 5-20 lần mà không tốn GPU (chạy CPU local).

## Cách dùng

```bash
python -m dedup.chon_anh_dai_dien --frames-dir data/frames --out results/dedup_map.json
python -m dedup.chon_anh_dai_dien --frames-dir data/frames --nguong 15 --phuong-phap histogram
```

In ra: tổng ảnh vào, số nhóm, tỉ lệ giảm, thời gian xử lý.

## Thuật toán

- **Chỉ so ảnh LIỀN KỀ** theo thứ tự tên file (không so tất-cả-với-tất-cả).
  Lý do bắt buộc: O(n²) với 300k ảnh = 45 tỷ phép so, bất khả thi. Keyframe cùng
  cảnh vốn nằm cạnh nhau về thời gian (cùng tiền tố tên file) → so liền kề là đủ.
  Độ phức tạp: **O(n)**.
- **pHash** (mặc định) — biến thể average-hash: resize ảnh xám 8x8, so từng pixel
  với trung bình toàn ảnh → 64 bit. So 2 hash bằng khoảng cách Hamming. Rẻ, không
  cần thư viện ngoài (`imagehash`) — không được đụng `requirements.txt` (Phase 01
  sở hữu), nên tự cài bằng Pillow + numpy.
- **Histogram màu** — histogram RGB 16 bin/kênh, chuẩn hoá, so bằng khoảng cách
  Bhattacharyya. Bắt được đổi cảnh theo tông màu mà pHash (chỉ nhìn độ sáng) có
  thể bỏ lỡ.
- **Ngưỡng là tham số**, không chép cứng. Mặc định:
  - pHash: `10` (trên thang Hamming 0-64 bit)
  - histogram: `0.15` (trên thang Bhattacharyya 0-1)

  Chọn **chặt** (giữ thừa còn hơn bỏ nhầm) theo khuyến nghị rủi ro trong phase spec:
  2 ảnh cùng cảnh chỉ khác nén/độ sáng nhẹ thường lệch < 6 bit trong 64 bit của pHash;
  ngưỡng 10 đủ khoan dung với nhiễu nén/sáng mà không gộp nhầm 2 cảnh khác hẳn.

## `results/dedup_map.json`

```json
{
  "so_nhom": 2,
  "tong_anh": 5,
  "nhom": [
    {"dai_dien": "a01.jpg", "thanh_vien": ["a01.jpg", "a02.jpg", "a03.jpg"]},
    {"dai_dien": "b01.jpg", "thanh_vien": ["b01.jpg", "b02.jpg"]}
  ],
  "anh_toi_nhom": {"a01.jpg": 0, "a02.jpg": 0, "a03.jpg": 0, "b01.jpg": 1, "b02.jpg": 1}
}
```

- `nhom`: đại diện → cả nhóm (dùng khi caption xong, cần lan caption cho cả nhóm).
- `anh_toi_nhom`: ảnh bất kỳ → chỉ số nhóm (dùng khi tìm kiếm ra 1 ảnh, cần suy ngược
  về nhóm/đại diện). Có cả 2 chiều thì tra cứu đằng nào cũng O(1).
- Chỉ chứa tên file, không chứa nội dung ảnh — nhẹ, chia sẻ trong nhóm được.
- Khử trùng lặp **chỉ đọc** ảnh gốc, không xoá, không sửa. Ảnh bị loại vẫn nằm
  nguyên trên đĩa. Hoàn tác = xoá `dedup_map.json`.

## ⚠️ Về tỉ lệ giảm — CHƯA đo được số thật

`data/frames/` trên máy local chỉ có 37 ảnh **tải từ mạng (COCO val2017)**, mỗi tấm
một chủ đề khác hẳn nhau (xem `data/README.md`) — **KHÔNG phải keyframe cắt từ video
AIC**. Chạy CLI trên bộ này ra tỉ lệ giảm ~1,00x (không gom được nhóm nào) — con số
đó **vô nghĩa với mục tiêu thật**, chỉ chứng minh CLI chạy được, không đại diện cho
hiệu quả trên keyframe video thật.

Tỉ lệ giảm thực tế trên ≥500 keyframe AIC thật **chưa đo được** — cần tải keyframe
qua `scripts/tai_anh_tu_zip_tren_mang.py` (đã có) hoặc chạy trên Kaggle nơi có sẵn
dataset `nhathoang42/aic2025-keyframes`. Đây là việc còn lại, không thuộc phạm vi
nhịp local CPU của Phase 04.

## Ràng buộc

- Không import `torch`/`transformers` — chỉ Pillow + numpy, chạy CPU thuần.
- Không sửa `system1/src/system1/shots/builder.py` (code lõi, Phần 1 sở hữu).
- 1.000 ảnh xử lý < 60 giây trên CPU (đo thật: xem báo cáo cook).
