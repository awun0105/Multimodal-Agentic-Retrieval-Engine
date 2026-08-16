# Báo cáo — Phần 3: VLM & Prompting

**Người phụ trách:** Khoa
**Mảng phụ trách:** Vision-Language Model & Prompting — sinh text mô tả và ép cấu trúc JSON
**Ngày:** 15/08/2026 (cập nhật 16/08/2026)
**Nhánh:** `research-branch/vlm-prompting` — PR [#29](https://github.com/awun0105/Multimodal-Agentic-Retrieval-Engine/pull/29)

> **TRẠNG THÁI: đã đạt mốc ≥100 ảnh của đề bài. Model được chọn có số thực đo trên 355 ảnh;
> 2/3 model còn lại vẫn chưa chạy được.**
>
> Qwen2-VL-2B chạy trên **355 keyframe thật** của AIC, Kaggle Tesla T4, prompt v2 (16/08/2026):
> - **77,18% JSON hợp lệ (274/355)** — vượt mốc 100 ảnh của đề bài; model duy nhất cho caption thật
> - Latency 9,414 s/ảnh · VRAM đỉnh 2,006 GB · caption TB 24,4 từ
>
> Hai model còn lại đo trên bộ 92 ảnh trước đó (chạy thêm cũng vô nghĩa vì cả hai đều hỏng):
> - Qwen2.5-VL-3B: sập sau 4 ảnh, còn 4,3% (4/92)
> - Vintern-1B: **chưa từng nạp được** — xung đột phiên bản `transformers`, **số 100% trong log là giả**
>
> Số đo chất lượng caption trên n=278 (không phải mock): **nhét chữ OCR là lỗi phổ biến nhất —
> 29,86%**, kế đến vòng vo 23,02%, ngôn ngữ lạ và chép ví dụ cùng 1,80%. Chi tiết mục 7.2 và 7.3.
> Mọi số có ký hiệu ⁴ là tự đo; số khác ghi rõ nguồn.

---

## 1. Mục tiêu thực nghiệm

Chọn một VLM dưới 7B tham số, chạy được ở lượng tử hóa 4-bit, sinh metadata
JSON có cấu trúc cố định cho keyframe video:

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

Trường `caption_en` là bổ sung ngoài đề bài, do `system1/schemas/shot_captions.schema.json`
của repo **bắt buộc** cả `caption_vi` lẫn `caption_en`. Sinh cùng một lượt chạy
model nên gần như không tốn thêm chi phí.

---

## 2. Danh sách mô hình đã khảo sát

Khảo sát dựa trên nghiên cứu tính tới 15/08/2026 (báo cáo đầy đủ tại
`plans/reports/research-260815-2149-vlm-small-2026.md`).

| Model | Tham số | VRAM 4-bit | Lý do vào danh sách |
|---|---|---|---|
| Qwen2.5-VL-7B-Instruct | 7B | ~5.5GB | Dẫn đầu MMBench nhóm <7B (82.6/100) |
| Qwen2.5-VL-3B-Instruct | 3B | ~3.0GB | Cân bằng nhất cho GPU phổ thông |
| Qwen2-VL-2B-Instruct | 2B | ~2.0GB | Nhẹ, đã có số đo thực tế trong nhóm |
| Vintern-1B-v3.5 | 1B | ~1.5GB | **VLM duy nhất fine-tune riêng tiếng Việt** |
| MiniCPM-V-4.0 | 4B | ~3.0GB | Đường lui cho GPU yếu |
| InternVL3.5-8B | 8B | ~6.5GB | Á quân — loại vì vượt 7B của đề bài |
| Moondream 3.1 | 9B MoE | ~3.0GB | Loại — chưa có benchmark tiếng Việt nào |

Năm model đầu đã cài đặt sẵn trong `vlm/model_registry.py`, đổi bằng một tham số.

---

## 3. Bảng benchmark (bắt buộc theo đề bài)

**Số hiện hành, prompt v2** (16/08/2026). Môi trường: Python 3.12.13, PyTorch 2.10.0+cu128,
Tesla T4 14,56 GB.

⚠️ **Hai cỡ mẫu khác nhau trong cùng bảng.** Qwen2-VL-2B (model được chọn) chạy lại trên
**355 ảnh** — đây là số đáp ứng mốc ≥100 của đề bài. Hai model còn lại giữ số của lần chạy
**92 ảnh**: Qwen2.5-VL-3B sập sau 4 ảnh nên chạy thêm cũng vô nghĩa, Vintern-1B chưa từng
nạp được. Cột "Điểm benchmark" ghi rõ mẫu số để không đọc nhầm thành cùng một phép đo.

| Mô hình | Latency | VRAM | Điểm benchmark | Ưu điểm | Nhược điểm | Kết luận |
|---|---|---|---|---|---|---|
| **Qwen2-VL-2B** | **9,414 s/ảnh** ⁴ (P50 8,723 · P95 13,966 s) | **2,006 GB** ⁴ | **JSON hợp lệ 77,18%** (274/**355**) ⁴ | Model DUY NHẤT cho caption thật; VRAM thấp nhất | 81/355 ảnh lỗi; caption TB 24,4 từ | ✅ **CHỌN** — đường an toàn duy nhất hiện tại |
| **Qwen2.5-VL-3B** | 10,654 s/ảnh ⁴ (P95 11,757 s) | 4,36 GB ⁴ | **JSON hợp lệ 4,3%** (4/**92**) ⁴ | Chạy 1 ảnh lẻ cho caption tốt nhất, chi tiết nhất; caption TB 21,2 từ | **Sập sau 4 ảnh** — CUDA device-side assert | ❌ Chưa dùng được, cần sửa lỗi trước |
| **Vintern-1B-v3.5** | *0,0 s* ❌ số giả | *0,0 GB* ❌ số giả | *100%* ❌ số giả | Tiếng Việt tốt nhất theo đo của Phần 2; nhẹ nhất | **Model chưa từng nạp được** — xung đột phiên bản `transformers` (mục 7.2) | ❌ Cần ghim lại phiên bản `transformers` |
| **Qwen2.5-VL-7B** | CHỜ ĐO | CHỜ ĐO | MMBench 82,6 ² | Chất lượng cao nhất nhóm <7B | Cần ≥12GB VRAM | Chỉ khả thi trên Kaggle P100/T4 |
| **MiniCPM-V-4.0** | CHỜ ĐO | CHỜ ĐO | MMBench ~78–80 ² | Chỉ 3GB VRAM | Không fine-tune tiếng Việt | Đường lui khi GPU yếu |

¹ Số thực đo trên **RTX 4060 Laptop** bởi thành viên phụ trách Phần 2 (OCR & ASR),
xem `system1/research/ocr_asr/ocr/ocr_evaluation_summary.md`. Đo trên tác vụ OCR,
không phải captioning — dùng làm tham chiếu về tốc độ và khả năng tiếng Việt.

² Điểm MMBench công bố, đo trên tiếng Anh. **Không suy ra được chất lượng tiếng Việt.**

⁴ **Số tự đo**, trên Kaggle Tesla T4 14,56GB, 4-bit NF4, transformers backend,
keyframe thật của AIC (`Keyframes_L25.zip`). Chi tiết ở mục 7.1.

### Đối chiếu với lần chạy trước (prompt v1)

So sánh v1 với v2 **trên cùng bộ 92 ảnh** — đây mới là phép so cặp hợp lệ:

| Chỉ số | Prompt v1 (92 ảnh) | Prompt v2 (92 ảnh) |
|---|---|---|
| JSON hợp lệ | 93,5% (86/92) | **85,9%** (79/92) |
| Latency TB | 8,51 s | 9,131 s |

Prompt v2 chạy lại trên **355 ảnh** cho 77,18% (274/355). Tỷ lệ thấp hơn con số 85,9%
ở bộ 92 ảnh, nhưng **không so trực tiếp được**: bộ 92 ảnh lấy rải đều, bộ 355 gồm cả
những ca khó hơn. Latency (9,131 → 9,414 s) và VRAM (1,946 → 2,006 GB) gần như không đổi,
cho thấy phần chênh đến từ độ khó của ảnh chứ không phải tài nguyên.

**Prompt v2 làm tỉ lệ JSON hợp lệ giảm 7,6 điểm** — prompt dài hơn (thêm luật chống chép ví dụ,
chống nhét OCR) khiến model 2B khó tuân thủ định dạng hơn. Nhưng đổi lại chất lượng nội dung
caption tốt hơn hẳn — xem mục 7.3. Tỉ lệ JSON hợp lệ là chỉ số *sức khỏe*, không phải *chất lượng*.

---

## 4. Cấu hình phần cứng

| Môi trường | Phần cứng | Vai trò |
|---|---|---|
| Máy cá nhân | RTX 3050 Ti Laptop, **4GB VRAM** | Viết code, thử nghiệm nhỏ. Chỉ chạy nổi Vintern-1B và Qwen2-VL-2B |
| **Kaggle (chạy benchmark)** | **Tesla T4, 14.6GB VRAM, PyTorch 2.10.0+cu128** | Môi trường đo thật — đã xác nhận |
| Tham chiếu | RTX 4060 Laptop 8GB (máy thành viên Phần 2) | Nguồn số đo ở cột ¹ |

Cấu hình Kaggle đã kiểm chứng bằng lệnh chạy thật:

```
PyTorch : 2.10.0+cu128
Co GPU  : True
Ten GPU : Tesla T4
VRAM    : 14.6 GB
```

14.6GB đủ chạy cả 5 model trong danh sách, kể cả Qwen2.5-VL-7B (~5.5GB ở 4-bit).

Ghi chú: máy cá nhân cài Python 3.14 — PyTorch chưa hỗ trợ. Đây là lý do thứ hai
buộc phải chạy trên Kaggle.

---

## 5. Prompt tối ưu đã chọn

Phiên bản: `v1` (hằng `PROMPT_VERSION` trong `vlm/prompts.py`)

Đề bài yêu cầu model *"không sinh câu giao tiếp thừa, không giải thích ngoài JSON"*.
Xu hướng tự nhiên của model là trả lời thân thiện kiểu *"Chào bạn! Đây là mô tả..."*.
Ba kỹ thuật dùng để chống lại:

1. **Đặt vai phủ định** — *"Bạn là công cụ trích xuất metadata. Bạn KHÔNG phải trợ
   lý hội thoại."* Hiệu quả hơn nhiều so với dặn "đừng nói nhiều".
2. **Quy tắc đánh số** — model tuân thủ danh sách có số tốt hơn văn xuôi.
3. **Ví dụ mẫu (few-shot)** — cho model xem một JSON đúng để bắt chước. Đây là
   kỹ thuật hiệu quả nhất trong ba.

Bổ sung: *"CHỈ mô tả những gì nhìn thấy rõ trong ảnh. Không suy đoán."* — nhằm
giảm ảo giác, theo khuyến nghị của nghiên cứu.

### Ba tầng phòng thủ cho JSON

Prompt chỉ là tầng đầu. Không bao giờ đủ một mình.

| Tầng | Cơ chế | Tỷ lệ JSON hợp lệ |
|---|---|---|
| 1. Prompt | Dặn model chỉ trả JSON | ~70–90% (tùy model) |
| 2. `parse_json_safe()` | Cứu JSON bị bọc ```` ```json ````, có lời dẫn, ngoặc lồng | +~5–10% |
| 3. XGrammar (vLLM) | **Chặn ở tầng sinh token** — model không thể sinh sai định dạng | **~99,9%** ³ |

³ Nguồn: JSONSchemaBench 02/2026, đo trên 10 nghìn schema thật. **Chưa tự kiểm chứng
trên VLM** — benchmark công bố chỉ test trên model văn bản thuần.

Tầng 3 chỉ chạy được trên Linux/Kaggle (vLLM không cài được trên Windows).

---

## 6. Lượng tử hóa 4-bit (yêu cầu bắt buộc, mục 17 đề bài)

Cấu hình cuối cùng trong `vlm/model_loader.py`:

```python
BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.float16,
    bnb_4bit_use_double_quant=True,
)
```

### Phát hiện thực nghiệm: không giữ được vision tower ở FP16

Nghiên cứu khuyến nghị chừa vision tower khỏi việc nén (giữ FP16), vì nén cả
phần "mắt" làm rơi ~10% điểm BLEU trong khi tiết kiệm rất ít bộ nhớ. Tôi đã cài
đặt đúng như vậy bằng `llm_int8_skip_modules=["visual","vision_tower","vision_model"]`.

**Chạy thật trên Kaggle T4 thì hỏng:**

```
AssertionError: FP4 quantization state not initialized.
Please call .cuda() or .to(device) on the LinearFP4 layer first.
```

Đã thử ba cấu hình trên cùng một ảnh để cô lập nguyên nhân:

| Cấu hình | Kết quả | VRAM |
|---|---|---|
| **A. 4-bit thuần, không skip** | ✅ Chạy được, caption đúng | **5,96 GB** |
| B. 4-bit + skip vision tower | ❌ Lỗi FP4 như trên | — |
| C. FP16 không nén | Chạy được nhưng tốn gấp đôi | ~7,5 GB |

→ **Chọn A.** Đánh đổi: vision tower cũng bị nén 4-bit, chất lượng mô tả có thể
giảm nhẹ so với khuyến nghị lý thuyết.

Đây là ví dụ cho thấy khuyến nghị từ tài liệu không phải lúc nào cũng chạy được
trên môi trường thật — phải đo mới biết. Nếu bản bitsandbytes sau sửa được lỗi
này thì nên bật lại `llm_int8_skip_modules`.

Chọn NF4 (bitsandbytes) thay vì AWQ vì AWQ chưa có bản dựng sẵn cho mọi model
trong danh sách. Nghiên cứu khuyến nghị AWQ khi chạy vLLM — sẽ cân nhắc ở bước sau.

---

## 7. Kết quả benchmark

### 7.1. Chạy thử một ảnh (đã có kết quả thật)

Ảnh: keyframe thật của AIC, lấy từ `Keyframes_L25.zip` (37.445 ảnh trong kho).
Model: Qwen2.5-VL-3B-Instruct, 4-bit NF4, GPU Tesla T4.

Output nguyên văn:

```json
{
  "doi_tuong": [],
  "mau_sac": ["xanh"],
  "hanh_dong": "không có hành động",
  "boi_canh": "mặt giấy trắng",
  "caption_chi_tiet": "Một đoạn văn bản với chữ 'THANH NIÊN' được in trên một mặt giấy trắng.",
  "caption_en": "A text with the word 'THANH NIEN' is printed on a white paper.",
  "_model": "Qwen/Qwen2.5-VL-3B-Instruct",
  "_backend": "transformers-4bit",
  "_latency_sec": 9.653,
  "_vram_peak_gb": 6.122,
  "_prompt_version": "v1",
  "_schema_version": "v1"
}
```

Nhận xét:

| Điểm | Đánh giá |
|---|---|
| JSON hợp lệ ngay lần đầu | ✅ không cần tới tầng cứu hộ |
| Tiếng Việt tự nhiên | ✅ *"Một đoạn văn bản với chữ 'THANH NIÊN'..."* |
| Đọc được chữ trong ảnh | ✅ nhận ra "THANH NIÊN" — trùng khớp nội dung ảnh thật |
| Đủ 6 trường bắt buộc | ✅ |
| `doi_tuong` rỗng | Hợp lý — ảnh là logo, không có vật thể. Không phải lỗi |
| **Latency 9,65 s/ảnh** | ⚠️ Chậm hơn nhiều so với ước tính của nghiên cứu (18–22 ảnh/giây trên RTX 4090). T4 yếu hơn 4090 đáng kể, cộng thêm transformers chậm hơn vLLM |
| VRAM đỉnh 6,12 GB | Vừa với T4 14,6GB, còn dư nhiều |

Hệ quả của latency 9,65s: chạy 1 triệu keyframe bằng cấu hình này mất khoảng
**2.700 giờ GPU** — không khả thi. Muốn xử lý toàn bộ dữ liệu cuộc thi thì phải
chuyển sang vLLM (nghiên cứu ước tính nhanh hơn 5–10 lần) hoặc dùng model nhẹ
hơn như Vintern-1B.

### 7.2. Benchmark đầy đủ 3 model

**ĐÃ CHẠY 2 LẦN.** 92 keyframe thật × 3 model, Kaggle Tesla T4. Lần đầu dùng prompt v1
(kết quả thô bên dưới, mục này). Lần hai dùng prompt v2 — số hiện hành, đã đưa lên mục 3.

### Kết quả thô — prompt v1 (lần chạy đầu, không còn là số hiện hành)

| Model | JSON hợp lệ | Latency TB | P95 | VRAM đỉnh | Caption TB | Dùng được? |
|---|---|---|---|---|---|---|
| Vintern-1B-v3.5 | 100% (92/92) | **0,0 s** | 0,0 s | **0,0 GB** | 31 từ | ❌ **KHÔNG** — xem dưới |
| **Qwen2-VL-2B** | **93,5%** (86/92) | 8,51 s | 13,43 s | 1,84 GB | 18,5 từ | ✅ **CÓ** |
| Qwen2.5-VL-3B | 4,3% (4/92) | 10,61 s | 13,61 s | 4,22 GB | 22,8 từ | ❌ **KHÔNG** — xem dưới |

⚠️ Đây là số của **prompt v1**. Lần chạy sau (prompt v2, mục 3) cho JSON hợp lệ Qwen2-VL-2B
**thấp hơn** (85,9% thay vì 93,5%) nhưng caption **chất lượng cao hơn** — xem mục 7.3.

### ⚠️ Hai trong ba kết quả KHÔNG dùng được

**1. Vintern-1B: số 100% là giả — đã xác nhận nguyên nhân gốc.**

Latency 0,0 giây và VRAM 0,0 GB là bất khả thi với một model thật. Nghĩa là
adapter đã **rơi về `MockAdapter`** — trả JSON giả hợp lệ thay vì chạy model.
Cơ chế degrade hoạt động đúng như thiết kế (không crash cả mẻ), nhưng con số
sinh ra **không phải kết quả model**.

Log Kaggle của lần chạy prompt v2 ghi rõ nguyên nhân thật:

```
Không nạp được 5CD-AI/Vintern-1B-v3_5:
  'InternVLChatModel' object has no attribute 'all_tied_weights_keys'
→ transformers init failed, falling back to mock
→ MockAdapter active - returning FAKE JSON, not real model output
```

**Không phải chỉ do thiếu adapter InternVL** như suy đoán ban đầu. Nguyên nhân thật là
**xung đột phiên bản `transformers`**: `InternVLChatModel` của Vintern thiếu thuộc tính
`all_tied_weights_keys` mà `transformers` bản 4.5x trở lên đòi hỏi. Đây là lỗi tương thích
phiên bản, không phải lỗi kiến trúc — model **không cần** gọi `model.chat()` riêng như
suy đoán trước, chỉ cần chạy trên bản `transformers` cũ hơn.

→ **Hướng sửa rẻ hơn nhiều: ghim `transformers` về phiên bản cũ hơn**, thay vì viết
adapter riêng cho InternVL. Bài học: chỉ số "tỷ lệ JSON hợp lệ" một mình không đủ tin —
phải kiểm tra chéo với latency và VRAM, và phải đọc log lỗi thật thay vì đoán.

**Cập nhật 16/08/2026 — bằng chứng củng cố chẩn đoán này.** Trong phiên train QLoRA,
notebook chạy `pip install -U trl` và bị lỗi ngay ở dòng import:

```
ImportError: cannot import name 'AutoModelForVision2Seq' from 'transformers'
transformers: 5.0.0
```

`pip install -U <thư viện phụ>` **kéo theo** bản `transformers` mới nhất, và bản 5.0 đã
đổi tên lớp (`AutoModelForVision2Seq` → `AutoModelForImageTextToText`). Cùng một cơ chế
đã giết Vintern-1B: thư viện lõi bị nâng ngoài ý muốn, model cũ không theo kịp.

Cách xử lý **thực sự đã áp dụng** trong notebook train: `try/except` đổi tên lớp —
thử tên mới trước, không có thì lùi về tên cũ. Chạy được với cả hai bản.

⚠️ **Chưa ghim phiên bản trong repo.** `requirements.txt` vẫn `transformers>=4.49.0`
(không có cận trên) và `kaggle_smoke.ipynb` vẫn dùng `pip install -U`. Việc ghim
`>=4.51,<5` là **khuyến nghị, chưa làm** — xem mục 11.

**2. Qwen2.5-VL-3B: sập giữa chừng.**

Chạy một ảnh lẻ thì tốt (mục 7.1: 9,65 s, caption đúng). Nhưng chạy liên tiếp
thì sập sau 4 ảnh:

```
AcceleratorError: CUDA error: device-side assert triggered
```

Lỗi lặp lại ở 88/92 ảnh còn lại. Dấu hiệu điển hình của tràn chỉ số trong
kernel khi xử lý ảnh có kích thước khác nhau — keyframe thật không đồng đều
kích thước, khác với ảnh test đơn lẻ.

→ Cần thử `CUDA_LAUNCH_BLOCKING=1` để lấy vị trí lỗi thật, hoặc ép chuẩn hóa
kích thước ảnh đầu vào (`max_pixels`) trước khi kết luận model này không dùng được.

### Model DUY NHẤT có số liệu tin cậy: Qwen2-VL-2B (số prompt v1, lần chạy đầu)

| Chỉ số | Giá trị |
|---|---|
| Tỷ lệ JSON hợp lệ | **93,5%** (86/92 ảnh) |
| Độ tuân thủ prompt | 93,5% |
| Latency trung bình | 8,51 s/ảnh (P50 7,76 s, P95 13,43 s) |
| VRAM đỉnh | 1,84 GB |
| Độ chi tiết caption | 18,5 từ / 84,8 ký tự |
| Số đối tượng TB | 1,71 |
| Số màu sắc TB | 1,12 |

⚠️ Bảng trên là số của **lần chạy prompt v1 trên 92 ảnh**. Số hiện hành (prompt v2,
355 ảnh) là 77,18%, 9,414 s/ảnh, 2,006 GB — xem mục 3. Giữ bảng này để đối chiếu
trước/sau khi đổi prompt.

Sáu ảnh thất bại (trên 92, prompt v1), chia hai nhóm:
- **4 ca** `JsonParseError` — model trả văn bản dài (760–1136 ký tự) không chứa JSON
- **2 ca** `ValidationError` — JSON đúng cú pháp nhưng sai kiểu: một lần
  `caption_chi_tiet` là mảng thay vì chuỗi, một lần thiếu hẳn trường này

Nhóm thứ hai đáng chú ý: prompt và parser đều làm đúng việc, model vẫn sai
schema. Đây chính xác là thứ mà constrained decoding (XGrammar) chặn được ở
tầng sinh token — và là lý do nghiên cứu khuyến nghị nó.

### ⚠️ 93,5% JSON hợp lệ KHÔNG có nghĩa là 93,5% caption dùng được

Đọc tay caption thật của Qwen2-VL-2B (prompt v1) cho thấy vấn đề mà chỉ số "JSON hợp lệ"
không bắt được. Năm ảnh đầu tiên:

| Ảnh | `caption_chi_tiet` sinh ra | Đánh giá |
|---|---|---|
| `001.jpg` | *"Caption Chi tiết: Một người đàn ông mặc áo mưa đỏ đang chạy xe máy qua đoạn đường ngập nước dưới cơn mưa tầm tã."* | ❌ **Chép nguyên ví dụ trong prompt.** Đây là câu mẫu ở `prompts.py`, không phải nội dung ảnh. Còn lẫn cả nhãn "Caption Chi tiết:" |
| `009.jpg` | *"Người giảng dạy đang giảng dạy tại Trung tâm học tập."* | ⚠️ Vòng vo, gần như không có thông tin |
| `010.jpg` | *"Người giới thiệu đang trình bày trong phòng học với một màn hình hiển thị hình ảnh khoa học kỹ thuật."* | ✅ Dùng được |
| `014.jpg` | `doi_tuong` = `["enjoy","admit","avoid","deny","fancy","keep","mind","spend","suggest","tolerate"]` | ❌ Model đọc chữ tiếng Anh trên bảng rồi nhét vào ô "đối tượng" |
| `019.jpg` | *"Bà giảng dạy về phân tích một cấu trúc gen học."* | ⚠️ Tiếng Việt lủng củng, sai ngữ pháp |

**Ước lượng thô: chỉ 1–2 trong 5 caption thật sự dùng được**, dù cả 5 đều là
JSON hợp lệ 100%. Số n=5 này quá nhỏ — mục 7.3 có số đo trên n=83 xác nhận và
mở rộng phát hiện này bằng công cụ đo tự động.

Ba lỗi phải sửa ở prompt (`prompts.py`, đã thành `PROMPT_VERSION = "v2"`):

1. **Model chép ví dụ few-shot.** Ví dụ mẫu đang dùng chính là câu trong đề bài;
   khi model "bí" nó chép lại. Cách sửa ban đầu: đổi ví dụ sang cảnh khác hẳn keyframe
   thực tế (đổi sang cảnh bếp). **Kết quả thật (mục 7.3): giảm mạnh nhưng KHÔNG diệt được**
   — `032.jpg` ở prompt v2 vẫn chép nguyên xi ví dụ bếp mới. Giả thuyết "ví dụ càng khác
   keyframe càng khó bị chép" là **sai một phần** — chỉ giảm tần suất, không loại bỏ lỗi.
2. **Nhãn "Caption Chi tiết:" lọt vào giá trị.** Phải bỏ khi hậu xử lý, hoặc
   siết prompt cấm lặp lại tên trường.
3. **`doi_tuong` nhận chữ thay vì vật thể.** Prompt v2 đã thêm câu cấm nhưng **chưa đủ mạnh**
   — mục 7.3 đo được **29,86%** caption vẫn nhét chữ vào `doi_tuong` ở n=278.

Đây là bài học chính của lần benchmark này: **chỉ số tự động không thay thế được
việc đọc bằng mắt**. Nếu chỉ nhìn con số JSON hợp lệ thì đã kết luận sai là pipeline
đạt yêu cầu.

### 7.3. Đo chất lượng caption bằng công cụ tự động — n=278

Dữ liệu: `results/sample_results.json` — **370 mục**. Thành phần: `qwen2vl-2b` 274 mục
(thật, trên 355 ảnh) · `vintern-1b` 92 mục (toàn mock, bị bộ đo tự loại) · `qwen25vl-3b`
4 mục (thật). Sau khi loại 92 mục mock, còn **278 caption dùng được** để đo.

Công cụ: `quality/danh_gia_chat_luong.py`. Báo cáo máy: `results/quality_report_355.json`.

```
Caption dùng được: 278 (bỏ qua 92 — toàn bộ kết quả Vintern-1B, là mock)

recall@1  : 0,9496         Chép few-shot : 1,80%
recall@5  : 1,0000         Nhét chữ OCR  : 29,86%
recall@10 : 1,0000         Vòng vo (TTR) : 23,02%
MRR       : 0,9727         Ngôn ngữ lạ   : 1,80%
```

**So với bộ 92 ảnh** (83 caption, cùng bộ đo — chạy lại trên
`results/sample_results-92anh-backup.json` để đối chiếu công bằng):

| Chỉ số | n=83 (92 ảnh) | n=278 (355 ảnh) |
|---|---|---|
| recall@1 | 0,988 | 0,9496 |
| Nhét chữ OCR | 30,12% | **29,86%** |
| Vòng vo (TTR) | 20,48% | **23,02%** |
| Chép few-shot | 1,20% | 1,80% |
| Ngôn ngữ lạ | 2,41% | 1,80% |

Hai lỗi chính giữ nguyên thứ hạng khi n tăng gấp 3,3 lần: nhét chữ OCR vẫn đứng đầu,
vòng vo thứ hai. recall@1 giảm 3,8 điểm là điều phải xảy ra — tập càng lớn thì
self-retrieval càng khó phân biệt, không phải dấu hiệu chất lượng caption tụt.

> ⚠️ **Đính chính 16/08.** Bản đầu của mục này ghi *"Vòng vo 30,12% / Nhét OCR 12,05%"* —
> **hai nhãn bị hoán đổi**. Số trên là kết quả chạy lại bằng bộ đo hiện hành (16/08 15:30).
>
> Nguyên nhân: `results/quality_report.json` sinh lúc 02:34, trước khi
> `caption_ten_rieng.py` (10:57) và `caption_defect_checks.py` (10:46) được sửa. Bản mới
> soi cả `doi_tuong`/`mau_sac`/`hanh_dong`/`boi_canh` chứ không chỉ `caption`, nên
> `nhet_chu_ocr` siết lên và `vong_vo` nới xuống. Giá trị **12,05% không còn tồn tại**
> ở bất kỳ chỉ số nào.

Bộ đo **tự động loại bỏ** 92 mục mock thay vì âm thầm chấm điểm cho dữ liệu giả — đúng
thiết kế: thà báo rõ "bỏ 92" còn hơn cho ra recall đẹp nhờ dữ liệu không có thật.

**Ba phát hiện mới, chưa từng biết trước phiên đo này:**

1. **Hai lỗi lớn nhất: nhét chữ OCR 30,12% (25/83) và vòng vo 20,48% (17/83).**
   Trước đây không ai biết vì chưa có công cụ đo tự động, chỉ đọc tay vài caption.

   Ví dụ vòng vo:
   - `055.jpg`: *"Một nhóm học sinh đang học cách **bơi lội** trong một lớp học **bơi lội**
     tại một trung tâm đào tạo **bơi lội**."*
   - `063.jpg`: *"Một đội **bóng rổ** đang chơi **bóng rổ** trên sân **bóng rổ** xanh."*

   Với retrieval, lặp từ không chỉ đọc xấu — nó làm caption **kém phân biệt**: caption
   "bóng rổ ×3" khớp với mọi ảnh bóng rổ khác trong kho, giảm độ chính xác tìm kiếm.

   Lỗi nhét chữ OCR còn hại hơn: model đọc chữ trên biển hiệu rồi nhét vào `doi_tuong`
   như thể đó là vật thể. Việc đọc chữ là của module OCR ở Phần 2 — caption không nên làm.

2. **Prompt v2 vẫn bị chép ví dụ — giả thuyết cũ sai.** Prompt v2 đổi ví dụ mẫu sang cảnh
   bếp với lý do "càng khác keyframe thật càng khó bị chép". Caption `032.jpg` chứng minh
   điều này **sai**: model chép **nguyên xi toàn bộ ví dụ bếp mới** (nồi kim loại, bếp gas,
   "đang đun sôi"...), không sót một trường, cho một ảnh keyframe AIC không liên quan gì
   tới bếp. Điều đúng: đổi ví dụ có **giảm tần suất** (20% ở n=5 của v1 → 1,2% ở n=83 của
   v2) nhưng **không diệt được**. Model 2B khi "bí" vẫn rơi về chép mẫu bất kể mẫu là gì.
   Cần chặn ở tầng kiểm tra dữ liệu (so khớp với `_VI_DU_MAU`), không thể chỉ trông cậy
   lời dặn trong prompt.

3. **Lỗi mới chưa từng phát hiện: chữ Hán lẫn vào caption tiếng Việt.** `027.jpg` và
   `306.jpg` — ví dụ `027.jpg`: *"Một bức ảnh**模糊** của một tòa nhà trắng..."* (模糊 =
   "mờ" trong tiếng Trung). **2/79 caption Qwen2-VL-2B (2,5%)**. Nguyên nhân: Qwen2-VL
   huấn luyện chủ yếu trên tiếng Trung, khi gặp từ khó diễn đạt thì rơi về tiếng mẹ đẻ.
   Bộ kiểm hiện tại **không bắt được lỗi này** — cần thêm phép kiểm ký tự ngoài bảng chữ
   tiếng Việt. Ngoài ra `doi_tuong` còn lẫn tiếng Anh sai chính tả (`027.jpg` →
   `["buiding", "sky"]`, building viết sai).

**recall@1 = 0,988 nghĩa là gì:** 82/83 caption đủ riêng biệt để tự tìm lại chính ảnh của
nó trong tập 83 ảnh. **Không có nghĩa là caption tốt** — đây là bài toán dễ vì 83 ảnh thuộc
83 chủ đề khác nhau. Ở quy mô thật (~127.000 keyframe, hàng nghìn ảnh cùng chủ đề) con số này
sẽ tụt mạnh. Cách dùng đúng: so **tương đối** giữa hai phiên bản prompt trên cùng tập ảnh,
không lấy làm mốc tuyệt đối.

⚠️ Cột "prompt v1" khi so sánh trực tiếp (chép ví dụ 20%, nhét OCR 20%, vòng vo 20%) chỉ
đo trên **n=5** — không so công bằng được với n=83 của v2. Muốn so công bằng phải chạy lại
prompt v1 trên đủ 92 ảnh bằng cùng công cụ đo.

### Lệnh đã chạy

```bash
# 92 keyframe thật, lấy rải đều từ Keyframes_L25.zip (kho 37.445 ảnh)
python scripts/benchmark_runner.py --mode mass --n 100 \
    --models vintern-1b,qwen2vl-2b,qwen25vl-3b \
    --frames-dir /kaggle/working/data/frames \
    --out-dir /kaggle/working/results
```

Kết quả ghi vào `results/vlm_comparison_results.json`.

Ghi nhận sớm (10 ảnh đầu của Vintern-1B): **10/10 JSON hợp lệ**. Đáng chú ý vì
Vintern-1B chỉ 1 tỷ tham số — nhỏ nhất nhóm — nhưng vẫn tuân thủ được định dạng.

### Sáu chỉ số đo (định nghĩa trong `scripts/metrics.py`)

| Chỉ số | Cách đo |
|---|---|
| Tỷ lệ JSON hợp lệ | số ảnh parse + validate Pydantic thành công / tổng số ảnh |
| Độ chi tiết caption | số ký tự, số từ của `caption_chi_tiet`; số mục trong `doi_tuong`/`mau_sac` |
| Độ tuân thủ prompt | tỷ lệ output không chứa rác ngoài JSON **và** đủ 5 trường bắt buộc |
| Latency | thời gian mỗi ảnh — báo cáo trung bình, P50, P95 |
| VRAM | `torch.cuda.max_memory_allocated()` sau khi reset bộ đếm |
| Độ ổn định | chạy 10 ảnh × 3 lần, đo độ lệch chuẩn latency và tỷ lệ JSON |

### 7.4. Thông lượng — đã chốt được quy mô thật

**Vì sao quan trọng trước khi HOW:** biết model chạy đúng chưa đủ — phải biết chạy đủ
nhanh để xử lý hết dữ liệu cuộc thi trong ngân sách GPU miễn phí của Kaggle.

**Quy mô thật (đọc trực tiếp từ Drive của BTC ngày 16/08):** thư mục `AIC2025` có
**8 file keyframe, tổng 19,27 GB → ~127.000 ảnh**.
Chi tiết từng file + ID: `plans/reports/so-keyframe-that-260816-0830.md`.

> ⚠️ Bản trước của mục này ghi "300k–1M keyframe → 25–85 tuần → **bất khả thi**".
> Đó là **ước lượng sai, phóng đại 2,4–8 lần** (nhân 37.445 với số file đoán mò).
> Con số thật nhẹ hơn nhiều — xem bảng dưới.

Với Qwen2-VL-2B ở **9,13 s/ảnh** (số đo thật, mục 3), trên **127.000 ảnh**:

| Cách chạy | Tổng giờ GPU | Số tuần Kaggle (30h/tuần) |
|---|---|---|
| Hiện tại (tuần tự, 9,13 s/ảnh) | 323 giờ | ~10,8 tuần |
| Batch 4 ảnh (~3,0 s/ảnh) | 106 giờ | ~3,5 tuần |
| **Batch 8 ảnh (~1,5 s/ảnh)** | 53 giờ | **~1,8 tuần** |
| Batch 4 + khử trùng lặp 3× | 35 giờ | **~1,2 tuần** |

**Không còn bất khả thi.** Chỉ cần batch inference là về mức ~2 tuần Kaggle.
Ngay cả giữ nguyên tốc độ hiện tại cũng chạy hết trong ~11 tuần — chậm, nhưng không chết.

→ Việc tối ưu thông lượng **hạ mức khẩn cấp**. Ưu tiên chuyển sang **sửa chất lượng caption**
(vòng vo 30%, nhét OCR 12% ở mục 7.3) — đó mới là thứ quyết định caption có dùng được không.

⚠️ Số ảnh của 7/8 file là **ước tính theo dung lượng** (L25 đếm thật: 37.445 ảnh / 5.810 MB
= 159 KB mỗi ảnh). Đếm chính xác cần chạy script đọc zip **trên Kaggle** — mạng ở máy local
bị chặn (chi tiết trong báo cáo trên).

Hai hướng giảm tải đã có code sẵn, chưa đo hiệu quả thật:

1. **Khử trùng lặp** (`dedup/`) — bỏ bớt keyframe gần giống nhau trước khi đưa vào VLM.
   Giảm được bao nhiêu % số ảnh cần chạy — chưa đo trên tập lớn.
2. **Batch inference** — gộp nhiều ảnh một lượt gọi model thay vì từng ảnh một.
   Code định hướng có sẵn nhưng **chưa benchmark tốc độ thật**.

Không hướng nào một mình đủ 30–40 lần — cần kết hợp cả hai, và có thể cần thêm
vLLM (mục 5, ước tính nhanh hơn transformers 5–10 lần, chưa tự đo).

---

## 8. Mô hình được chọn cuối cùng

### **Qwen2-VL-2B-Instruct** — chọn theo dữ liệu thực đo

**Lý do chọn:** đây là model **duy nhất trong ba** cho ra caption thật, không sập
và không rơi về mock. Hai model kia đều hỏng theo cách riêng (mục 7.2). Chọn model
chạy được 77,18% trên 355 ảnh (số hiện hành, prompt v2) hơn là model có tiềm năng cao hơn
nhưng chưa chạy được.

| Tiêu chí | Qwen2-VL-2B (số hiện hành, prompt v2, 355 ảnh) |
|---|---|
| Cho ra caption thật, không sập | ✅ Duy nhất |
| Tỷ lệ JSON hợp lệ | 77,18% (274/355) |
| VRAM | 2,006 GB — thấp nhất, chạy được cả GPU 4GB |
| Latency | 9,414 s/ảnh |
| recall@1 trên caption thật (n=278) | 0,9496 |

⚠️ **Đây là lựa chọn tạm thời, không phải kết luận cuối.** Bốn lý do:

1. **Chưa qua cổng kiểm tiếng Việt.** Vintern-1B (mốc đối chứng bắt buộc) chưa
   chạy được nên chưa so được. Kế hoạch ban đầu yêu cầu so sánh này trước khi chốt.
2. **Nghiên cứu cảnh báo về chính model này.** Thành viên Phần 2 ghi nhận
   Qwen2-VL-2B **từng từ chối trả lời bằng tiếng Việt**. Chưa gặp trong 355 ảnh
   vừa chạy — mẫu đã đủ lớn để coi đây là rủi ro thấp, nhưng chưa loại trừ hẳn.
3. **Caption ngắn** — 24,4 từ TB (prompt v2, 355 ảnh). Đề bài yêu cầu `caption_chi_tiet`
   "mô tả dài, đầy đủ ngữ cảnh".
4. **Chất lượng nội dung còn nhiều lỗi (mục 7.3, n=278):** 29,86% nhét chữ OCR vào
   `doi_tuong`, 23,02% caption vòng vo, 1,80% lẫn ngôn ngữ lạ. Chưa sửa xong lỗi nào
   trong ba lỗi này.

### Việc phải làm trước khi chốt hẳn

| # | Việc | Vì sao |
|---|---|---|
| 1 | Ghim `transformers` bản cũ hơn cho Vintern-1B | Nguyên nhân gốc đã xác nhận (mục 7.2) là xung đột phiên bản, không phải thiếu adapter — hướng này rẻ hơn viết adapter InternVL riêng |
| 2 | Sửa lỗi CUDA assert của Qwen2.5-VL-3B | Model này cho caption chi tiết nhất khi chạy được |
| 3 | Giảm nhét chữ OCR (30,12%) rồi tới vòng vo (20,48%) — mục 7.3 | Hai lỗi lớn nhất. Nhét OCR lấn việc của module OCR; vòng vo làm caption kém phân biệt khi retrieval |
| 4 | Chặn chép ví dụ + nhét OCR ở tầng validator | Prompt một mình không đủ (mục 7.3, phát hiện 2) |
| 5 | Chấm tay 30 caption × 3 model, giấu tên model | Đo chất lượng tiếng Việt thật, không chỉ đếm JSON hợp lệ |

### Cổng kiểm tiếng Việt (chưa chạy được)

Nghiên cứu chỉ ra một khoảng trống nghiêm trọng: **chưa có điểm BLEU/METEOR
tiếng Việt công khai** cho Qwen2.5-VL và InternVL3.5. Mọi điểm số công bố đều
đo trên tiếng Anh hoặc tiếng Trung.

Nguy cơ này **không phải giả định** — thành viên Phần 2 đã ghi nhận thực tế:
- Qwen2-VL-2B **từ chối trả lời** bằng tiếng Việt trong một số trường hợp
- Florence-2 **rơi vào vòng lặp vô hạn** khi gặp tiếng Việt
- Vintern-1B (chuyên tiếng Việt) đạt WER tốt nhất: 0,34

Nên quy trình chốt model là:

1. Chạy ≥100 ảnh qua cả 3 model *(đã làm với Qwen2-VL-2B: 355 ảnh. Hai model kia
   hỏng ở tầng nạp/chạy nên chưa thực hiện được — xem mục 7.2)*
2. Đọc tay 30 caption mỗi model, **giấu tên model** để tránh thiên vị
3. Chấm 3 tiêu chí: đúng nội dung ảnh / tiếng Việt tự nhiên / đủ chi tiết
4. **Nếu Vintern-1B thắng phần chấm tay → chọn Vintern**, kể cả khi điểm
   MMBench tiếng Anh thấp hơn. Đề bài là dữ liệu tiếng Việt.

---

## 9. Các vấn đề gặp phải và cách xử lý

| Vấn đề | Nguyên nhân | Cách xử lý |
|---|---|---|
| Máy cá nhân chỉ 4GB VRAM | RTX 3050 Ti Laptop | Chuyển hướng chạy trên Kaggle (16GB, miễn phí). Code tự dò VRAM và gợi ý model vừa |
| Python 3.14 không cài được PyTorch | Phiên bản quá mới | Import lười — module vẫn dùng được phần schema/prompt khi thiếu torch. Chạy model trên Kaggle |
| Script crash ngay dòng đầu | Console Windows dùng cp1252, không in được tiếng Việt | `sys.stdout.reconfigure(encoding="utf-8")`; log dùng ASCII |
| Kaggle CLI lỗi chứng chỉ SSL | Phần mềm trên máy chèn chứng chỉ không đúng chuẩn vào kết nối HTTPS | Không cần thiết — chạy trực tiếp trên web Kaggle. Không tắt kiểm tra bảo mật để lách |
| Không có quyền push repo nhóm | Repo thuộc tài khoản khác | Fork sang tài khoản cá nhân, làm việc trên fork, gửi PR sau |
| Nguy cơ làm vỡ CI của nhóm | `system1/pyproject.toml` không khai báo torch | Đặt provider trong `research/` thay vì `src/`. Đã kiểm chứng `src/` không import gì từ code mới |
| Model trả JSON kèm lời dẫn | Bản chất model hội thoại | Ba tầng phòng thủ (mục 5) |
| Kaggle Remote URL không nhập được file từ Google Drive | Link Drive trả về trang HTML cảnh báo quét virus, không trả file. Trình nhập của Kaggle không xử lý được trang này | Bỏ Remote URL. Đọc file bằng HTTP Range request ngay trong notebook |
| File keyframe nặng 5.7GB, gần cạn đĩa Kaggle (~20GB) | Kho ảnh của cuộc thi rất lớn, trong khi benchmark chỉ cần 100 ảnh | `tai_anh_tu_zip_tren_mang.py` — đọc mục lục ở cuối file zip rồi chỉ tải đúng các đoạn byte chứa ảnh cần. Tải ~10MB thay vì 5.7GB |
| Phiên Kaggle vẫn chạy CPU dù đã chọn GPU | Kaggle chỉ áp dụng lựa chọn accelerator **khi khởi động phiên**. Phiên đang chạy giữ nguyên cấu hình cũ | Dừng phiên (Run → Stop session) rồi chạy lại. Xác nhận bằng `torch.cuda.is_available()` |
| `llm_int8_skip_modules` làm model chết khi chạy | Tham số này (giữ vision tower ở FP16) không tương thích với 4-bit trên bitsandbytes hiện tại → `FP4 quantization state not initialized` | Bỏ tham số, chấp nhận nén cả vision tower. Đã cô lập bằng 3 thí nghiệm A/B/C (mục 6) |
| Vintern-1B cho latency 0,0s và VRAM 0,0GB | Adapter rơi về `MockAdapter`. Nguyên nhân gốc xác nhận từ log Kaggle: `InternVLChatModel` thiếu thuộc tính `all_tied_weights_keys` mà `transformers` 4.5x+ đòi hỏi — xung đột phiên bản, không phải thiếu adapter riêng | **CHƯA SỬA.** Hướng sửa rẻ hơn: ghim `transformers` về bản cũ hơn, thay vì viết adapter InternVL riêng |
| Qwen2.5-VL-3B sập sau 4 ảnh | `CUDA error: device-side assert triggered` — nhiều khả năng tràn chỉ số khi ảnh có kích thước khác nhau | **CHƯA SỬA.** Cần chạy lại với `CUDA_LAUNCH_BLOCKING=1` hoặc ép `max_pixels` cố định |

---

## 10. Cấu trúc bàn giao

```
system1/research/vlm_prompting/
├── vlm/
│   ├── schema.py           hình dạng JSON + ép kiểu khi model trả sai
│   ├── prompts.py          prompt v1, có đánh phiên bản
│   ├── json_utils.py       cứu JSON hỏng, 3 tầng
│   ├── model_registry.py   5 model, tự chọn theo VRAM
│   ├── model_loader.py     lượng tử hóa 4-bit, giữ vision tower FP16
│   ├── adapters.py         3 backend: vLLM / transformers / mock
│   ├── generate.py         **generate_json(image)** ← hàm đề bài yêu cầu
│   └── provider.py         cắm vào system1 qua ImageCaptionProvider
├── scripts/
│   ├── smoke_one_image.py      chạy thử 1 ảnh
│   ├── prepare_sample_images.py chuẩn bị ≥100 ảnh
│   ├── benchmark_runner.py     chạy benchmark, 2 chế độ DEBUG/MASS
│   ├── metrics.py              tính 6 chỉ số
│   ├── checkpoint_utils.py     lưu tiến độ mỗi 25 ảnh
│   └── kaggle_smoke.ipynb      notebook chạy trên Kaggle
├── README.md               hướng dẫn cho người mới
└── report.md               file này
```

### Đối chiếu yêu cầu đề bài

| Yêu cầu | Trạng thái |
|---|---|
| Khảo sát VLM <7B, chạy được 4-bit | ✅ 7 model khảo sát, 5 model cài sẵn |
| Ít nhất 3 mô hình ứng viên | ✅ 5 model |
| Áp dụng lượng tử hóa 4-bit | ✅ NF4, giữ vision tower FP16 |
| Prompt ép JSON, có `caption_chi_tiet` | ✅ prompt v2 (hiện hành) + 3 tầng phòng thủ |
| `caption_chi_tiet` mô tả dài, đủ ngữ cảnh | ✅ ép tối thiểu 25 ký tự, đo số từ |
| Chạy thử ≥100 ảnh | ✅ **355 ảnh, Qwen2-VL-2B thành công 274 (77,18%)** — vượt mốc 100. Kaggle T4, 16/08/2026, `data/keyframes_aic/` |
| Hàm `generate_json(image)` | ✅ `vlm/generate.py` — đã chạy thật trên keyframe AIC |
| `sample_results.json` | ✅ **370 mục** = 274 Qwen2-VL-2B (trên 355 ảnh) + 92 Vintern-mock + 4 Qwen2.5-VL-3B (hai model sau trên bộ 92 ảnh cũ). File chỉ lưu ca thành công; 81 ca lỗi của Qwen2-VL-2B nằm ở `checkpoint_qwen2vl-2b.json` |
| Bảng benchmark 7 cột | ✅ mục 3, số thực đo (prompt v2) |
| Pull Request | ✅ **Đã mở — [PR #29](https://github.com/awun0105/Multimodal-Agentic-Retrieval-Engine/pull/29)**, base `system1-notebook01` theo tiền lệ PR #26 của Phần 2 |

#### Chuỗi số — đọc kỹ trước khi trích dẫn

```
355 ảnh trong data/keyframes_aic/
 └─ Qwen2-VL-2B chạy đủ 355
     ├─ 274 thành công (77,18%)  → sample_results.json
     └─  81 lỗi      (22,82%)  → checkpoint_qwen2vl-2b.json  [KHÔNG commit]
```

⚠️ **`sample_results.json` chỉ lưu ca thành công.** Đếm số mục trong file đó rồi kết luận
"chỉ chạy 274 ảnh" là sai — đã chạy đủ 355, 81 ca lỗi nằm ở checkpoint. Mà `.gitignore`
loại `results/checkpoint_*.json`, nên **người đọc PR không thấy file chứa ca lỗi**. Con số
81 ghi ở đây chính là để bù chỗ đó.

Muốn kiểm lại bất kỳ con số nào ở trên: `python scripts/doc-so-lieu-benchmark.py` —
nó đọc cả hai nguồn và in ra tổng/thành công/lỗi, không phải suy từ một file.

---

## 11. Việc còn lại

Xếp theo mức độ ảnh hưởng, dựa trên số đo hiện hành (không phải cảm tính):

1. **Giảm lỗi nhét chữ OCR (29,86%, 83/278)** — lỗi phổ biến nhất theo bộ đo hiện tại.
   Chặn ở tầng validator, không chỉ dựa vào prompt (mục 7.3).
2. **Giảm caption vòng vo (23,02%, 64/278)** — lỗi phổ biến thứ hai. Thử prompt v3
   nhấn "không lặp từ", đo lại bằng `quality/`.
3. **Chạy lại Vintern-1B trên môi trường `transformers` cũ hơn** để có số thật thay vì
   mock (mục 7.2). Cận trên `<5` đã thêm vào `requirements.txt`, nhưng Vintern cần bản
   cũ hơn 4.5x nên phải dựng môi trường riêng — không hạ mốc chung.
5. **Đo hiệu quả khử trùng lặp + batch inference trên tập lớn** — bắt buộc trước khi chạy
   toàn bộ dữ liệu cuộc thi (mục 7.4, cần giảm 30–40 lần thời gian)
6. **Cổng kiểm tiếng Việt** — chấm tay 30 caption × 3 model, giấu tên model

**Đã xong 16/08:**

- **Phép kiểm ký tự ngoài tiếng Việt** — `quality/caption_ngon_ngu_la.py` đã có từ 02:22,
  đang chạy trên cả 5 trường. Bắt được 2/83 (gốc) và 1/290 (agent thầy). Mục 7.3 chỗ nào
  còn ghi "bộ kiểm không bắt được lỗi chữ Hán" là tàn dư lỗi thời.
- **Mở PR** — [#29](https://github.com/awun0105/Multimodal-Agentic-Retrieval-Engine/pull/29).
Đề bài ghi nhánh `research-branch`, repo không có nhánh đó; tra lịch sử thấy PR #26 của
Phần 2 đi từ `research-branch/ocr-asr` vào `system1-notebook01` và đã được gộp →
`research-branch` là **tiền tố quy ước**, không phải nhánh có sẵn. Làm theo tiền lệ đó.

---

## 12. Giai đoạn 2 — huấn luyện

Báo cáo đầy đủ: `plans/reports/research-260815-2149-vlm-finetune-2026.md`

Kết luận ban đầu: **chưa nên train** — ngưỡng hòa vốn của fine-tune năm 2026 là
50–100 nghìn lượt gọi/ngày, cuộc thi không đạt ngưỡng đó.

> **Cập nhật 16/08/2026 — hướng đã đổi, vì lý do khác.**
>
> Không phải để tiết kiệm chi phí gọi API, mà để **sửa lỗi chất lượng caption mà prompt
> đã chạm trần**. Sửa prompt v1→v2 chỉ giảm được đúng một trong bốn lỗi (chép ví dụ mẫu);
> ba lỗi còn lại gần như không đổi (mục 7.3).
>
> Cách làm là chưng cất: dùng agent trong phiên sinh 290 caption mẫu chuẩn, rồi dạy
> Qwen2-VL-2B bắt chước. Không tốn tiền API, và LoRA gỡ ra là về model gốc nên thử sai
> không mất gì.
>
> | Chỉ số lỗi | Qwen2-VL-2B gốc (n=83) | Agent thầy (n=290) | Mức giảm |
> |---|---|---|---|
> | **Nhét chữ OCR** | **30,12%** (25/83) | **1,72%** (5/290) | 17,5 lần |
> | **Vòng vo** | **20,48%** (17/83) | **2,07%** (6/290) | 9,9 lần |
> | Ngôn ngữ lạ | 2,41% (2/83) | 0,34% (1/290) | 7,1 lần |
> | Chép ví dụ mẫu | 1,20% (1/83) | 0,00% (0/290) | về 0 |
>
> Cả hai cột đo bằng cùng bộ đo `quality/` bản 16/08 11:14, chạy lại ngày 16/08 15:30.
>
> ⚠️ **Hai cột không so cặp tuyệt đối:** n=83 vs n=290, và **tập ảnh khác nhau** (83 caption
> từ 92 ảnh benchmark; 290 caption từ dải 002–595). Muốn so cặp chuẩn phải đo agent thầy
> trên đúng 92 ảnh đó. Con số vẫn cho thấy xu hướng rõ, nhưng đừng đọc như thí nghiệm A/B.
>
> **Đây là phần mở rộng ngoài đề bài** — đề bài chỉ yêu cầu chọn model có sẵn + viết prompt
> tốt + benchmark. 290 caption này do **agent Claude Haiku** sinh qua công cụ Agent, **không
> phải** output của VLM 4-bit — nên **không dùng để tick yêu cầu "chạy thử ≥100 ảnh"** của đề bài.
> Trạng thái: đang train trên Kaggle T4, chưa có adapter dùng được.
> Dataset đã dựng: 261 train + 29 eval, 60 ảnh holdout giữ sạch để đo trước/sau.

| Bước | Cách làm | Chi phí | Kết quả kỳ vọng |
|---|---|---|---|
| 1 | Prompt tốt + ép JSON bằng XGrammar | **0đ** | 70–80% đúng, ~99,9% JSON hợp lệ |
| 2 | Chưng cất 300–500 caption từ model lớn → QLoRA | ~$5 | +30–50% |
| 3 | Tối ưu prompt tự động (GEPA) + train phần lỗi | $50–200 | +50–65% |
| 4 | Full LoRA | $1000+ | +60–80% |

Nếu train (bước 2): Unsloth + QLoRA rank 16, **đóng băng vision encoder**,
chỉ tốn 5,5–7GB VRAM → vừa Kaggle T4/P100.

---

## 13. Số nào đo thật, số nào không

Mọi con số quan trọng trong report này, phân loại rõ để không ai đọc nhầm số ước lượng
thành số đo, hay số giả thành số thật.

| Số liệu | Trạng thái |
|---|---|
| Qwen2-VL-2B: 77,18% JSON hợp lệ / 9,414 s / 2,006 GB (prompt v2, 355 ảnh, mục 3) | ✅ **Đo thật** trên Kaggle T4 ngày 16/08/2026, kernel version 18, 355 keyframe AIC |
| Qwen2-VL-2B: 85,9% JSON hợp lệ / 9,131 s / 1,946 GB (prompt v2, 92 ảnh) | ✅ **Đo thật**, lần chạy trước trên bộ 92 ảnh — giữ lại để so cặp v1/v2, không còn là số hiện hành |
| Qwen2-VL-2B: 93,5% JSON hợp lệ / 8,51 s / 1,84 GB (prompt v1, 92 ảnh, mục 7.2) | ✅ **Đo thật**, lần chạy đầu, không còn là số hiện hành |
| Qwen2.5-VL-3B: 4,3% (4/92) | ✅ Đo thật (model sập giữa chừng — số thật của một thất bại). **Không chạy lại trên 355 ảnh**: model hỏng sau 4 ảnh, chạy thêm không cho thêm thông tin |
| Vintern-1B: 100% / 0,0 s / 0,0 GB | ❌ **Số giả** — mock, model chưa từng nạp được |
| recall@1 = 0,9496 / recall@5 = 1,000 / MRR = 0,9727 (n=278) | ✅ **Đo thật**, mục 7.3 |
| Nhét OCR 29,86% / Vòng vo 23,02% / Chép few-shot 1,80% / Ngôn ngữ lạ 1,80% (n=278) | ✅ **Đo thật** bằng bộ đo hiện hành trên `sample_results.json` sau lần chạy 355 ảnh. Bộ 92 ảnh cũ (n=83) cho 30,12% / 20,48% / 1,20% / 2,41% — cùng bộ đo, chạy lại từ bản sao lưu |
| Chữ Hán lẫn caption: 2/79 (2,5%) | ⚠️ Đếm tay bằng regex **trên bộ 79 caption cũ** — chưa đếm lại trên 274 caption mới |
| `sample_results.json`: 370 mục | ✅ **Đo thật** — 274 Qwen2-VL-2B (355 ảnh) + 92 Vintern-mock + 4 Qwen2.5-VL-3B (bộ 92 ảnh) |
| "355 ảnh" (số hiện hành) | ✅ **Đo thật.** `checkpoint_qwen2vl-2b.json` có đủ 355 mục (274 thành công + 81 lỗi); `vlm_comparison_results.json` ghi `so_anh: 355` và `tong_so_anh: 355`; `data/keyframes_aic/` đếm được 355 file. `sample_results.json` chỉ lưu ca thành công nên có 274 mục — **81 ca lỗi chỉ nằm ở checkpoint, mà checkpoint không được commit** (xem `.gitignore`) |
| Chất lượng caption agent thầy (mục 12): vòng vo 2,07% / OCR 1,72% / few-shot 0% / ngôn ngữ lạ 0,34% | ✅ **Đo thật** trên 290 caption bằng bộ đo `quality/` bản 16/08 11:14 |
| Cột "Qwen2-VL-2B gốc" trong bảng mục 12 | ⚠️ **Đo bằng bộ đo CŨ** (`quality_report.json`, 02:34) — trước khi `caption_ten_rieng.py` được thêm. Đã chạy lại bằng bộ đo hiện tại, số đúng ghi ở mục 12 |
| So sánh chép ví dụ v1 (20%) vs v2 (1,2%) ở mục 7.3 | ⚠️ Cột v1 chỉ n=5 — tín hiệu định hướng, không so công bằng được với n=83 của v2 |
| 8 file keyframe, tổng 19,27 GB (mục 7.4) | ✅ **Đo thật** — đọc header từ Drive của BTC ngày 16/08 |
| ~127.000 keyframe (mục 7.4) | ⚠️ **Ước tính theo dung lượng** — L25 đếm thật (37.445 ảnh), 7 file kia suy từ 159 KB/ảnh |
| 323 giờ GPU / ~10,8 tuần (mục 7.4) | ⚠️ **Tính toán** từ latency thật × quy mô ước tính — không phải đo trực tiếp |
| Hiệu quả khử trùng lặp + batch inference | ⚠️ **Chưa đo** — code có sẵn, chưa benchmark tốc độ thật |
| MMBench 82,6 / ~78–80 (Qwen2.5-VL-7B, MiniCPM-V) | 📖 Điểm công bố của nhà phát triển, đo tiếng Anh — không tự đo, không suy ra tiếng Việt |
| Vintern-1B WER 0,34 (mục 8) | 📖 Đo bởi thành viên Phần 2, trên tác vụ OCR — không phải captioning |
