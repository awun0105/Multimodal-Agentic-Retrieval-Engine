# Bộ đo chất lượng caption (`quality/`)

Bộ này trả lời câu hỏi mà `scripts/metrics.py` không trả lời được:
**"Caption này có tìm được ảnh của chính nó không?"**

Ví dụ: caption *"Người giảng dạy đang giảng dạy"* — về mặt kỹ thuật nó là JSON
hợp lệ, đủ độ dài, đủ trường. `metrics.py` sẽ chấm điểm tối đa. Nhưng nó
KHỚP VỚI HÀNG NGHÌN ẢNH KHÁC (bất kỳ ảnh nào có người đang giảng bài). Giá
trị tìm kiếm của nó gần như bằng 0. Bộ `quality/` phát hiện đúng loại lỗi này.

## Chạy thế nào

```bash
cd system1/research/vlm_prompting

# Chấm 1 checkpoint đã chạy (từ benchmark_runner.py)
python -m quality.danh_gia_chat_luong --input results/checkpoint_qwen25vl-3b.json

# Chấm sample_results.json, ghi báo cáo ra file, xem 10 caption tệ nhất
python -m quality.danh_gia_chat_luong \
    --input results/sample_results.json \
    --out results/quality_report.json \
    --top-worst 10
```

Trên Windows, nếu thấy lỗi `UnicodeEncodeError` khi in tiếng Việt ra console,
đặt biến môi trường trước khi chạy: `set PYTHONIOENCODING=utf-8` (cmd) hoặc
`$env:PYTHONIOENCODING="utf-8"` (PowerShell).

## `recall@k` nghĩa là gì (giải thích không dùng thuật ngữ)

Tưởng tượng có 100 caption, mỗi caption ứng với một tấm ảnh. Với MỘT caption
bất kỳ, công cụ hỏi: "nếu tôi gõ đúng caption này vào ô tìm kiếm, hệ thống
có trả về đúng tấm ảnh mà caption đó mô tả hay không?"

- Nếu ảnh đúng nằm ở **vị trí số 1** trong kết quả tìm kiếm → tính là "trúng
  recall@1".
- Nếu ảnh đúng nằm trong **5 kết quả đầu** → tính là "trúng recall@5".
- `recall@1 = 0.8` nghĩa là: làm phép thử này trên tất cả caption, 80% số
  lần ảnh đúng đứng ở vị trí số 1.

**recall@1 cao = caption mô tả riêng biệt, dễ tìm lại đúng ảnh.**
**recall@1 thấp = nhiều caption giống nhau, tìm ra một đống ảnh lẫn lộn.**

`MRR` (Mean Reciprocal Rank) là một con số gộp: lấy nghịch đảo của hạng
(hạng 1 → 1.0, hạng 2 → 0.5, hạng 4 → 0.25...) rồi tính trung bình. Tiện khi
muốn so sánh nhanh mà không cần nhìn cả 3 con số recall@1/5/10.

## Vì sao dùng "self-retrieval" (tự tìm chính mình)

Cách đo recall chuẩn cần có **đáp án đúng** do con người gán sẵn ("ảnh này
nên khớp với query nào"). Cuộc thi không cho đáp án đó, và tự gán tay 92-1000
ảnh là không khả thi trong thời gian có hạn.

Self-retrieval né vấn đề này bằng một mẹo: **lấy chính caption của ảnh X làm
câu hỏi, rồi xem nó có tìm ra đúng ảnh X không.** Không cần ai chấm điểm bên
ngoài — nếu caption viết tốt (mô tả riêng biệt), nó sẽ tự khớp với chính nó
tốt hơn khớp với caption của ảnh khác.

## ⚠️ Không có mốc tuyệt đối — chỉ so sánh tương đối

**Quan trọng nhất trong toàn bộ tài liệu này:** không có con số nào kiểu
"recall@1 phải đạt 0.85 mới coi là tốt". Không có bảng chuẩn quốc tế cho bài
toán này.

Cách dùng ĐÚNG: chạy cùng một bộ ảnh, cùng một model, với **hai phiên bản
prompt khác nhau** (ví dụ prompt v2 và prompt v3). So hai con số recall@1
với nhau. Cái nào cao hơn → prompt đó tạo ra caption dễ tìm kiếm hơn. Chấm
hết — không suy diễn thêm "0.7 là tốt hay xấu" theo mốc tuyệt đối nào cả.

## Ba lỗi được kiểm tự động

| Lỗi | Cách bắt | Ví dụ thật đã gặp |
|---|---|---|
| Chép nguyên ví dụ mẫu trong prompt | So cụm 5 từ liên tiếp với ví dụ mẫu (`_VI_DU_MAU`) | Model trả nguyên câu "nồi kim loại màu bạc đun sôi trên bếp gas" dù ảnh không phải cảnh bếp |
| Nhét chữ đọc từ ảnh (OCR) vào danh sách vật thể | Đếm bao nhiêu phần tử không có dấu tiếng Việt | `doi_tuong: ["enjoy","admit","avoid",...]` — model đọc chữ trên bảng rồi tưởng đó là vật thể |
| Caption lặp từ, vòng vo | Type-token ratio (TTR) = số từ khác nhau / tổng số từ | "Người giảng dạy đang giảng dạy giảng dạy" |

Ba ngưỡng mặc định (đã dùng trong code, có thể chỉnh qua tham số hàm):

- N-gram trùng khớp ví dụ mẫu ≥ 1 → đánh dấu chép few-shot.
- Tỷ lệ phần tử không dấu trong `doi_tuong` > 50% → đánh dấu nhét OCR.
- TTR < 0.6 → đánh dấu vòng vo.

⚠️ **Đây là điểm khởi đầu, không phải số cố định mãi mãi.** Sau khi chạy
trên caption thật (Nhịp B), phải đọc tay ít nhất 10 caption bị đánh dấu tệ
nhất — nếu công cụ báo sai nhiều, chỉnh ngưỡng qua tham số rồi chạy lại.
Không sửa số trực tiếp trong code khi chưa có bằng chứng từ dữ liệu thật.

### Cạm bẫy từ mượn không dấu

Từ như `"laptop"`, `"ti vi"`, `"radio"` không có dấu tiếng Việt nhưng vẫn là
từ hợp lệ. Nếu không có danh sách miễn trừ, phép kiểm OCR sẽ báo nhầm hàng
loạt caption bình thường. Danh sách miễn trừ nằm ở
`caption_defect_checks.TU_MUON_MIEN_TRU` — mở rộng dần khi gặp từ mượn mới
bị báo nhầm trên dữ liệu thật.

## Cấu trúc file

```
quality/
  caption_loader.py          đọc checkpoint_*.json hoặc sample_results.json
  self_retrieval_bm25.py     đo recall@1/@5/@10 + MRR bằng BM25
  caption_defect_checks.py   3 phép kiểm lỗi ở trên
  danh_gia_chat_luong.py     CLI gộp tất cả, in bảng + ghi JSON
```

Không đụng vào `scripts/metrics.py` — file đó đo "có tuân thủ đề bài không"
(JSON hợp lệ, đủ trường), vẫn cần giữ để nộp bài. Hai bộ đo hai câu hỏi khác
nhau, không thay thế nhau.

## Giới hạn đã biết

- Tách từ tiếng Việt bằng cách tách theo khoảng trắng đơn giản, không dùng
  công cụ tách từ chuyên dụng (underthesea, pyvi...). Vì chỉ so sánh tương
  đối giữa hai phiên bản prompt trên cùng cách tách, sai số hệ thống sẽ
  triệt tiêu — không cần độ chính xác tuyệt đối ở bước này.
- Không gọi mạng, không gọi API — chạy hoàn toàn offline.
- Không in nội dung caption ra màn hình trừ khi bật `--top-worst` — tránh
  lộ dữ liệu cuộc thi ra log mặc định.
