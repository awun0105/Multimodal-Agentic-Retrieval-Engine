# Phần 3 — VLM & Prompting

Sinh metadata JSON mô tả nội dung khung hình video, bằng mô hình Vision-Language.

Đây là tài liệu dành cho người **chưa từng làm việc với AI model**. Đọc từ trên
xuống, không nhảy cóc.

---

## 1. Phần này làm gì, và vì sao cần nó

Hệ thống tìm kiếm video của nhóm hoạt động theo nguyên tắc: **biến mọi thứ thành chữ, rồi tìm trong chữ**.

Video có 4 nguồn thông tin có thể biến thành chữ:

| Nguồn | Ai làm | Lấy được gì |
|---|---|---|
| Chữ hiện trong ảnh (biển hiệu, phụ đề) | Phần 2 — OCR | "CẤM ĐỖ XE" |
| Lời nói trong video | Phần 2 — ASR | "hôm nay trời mưa rất to" |
| Ảnh → vector số | Phần 1 — Embedding | `[0.23, -0.11, ...]` |
| **Mô tả cảnh bằng câu văn** | **Phần 3 — cái này** | "người mặc áo đỏ chạy xe qua đường ngập" |

Vì sao cần phần 3 khi đã có phần 1? Vì embedding hiểu ảnh theo kiểu "cảm nhận
tổng quát" — nó biết ảnh này *giống* câu truy vấn tới mức nào, nhưng không nói
được **cụ thể trong ảnh có gì**. Khi giám khảo hỏi *"cảnh người đàn ông áo đỏ
dắt xe qua chỗ ngập"*, việc có sẵn một câu mô tả bằng chữ giúp tìm bằng từ khóa
— thứ mà embedding làm không tốt.

**Đầu vào:** một tấm ảnh.
**Đầu ra:** một object JSON như sau:

```json
{
  "doi_tuong": ["xe máy", "người"],
  "mau_sac": ["đỏ"],
  "hanh_dong": "đang chạy",
  "boi_canh": "đường ngập nước dưới trời mưa",
  "caption_chi_tiet": "Một người đàn ông mặc áo mưa đỏ đang chạy xe máy qua đoạn đường ngập nước dưới cơn mưa tầm tã.",
  "caption_en": "A man in a red raincoat rides a motorbike through a flooded street in heavy rain."
}
```

---

## 2. Vài khái niệm cần biết trước

**VLM (Vision-Language Model)** — mô hình vừa "nhìn" được ảnh vừa viết được câu
văn. Khác với model chỉ đọc chữ (như ChatGPT thuần văn bản), VLM nhận thêm ảnh
làm đầu vào.

**Lượng tử hóa 4-bit** — mô hình gốc lưu mỗi con số bằng 16 bit. Nén xuống 4 bit
thì dung lượng còn khoảng 1/4, đổi lại độ chính xác giảm nhẹ (2–3%). Đây là cách
duy nhất để chạy model 7 tỷ tham số trên card đồ họa phổ thông. Đề bài **bắt buộc**
dùng kỹ thuật này.

**VRAM** — bộ nhớ riêng của card đồ họa. Model phải nạp hết vào đây mới chạy được.
VRAM không đủ → lỗi "out of memory", không có cách nào lách ngoài việc dùng model
nhỏ hơn.

**Vision tower** — phần "mắt" của model, chuyên xử lý ảnh. Chúng ta cố tình
**không nén** phần này, vì nén nó làm chất lượng mô tả giảm mạnh trong khi tiết
kiệm được rất ít bộ nhớ.

**Prompt** — câu lệnh ta viết cho model. Ở đây prompt có nhiệm vụ đặc biệt: ép
model chỉ trả JSON, không nói thêm câu nào.

---

## 3. Cấu trúc thư mục

```
vlm_prompting/
├── vlm/                          ← code chính
│   ├── schema.py                 hình dạng JSON đầu ra + ép kiểu
│   ├── prompts.py                câu lệnh gửi cho model
│   ├── json_utils.py             cứu JSON khi model trả sai định dạng
│   ├── model_registry.py         danh sách 5 model + cấu hình
│   ├── model_loader.py           nạp model, lượng tử hóa 4-bit
│   ├── adapters.py               3 backend: vLLM / transformers / mock
│   ├── generate.py               generate_json() — trái tim của phần này
│   └── provider.py               cắm vào hệ thống lõi system1
├── scripts/
│   ├── smoke_one_image.py        chạy thử 1 ảnh
│   ├── prepare_sample_images.py  chuẩn bị ≥100 ảnh test
│   ├── benchmark_runner.py       chạy benchmark, 2 chế độ DEBUG/MASS
│   ├── metrics.py                tính 6 chỉ số đề bài
│   ├── checkpoint_utils.py       lưu tiến độ, chống mất khi ngắt phiên
│   └── kaggle_smoke.ipynb        notebook chạy trên Kaggle
├── data/frames/                  ảnh test (không commit lên git)
├── results/                      kết quả benchmark
├── report.md                     báo cáo bàn giao
└── requirements.txt              thư viện cần cài
```

**Vì sao chia nhiều file thay vì một file to?** Mỗi file lo đúng một việc. Khi
prompt cho kết quả kém, bạn chỉ mở `prompts.py` — không phải dò trong 500 dòng
lẫn lộn. Đây cũng là quy ước của repo (mỗi file dưới 200 dòng).

---

## 4. Giải thích từng file

### 4.1 `vlm/schema.py` — hình dạng dữ liệu đầu ra

Định nghĩa JSON trả về phải có những trường gì. Dùng thư viện Pydantic để **tự
động kiểm tra** dữ liệu.

Vì sao cần kiểm tra? Vì model là thứ *xác suất* — cùng một câu lệnh, lần này trả
đúng, lần sau có thể thiếu trường hoặc sai kiểu. Pydantic bắt lỗi ngay tại chỗ
thay vì để dữ liệu hỏng lọt xuống các bước sau.

Hai việc file này làm:

**Ép kiểu tự động.** Model đôi khi trả `"xe máy, người"` (một chuỗi) thay vì
`["xe máy", "người"]` (một mảng). Thay vì báo lỗi, code tự tách theo dấu phẩy.

**Chặn caption cụt.** Model nhỏ hay trả lời kiểu "một con mèo" — đúng nhưng vô
dụng cho tìm kiếm. Ta bắt buộc `caption_chi_tiet` dài tối thiểu 25 ký tự.

Hàm `to_shot_caption_row()` chuyển kết quả sang đúng định dạng bảng của hệ thống
lõi (`system1/schemas/shot_captions.schema.json`). Tách riêng vì hai thứ khác
nhau: model chỉ biết nội dung ảnh, còn bảng dữ liệu cần thêm mã video, mốc thời
gian — thứ model không biết.

### 4.2 `vlm/prompts.py` — câu lệnh cho model

Đề bài yêu cầu: *"không sinh câu giao tiếp thừa, không giải thích ngoài JSON"*.

Model được huấn luyện để trò chuyện thân thiện, nên xu hướng tự nhiên của nó là
viết *"Chào bạn! Đây là mô tả ảnh: ..."*. Prompt phải chống lại xu hướng đó.

Ba kỹ thuật dùng trong file này:

1. **Đặt vai rõ ràng** — "Bạn là công cụ trích xuất metadata. Bạn KHÔNG phải trợ
   lý hội thoại." Câu này hiệu quả hơn nhiều so với việc chỉ dặn "đừng nói nhiều".
2. **Quy tắc đánh số** — model tuân thủ danh sách có số tốt hơn văn xuôi.
3. **Ví dụ mẫu** — cho model xem một JSON đúng để bắt chước. Đây là cách hiệu quả
   nhất trong ba cách.

`PROMPT_VERSION` đánh dấu phiên bản prompt. Cần thiết vì khi so sánh kết quả giữa
hai lần chạy, phải biết được là do đổi model hay do đổi prompt.

### 4.3 `vlm/json_utils.py` — cứu JSON hỏng

**Đừng bao giờ tin model trả JSON sạch ngay lần đầu.** Dù prompt viết chặt tới
đâu, sẽ có lúc model trả về:

````
Đây là kết quả phân tích:
```json
{"doi_tuong": ["người"]}
```
Hy vọng giúp ích cho bạn!
````

Hàm `parse_json_safe()` thử cứu theo ba tầng, từ rẻ tới đắt:

1. Đọc thẳng — trường hợp model ngoan
2. Bóc phần trong khối ```json
3. Quét thủ công tìm cặp ngoặc `{}` cân bằng

Tầng 3 không dùng regex đơn giản, vì JSON có ngoặc lồng nhau và ngoặc nằm trong
chuỗi. Regex thường sẽ cắt nhầm ở dấu `}` đầu tiên gặp phải. Code này đếm độ sâu
ngoặc và bỏ qua phần trong dấu nháy — đã kiểm tra với ca `{"t": "có dấu } trong chuỗi"}`.

Cả ba tầng thất bại → ném lỗi kèm **nguyên văn** output của model, để bạn đọc và
biết đường sửa prompt.

### 4.4 `vlm/model_registry.py` — danh sách model

Mỗi model là một dòng khai báo: tên trên HuggingFace, VRAM cần, cách nạp.

Nhờ file này, **đổi model chỉ cần đổi một chữ**:

```python
generate_json("anh.jpg", model_key="vintern-1b")   # thay vì qwen25vl-3b
```

Năm model đang có:

| Khóa | Model | VRAM (4-bit) | Ghi chú |
|---|---|---|---|
| `vintern-1b` | Vintern 1B v3.5 | ~1.5GB | Chuyên tiếng Việt. Mốc so sánh bắt buộc. |
| `qwen2vl-2b` | Qwen2-VL 2B | ~2GB | Nhẹ. Đồng đội đo ~1.25s/ảnh trên RTX 4060. |
| `qwen25vl-3b` | Qwen2.5-VL 3B | ~3GB | **Mặc định.** Cân bằng nhất. |
| `minicpm-v-4` | MiniCPM-V 4.0 | ~3GB | Đường lui cho máy yếu. |
| `qwen25vl-7b` | Qwen2.5-VL 7B | ~5.5GB | Tốt nhất, cần GPU ≥12GB. |

`goi_y_theo_vram()` tự chọn model vừa với card của bạn. Nó trừ hao 1.5GB cho ảnh
đầu vào và bộ nhớ tạm — không trừ thì model vừa khít sẽ tràn lúc chạy thật.

### 4.5 `vlm/generate.py` — hàm chính

Đây là file đề bài yêu cầu: `generate_json(image)`.

Luồng xử lý:

```
ảnh vào  →  chuẩn hóa về RGB  →  ghép prompt  →  model chạy
         →  cứu JSON  →  kiểm tra bằng Pydantic  →  dict trả ra
```

Ba quyết định thiết kế đáng chú ý:

**Nạp thư viện muộn (lazy import).** `torch` chỉ được nạp khi thực sự chạy model.
Nhờ vậy máy chưa cài torch vẫn `import` được module để chạy thử phần schema và
prompt. Không có nó, bạn sẽ bị chặn ngay dòng đầu tiên.

**Model nạp một lần rồi giữ lại (cache).** Nạp model mất 30–60 giây. Nạp lại cho
mỗi ảnh thì chạy 100 ảnh sẽ mất cả tiếng chỉ để chờ.

**Giữ vision tower ở FP16.** Trong `_tao_quant_config()` có dòng
`llm_int8_skip_modules` — bảo bộ nén "đừng đụng vào phần mắt". Nén cả phần này
làm chất lượng mô tả giảm rõ trong khi tiết kiệm rất ít bộ nhớ.

Các trường bắt đầu bằng `_` trong kết quả (`_latency_sec`, `_vram_peak_gb`...)
là thông tin kỹ thuật phục vụ benchmark, không thuộc JSON mà đề bài yêu cầu.

### 4.6 `scripts/smoke_one_image.py` — chạy thử

"Smoke test" là phép thử nhanh nhất: bật lên xem có bốc khói không.

**Vì sao phải thử 1 ảnh trước khi chạy 100 ảnh?** Lỗi hay gặp của người mới: viết
luôn vòng lặp 100 ảnh, chạy 40 phút, rồi phát hiện prompt sai ngay từ ảnh đầu.
Mất cả buổi. Một ảnh chạy 2 giây — sai thì sửa rồi chạy lại ngay.

---

## 5. Cách chạy

### Bước 1 — kiểm tra máy có gì

```bash
cd system1/research/vlm_prompting
python scripts/smoke_one_image.py --check
```

Lệnh này không cần cài gì, cho biết máy bạn chạy được model nào.

### Bước 2 — cài thư viện

⚠️ **Cần Python 3.10–3.12.** Python 3.13/3.14 chưa được PyTorch hỗ trợ.

```bash
pip install -r requirements.txt
```

### Bước 3 — chạy thử một ảnh

```bash
python scripts/smoke_one_image.py --image duong/dan/anh.jpg
```

Muốn xem model trả về gì trước khi xử lý:

```bash
python scripts/smoke_one_image.py --image anh.jpg --debug
```

Đổi model:

```bash
python scripts/smoke_one_image.py --image anh.jpg --model vintern-1b
```

### Dùng trong code

```python
from vlm import generate_json

ket_qua = generate_json("anh.jpg")
print(ket_qua["caption_chi_tiet"])
```

---

## 6. Chạy trên Kaggle (khuyến nghị)

Kaggle cho **30 giờ GPU miễn phí mỗi tuần**, card 16GB — mạnh hơn hầu hết máy cá
nhân. Không cần cài gì, chỉ cần trình duyệt.

Các bước:

1. Vào [kaggle.com](https://www.kaggle.com) → Code → New Notebook
2. Bên phải: Settings → Accelerator → chọn **GPU T4 x2** hoặc **P100**
3. Settings → Internet → **bật** (cần để tải model)
4. Dán code từ `scripts/kaggle_smoke.ipynb`
5. Run All

⚠️ **Phiên Kaggle tự ngắt sau 12 giờ.** Chạy hàng loạt phải lưu tiến độ thường
xuyên (mỗi 25 ảnh) — không thì mất trắng cả phiên.

---

## 7. Lỗi hay gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| `CUDA out of memory` | Model to hơn VRAM | Đổi sang model nhẹ hơn (xem bảng mục 4.4) |
| `No module named 'torch'` | Chưa cài thư viện | `pip install -r requirements.txt` |
| torch không cài được | Python 3.13/3.14 quá mới | Cài Python 3.11 hoặc dùng Kaggle |
| `JsonParseError` | Model trả kèm chữ thừa | Chạy `--debug` xem output thô, siết prompt |
| `UnicodeEncodeError` | Windows không in được tiếng Việt | Đã xử lý sẵn trong script |
| Caption bị cắt giữa chừng | `MAX_NEW_TOKENS` quá nhỏ | Tăng trong `generate.py` |
| Model lặp một câu vô hạn | `temperature` quá cao | Giữ 0.2–0.3 |

---

## 8. Điều quan trọng cần nhớ

**Caption do máy sinh ra có thể sai.** Model đôi khi "nhìn thấy" thứ không có
trong ảnh — gọi là *ảo giác*. Đây là gợi ý để tìm kiếm, không phải sự thật về nội
dung ảnh. Trước khi chạy hàng loạt, hãy đọc bằng mắt vài chục caption để tự đánh
giá chất lượng.

**Chưa ai kiểm chứng chất lượng tiếng Việt của các model này.** Nghiên cứu tính
tới 8/2026 cho thấy Qwen2.5-VL và InternVL3.5 chưa có điểm benchmark tiếng Việt
công khai. Vì vậy kế hoạch bắt buộc phải so với Vintern-1B (model chuyên tiếng
Việt) trước khi chốt — đó là lý do `vintern-1b` nằm trong danh sách.

---

## 9. Trạng thái

- [x] Phase 01 — nền móng, `generate_json()` chạy được 1 ảnh
- [x] Phase 02 — 5 model + 3 backend (vLLM / transformers / mock)
- [x] Phase 03 — chuẩn bị ảnh + khung đo 6 chỉ số + checkpoint
- [ ] Phase 04 — **chạy 100+ ảnh trên GPU thật** ← đang chờ
- [x] Phase 05 — provider cắm vào system1
- [x] Phase 06 — `report.md` (số benchmark chờ điền)

Toàn bộ code đã xong và kiểm thử ở chế độ mock. Việc còn lại là chạy trên GPU
thật (Kaggle) để có số đo, rồi điền vào `report.md`.

Kế hoạch đầy đủ: `plans/260815-2205-vlm-prompting-part3/`
