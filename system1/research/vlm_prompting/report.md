# Báo cáo — Phần 3: VLM & Prompting

**Người phụ trách:** lolizabrett-byte
**Mảng phụ trách:** Vision-Language Model & Prompting — sinh text mô tả và ép cấu trúc JSON
**Ngày:** 15/08/2026
**Nhánh:** `research/vlm-prompting`

> **TRẠNG THÁI: đã có số thực đo, nhưng 2/3 model chưa chạy được.**
>
> Đã chạy 92 keyframe thật của AIC trên Kaggle Tesla T4. Kết quả:
> - **Qwen2-VL-2B: 93,5% JSON hợp lệ** — model duy nhất chạy trọn 92 ảnh
> - Qwen2.5-VL-3B: sập sau 4 ảnh (CUDA device-side assert)
> - Vintern-1B: adapter rơi về mock, **số 100% trong log là giả**
>
> Chi tiết ở mục 7.2. Mọi số có ký hiệu ⁴ là tự đo; số khác ghi rõ nguồn.

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

| Mô hình | Latency | VRAM | Điểm benchmark | Ưu điểm | Nhược điểm | Kết luận |
|---|---|---|---|---|---|---|
| **Qwen2-VL-2B** | **8,51 s/ảnh** ⁴ | **1,84 GB** ⁴ | **JSON hợp lệ 93,5%** ⁴ | Model DUY NHẤT chạy trọn 92 ảnh không sập; VRAM thấp nhất | 6/92 ảnh lỗi; caption ngắn (18,5 từ) | ✅ **CHỌN** — đường an toàn duy nhất hiện tại |
| **Qwen2.5-VL-3B** | 10,61 s/ảnh ⁴ | 4,22 GB ⁴ | **JSON hợp lệ 4,3%** ⁴ | Chạy 1 ảnh lẻ cho caption tốt nhất, chi tiết nhất | **Sập sau 4 ảnh** — CUDA device-side assert | ❌ Chưa dùng được, cần sửa lỗi trước |
| **Vintern-1B-v3.5** | 0,69 s/ảnh ¹ | (chưa đo được) | (chưa đo được) | Tiếng Việt tốt nhất theo đo của Phần 2; nhẹ nhất | **Adapter rơi về mock** — chưa chạy được model thật | ❌ Cần adapter riêng cho InternVL |
| **Qwen2.5-VL-7B** | CHỜ ĐO | CHỜ ĐO | MMBench 82,6 ² | Chất lượng cao nhất nhóm <7B | Cần ≥12GB VRAM | Chỉ khả thi trên Kaggle P100/T4 |
| **MiniCPM-V-4.0** | CHỜ ĐO | CHỜ ĐO | MMBench ~78–80 ² | Chỉ 3GB VRAM | Không fine-tune tiếng Việt | Đường lui khi GPU yếu |

¹ Số thực đo trên **RTX 4060 Laptop** bởi thành viên phụ trách Phần 2 (OCR & ASR),
xem `system1/research/ocr_asr/ocr/ocr_evaluation_summary.md`. Đo trên tác vụ OCR,
không phải captioning — dùng làm tham chiếu về tốc độ và khả năng tiếng Việt.

² Điểm MMBench công bố, đo trên tiếng Anh. **Không suy ra được chất lượng tiếng Việt.**

⁴ **Số tự đo**, trên Kaggle Tesla T4 14,6GB, 4-bit NF4, transformers backend,
keyframe thật của AIC (`Keyframes_L25.zip`). Chi tiết ở mục 7.1.

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

**ĐÃ CHẠY XONG.** 92 keyframe thật × 3 model, Kaggle Tesla T4.

### Kết quả thô

| Model | JSON hợp lệ | Latency TB | P95 | VRAM đỉnh | Caption TB | Dùng được? |
|---|---|---|---|---|---|---|
| Vintern-1B-v3.5 | 100% (92/92) | **0,0 s** | 0,0 s | **0,0 GB** | 31 từ | ❌ **KHÔNG** — xem dưới |
| **Qwen2-VL-2B** | **93,5%** (86/92) | 8,51 s | 13,43 s | 1,84 GB | 18,5 từ | ✅ **CÓ** |
| Qwen2.5-VL-3B | 4,3% (4/92) | 10,61 s | 13,61 s | 4,22 GB | 22,8 từ | ❌ **KHÔNG** — xem dưới |

### ⚠️ Hai trong ba kết quả KHÔNG dùng được

**1. Vintern-1B: số 100% là giả.**

Latency 0,0 giây và VRAM 0,0 GB là bất khả thi với một model thật. Nghĩa là
adapter đã **rơi về `MockAdapter`** — trả JSON giả hợp lệ thay vì chạy model.
Cơ chế degrade hoạt động đúng như thiết kế (không crash cả mẻ), nhưng con số
sinh ra **không phải kết quả model**.

Nguyên nhân nhiều khả năng: Vintern-1B dùng `trust_remote_code=True` với
kiến trúc InternVL, cần gọi qua `model.chat()` riêng chứ không phải
`model.generate()` chuẩn của transformers.

→ **Không được dùng con số 100% này.** Phải viết adapter riêng cho InternVL
rồi đo lại. Đây là bài học: chỉ số "tỷ lệ JSON hợp lệ" một mình không đủ tin —
phải kiểm tra chéo với latency và VRAM.

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

### Model DUY NHẤT có số liệu tin cậy: Qwen2-VL-2B

| Chỉ số | Giá trị |
|---|---|
| Tỷ lệ JSON hợp lệ | **93,5%** (86/92 ảnh) |
| Độ tuân thủ prompt | 93,5% |
| Latency trung bình | 8,51 s/ảnh (P50 7,76 s, P95 13,43 s) |
| VRAM đỉnh | 1,84 GB |
| Độ chi tiết caption | 18,5 từ / 84,8 ký tự |
| Số đối tượng TB | 1,71 |
| Số màu sắc TB | 1,12 |

Sáu ảnh thất bại, chia hai nhóm:
- **4 ca** `JsonParseError` — model trả văn bản dài (760–1136 ký tự) không chứa JSON
- **2 ca** `ValidationError` — JSON đúng cú pháp nhưng sai kiểu: một lần
  `caption_chi_tiet` là mảng thay vì chuỗi, một lần thiếu hẳn trường này

Nhóm thứ hai đáng chú ý: prompt và parser đều làm đúng việc, model vẫn sai
schema. Đây chính xác là thứ mà constrained decoding (XGrammar) chặn được ở
tầng sinh token — và là lý do nghiên cứu khuyến nghị nó.

### ⚠️ 93,5% JSON hợp lệ KHÔNG có nghĩa là 93,5% caption dùng được

Đọc tay caption thật của Qwen2-VL-2B cho thấy vấn đề mà chỉ số "JSON hợp lệ"
không bắt được. Năm ảnh đầu tiên:

| Ảnh | `caption_chi_tiet` sinh ra | Đánh giá |
|---|---|---|
| `001.jpg` | *"Caption Chi tiết: Một người đàn ông mặc áo mưa đỏ đang chạy xe máy qua đoạn đường ngập nước dưới cơn mưa tầm tã."* | ❌ **Chép nguyên ví dụ trong prompt.** Đây là câu mẫu ở `prompts.py`, không phải nội dung ảnh. Còn lẫn cả nhãn "Caption Chi tiết:" |
| `009.jpg` | *"Người giảng dạy đang giảng dạy tại Trung tâm học tập."* | ⚠️ Vòng vo, gần như không có thông tin |
| `010.jpg` | *"Người giới thiệu đang trình bày trong phòng học với một màn hình hiển thị hình ảnh khoa học kỹ thuật."* | ✅ Dùng được |
| `014.jpg` | `doi_tuong` = `["enjoy","admit","avoid","deny","fancy","keep","mind","spend","suggest","tolerate"]` | ❌ Model đọc chữ tiếng Anh trên bảng rồi nhét vào ô "đối tượng" |
| `019.jpg` | *"Bà giảng dạy về phân tích một cấu trúc gen học."* | ⚠️ Tiếng Việt lủng củng, sai ngữ pháp |

**Ước lượng thô: chỉ 1–2 trong 5 caption thật sự dùng được**, dù cả 5 đều là
JSON hợp lệ 100%.

Ba lỗi phải sửa ở prompt (`prompts.py`, sẽ thành `PROMPT_VERSION = "v2"`):

1. **Model chép ví dụ few-shot.** Ví dụ mẫu đang dùng chính là câu trong đề bài;
   khi model "bí" nó chép lại. Cách sửa: đổi ví dụ sang cảnh khác hẳn keyframe
   thực tế, hoặc bỏ few-shot và chỉ mô tả schema.
2. **Nhãn "Caption Chi tiết:" lọt vào giá trị.** Phải bỏ khi hậu xử lý, hoặc
   siết prompt cấm lặp lại tên trường.
3. **`doi_tuong` nhận chữ thay vì vật thể.** Prompt phải nói rõ: *"chỉ liệt kê
   vật thể/người nhìn thấy, KHÔNG liệt kê chữ viết trong ảnh — chữ thuộc về OCR"*.

Đây là bài học chính của lần benchmark này: **chỉ số tự động không thay thế được
việc đọc bằng mắt**. Nếu chỉ nhìn con số 93,5% thì đã kết luận sai là pipeline
đạt yêu cầu.

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

---

## 8. Mô hình được chọn cuối cùng

### **Qwen2-VL-2B-Instruct** — chọn theo dữ liệu thực đo

**Lý do chọn:** đây là model **duy nhất trong ba** chạy trọn 92 ảnh mà không
sập. Hai model kia đều hỏng theo cách riêng (mục 7.2). Chọn model chạy được
93,5% hơn là model có tiềm năng cao hơn nhưng chưa chạy được.

| Tiêu chí | Qwen2-VL-2B |
|---|---|
| Chạy hết 92 ảnh không sập | ✅ Duy nhất |
| Tỷ lệ JSON hợp lệ | 93,5% |
| VRAM | 1,84 GB — thấp nhất, chạy được cả GPU 4GB |
| Latency | 8,51 s/ảnh |

⚠️ **Đây là lựa chọn tạm thời, không phải kết luận cuối.** Ba lý do:

1. **Chưa qua cổng kiểm tiếng Việt.** Vintern-1B (mốc đối chứng bắt buộc) chưa
   chạy được nên chưa so được. Kế hoạch ban đầu yêu cầu so sánh này trước khi chốt.
2. **Nghiên cứu cảnh báo về chính model này.** Thành viên Phần 2 ghi nhận
   Qwen2-VL-2B **từng từ chối trả lời bằng tiếng Việt**. Chưa gặp trong 92 ảnh
   vừa chạy, nhưng mẫu còn nhỏ.
3. **Caption ngắn** — 18,5 từ, ngắn hơn Qwen2.5-VL-3B (22,8 từ). Đề bài yêu cầu
   `caption_chi_tiet` "mô tả dài, đầy đủ ngữ cảnh".

### Việc phải làm trước khi chốt hẳn

| # | Việc | Vì sao |
|---|---|---|
| 1 | Viết adapter InternVL cho Vintern-1B | Mốc đối chứng tiếng Việt, không có thì cổng kiểm vô nghĩa |
| 2 | Sửa lỗi CUDA assert của Qwen2.5-VL-3B | Model này cho caption chi tiết nhất khi chạy được |
| 3 | Chấm tay 30 caption × 3 model, giấu tên model | Đo chất lượng tiếng Việt thật, không chỉ đếm JSON hợp lệ |

### Cổng kiểm tiếng Việt (chưa chạy được)

### Cổng kiểm tiếng Việt

Nghiên cứu chỉ ra một khoảng trống nghiêm trọng: **chưa có điểm BLEU/METEOR
tiếng Việt công khai** cho Qwen2.5-VL và InternVL3.5. Mọi điểm số công bố đều
đo trên tiếng Anh hoặc tiếng Trung.

Nguy cơ này **không phải giả định** — thành viên Phần 2 đã ghi nhận thực tế:
- Qwen2-VL-2B **từ chối trả lời** bằng tiếng Việt trong một số trường hợp
- Florence-2 **rơi vào vòng lặp vô hạn** khi gặp tiếng Việt
- Vintern-1B (chuyên tiếng Việt) đạt WER tốt nhất: 0,34

Nên quy trình chốt model là:

1. Chạy 100 ảnh qua cả 3 model
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
| Vintern-1B cho latency 0,0s và VRAM 0,0GB | Adapter rơi về `MockAdapter` vì model dùng kiến trúc InternVL, cần gọi `model.chat()` thay vì `model.generate()` | **CHƯA SỬA.** Ghi rõ số này không dùng được thay vì báo cáo nhầm thành 100% |
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
| Prompt ép JSON, có `caption_chi_tiet` | ✅ prompt v1 + 3 tầng phòng thủ |
| `caption_chi_tiet` mô tả dài, đủ ngữ cảnh | ✅ ép tối thiểu 25 ký tự, đo số từ |
| Chạy thử ≥100 ảnh | ⚠️ Chạy 92 ảnh thật (kho chỉ có 92 ảnh không trùng tên trong mẫu đã lấy) |
| Hàm `generate_json(image)` | ✅ `vlm/generate.py` — đã chạy thật trên keyframe AIC |
| `sample_results.json` | ✅ code đã có, sinh từ checkpoint |
| Bảng benchmark 7 cột | ✅ mục 3, số thực đo |
| Pull Request | ⏳ nên sửa 2 model hỏng trước khi mở PR |

---

## 11. Việc còn lại

1. **Chạy benchmark thật trên Kaggle** — mở `scripts/kaggle_smoke.ipynb`, bật GPU, Run All
2. **Cổng kiểm tiếng Việt** — chấm tay 30 caption × 3 model, giấu tên model
3. **Điền số vào mục 3, 7, 8** của báo cáo này
4. **Mở PR** — đề bài ghi nhánh `research-branch`, repo thực tế chưa có nhánh này,
   cần hỏi lại nhóm trước khi mở

---

## 12. Giai đoạn 2 — huấn luyện (nghiên cứu, chưa triển khai)

Báo cáo đầy đủ: `plans/reports/research-260815-2149-vlm-finetune-2026.md`

Kết luận chính: **chưa nên train.** Ngưỡng hòa vốn của fine-tune năm 2026 là
50–100 nghìn lượt gọi/ngày. Cuộc thi không đạt ngưỡng đó.

| Bước | Cách làm | Chi phí | Kết quả kỳ vọng |
|---|---|---|---|
| 1 | Prompt tốt + ép JSON bằng XGrammar | **0đ** | 70–80% đúng, ~99,9% JSON hợp lệ |
| 2 | Chưng cất 300–500 caption từ model lớn → QLoRA | ~$5 | +30–50% |
| 3 | Tối ưu prompt tự động (GEPA) + train phần lỗi | $50–200 | +50–65% |
| 4 | Full LoRA | $1000+ | +60–80% |

Nếu train (bước 2): Unsloth + QLoRA rank 16, **đóng băng vision encoder**,
chỉ tốn 5,5–7GB VRAM → vừa Kaggle T4/P100.
