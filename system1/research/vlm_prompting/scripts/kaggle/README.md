# Điều khiển Kaggle bằng API

Máy cá nhân không chạy được model (RTX 3050 Ti 4GB + Python 3.14, PyTorch chưa hỗ trợ),
nên mọi việc cần GPU đều làm trên Kaggle.

Ban đầu định điều khiển qua trình duyệt, nhưng bỏ: `connectOverCDP` của Playwright treo
với Chrome 151, còn CDP thuần mất ~2 phút mỗi lệnh. Với 15 lượt chạy thì không khả thi.

## Bắt buộc trước khi chạy bất kỳ script nào

Máy này có phần mềm chèn chứng chỉ vào HTTPS, `certifi` không xác thực được. Mọi script
ở đây đã gọi `truststore.inject_into_ssl()` trước khi import kaggle. Cần cài:

```bash
pip install truststore kaggle
```

Lệnh `kaggle ...` chạy thẳng **vẫn lỗi SSL** vì không đi qua đoạn inject — phải gọi script.

## Quy trình đầy đủ

```powershell
$env:TMP="D:\aic-tmp"; $env:TEMP="D:\aic-tmp"; $env:PYTHONIOENCODING="utf-8"

# 1. Upload dataset (chỉ làm một lần)
python kaggle-upload-dataset.py --jsonl <thư mục jsonl> --anh <thư mục ảnh> `
    --staging D:\aic-tmp\staging --tat-ca-anh

# 2. Kiểm cú pháp notebook TRƯỚC khi tốn GPU
python kiem-cu-phap-notebook.py notebook-train-qlora.ipynb

# 3. Đẩy + chạy (đây cũng chính là Save & Run All)
python kaggle-day-notebook.py --notebook notebook-train-qlora.ipynb `
    --meta <kernel-metadata.json> --staging D:\aic-tmp\nb-staging --chay-luon

# 4. Theo dõi
python kaggle-theo-doi.py

# 5. Đọc log (dùng cả khi lần chạy LỖI)
python kaggle-lay-log-web.py

# 6. Tải kết quả về
python kaggle-tai-adapter.py --tai-ve D:\aic-tmp\out --dich <thư mục đích>
```

## Vì sao đường API tốt hơn bấm nút

**Tránh hẳn bẫy GPU.** Cấu hình ghi trong `kernel-metadata.json`:

```json
{
  "enable_gpu": true,
  "machine_shape": "NvidiaTeslaT4",
  "enable_internet": true,
  "dataset_sources": ["<user>/<dataset-slug>"]
}
```

`kernels_push` tạo **phiên mới** với đúng cấu hình đó → không có chuyện "chọn GPU giữa
phiên không ăn thua", không cần Stop Session.

**Không lo mất dữ liệu.** `kernels_push` chính là Save & Run All — Kaggle tự lưu version
khi chạy xong, không phụ thuộc việc ai nhớ bấm nút.

## Hai cái bẫy của chính API

| Bẫy | Xử lý |
|---|---|
| `kernels_output()` **treo vô hạn** khi kernel lỗi | Dùng `kaggle-lay-log-web.py` — gọi thẳng endpoint |
| Log rỗng khi kernel đang `RUNNING` | Bình thường. Kaggle chỉ công bố log khi chạy xong |

## Khi nào vẫn cần trình duyệt

Đăng nhập lần đầu · xem quota GPU còn lại · dừng phiên giữa chừng (API không có
`kernels_stop`) · đọc kết quả hiển thị trong notebook web (nội dung nằm trong iframe).

Dùng `/browser` chế độ attach, đừng launch trình duyệt mới.

## Notebook

| File | Việc |
|---|---|
| `notebook-train-qlora.ipynb` | Train QLoRA Qwen2-VL-2B, 11 cell. Có cell kiểm nhanh bắt 5 loại hỏng trong ~10 giây |
| `notebook-benchmark-355.ipynb` | Chạy benchmark trên 355 keyframe. Có `--strict` + kiểm `latency=0` chặn số giả |

Cấu hình train bắt buộc cho T4 và lý do từng cái: `docs/kaggle-huong-dan-va-bay.md` mục 5bis.
