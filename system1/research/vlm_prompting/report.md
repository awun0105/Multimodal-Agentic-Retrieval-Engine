# Báo cáo — Phần 3: VLM & Prompting

**Người phụ trách:** Khoa
**Mảng phụ trách:** Vision-Language Model & Prompting — sinh text mô tả và ép cấu trúc JSON
**Ngày:** 15/08/2026 (cập nhật 16/08/2026)
**Nhánh:** `research-branch/vlm-prompting` — PR [#29](https://github.com/awun0105/Multimodal-Agentic-Retrieval-Engine/pull/29)

> **TRẠNG THÁI: đạt mốc ≥100 ảnh của đề bài. Hai model chạy trọn 355 ảnh cùng một lượt.**
>
> **Qwen2.5-VL-3B — model được chọn** (Kaggle T4, prompt v2, kernel v19, 16/08/2026):
> - **96,34% JSON hợp lệ (342/355)** · `caption_en` **100%** · vòng vo 10,53% · chép ví dụ 0%
> - Latency 11,824 s/ảnh · VRAM đỉnh 4,304 GB · caption TB 26,0 từ
>
> **Qwen2-VL-2B — đường lui cho GPU nhỏ**, cùng lượt chạy, cùng 355 ảnh:
> - 77,46% JSON hợp lệ (275/355) · `caption_en` 72,0% · vòng vo 22,91%
> - Latency 9,15 s/ảnh · VRAM đỉnh 2,005 GB
>
> **Vintern-1B: vẫn chưa sinh được caption.** Ghim `transformers <4.50` thì model **nạp được**
> (`InternVLChatModel`), nhưng hỏng ở tầng xử lý ảnh — processor của nó là tokenizer thuần.
> Mọi số 100% trong log cũ là mock.
>
> **Đổi model được chọn (16/08).** Bản trước chọn Qwen2-VL-2B vì Qwen2.5-VL-3B "sập sau 4 ảnh".
> Nguyên nhân sập hóa ra là `do_sample=True` bốc thăm trên phân phối `float16` chứa `nan`,
> không phải lỗi model. Tắt lấy mẫu → 4,3% thành 96,34%. Chi tiết mục 7.2.
>
> Chất lượng caption đo riêng từng model ở mục 7.3. Lỗi lớn nhất của cả hai vẫn là **nhét chữ
> OCR vào `doi_tuong`** (33,33% / 29,82%). Mọi số có ký hiệu ⁴ là tự đo; số khác ghi rõ nguồn.

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
| Qwen2.5-VL-7B-Instruct | **8,29B** ⁶ | ~5.5GB | Dẫn đầu MMBench nhóm <7B (82.6/100) |
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

Hai model Qwen chạy **cùng một lượt, cùng 355 ảnh, cùng cấu hình** (kernel version 19,
`do_sample=False`) — so sánh trực tiếp được. Vintern-1B giữ số của lần chạy 92 ảnh vì
model chưa từng nạp được, mọi số của nó là mock (mục 7.2).

| Mô hình | Latency | VRAM | Điểm benchmark | Ưu điểm | Nhược điểm | Kết luận |
|---|---|---|---|---|---|---|
| **Qwen2.5-VL-3B** | 11,824 s/ảnh ⁴ (P50 11,431 · P95 16,055 s) | 4,304 GB ⁴ | **JSON hợp lệ 96,34%** (342/**355**) ⁴ | Cao nhất mọi mặt: JSON hợp lệ, `caption_en` **100%**, vòng vo thấp nhất (10,53%), không chép ví dụ mẫu (0%) | Chậm hơn 2,7 s/ảnh; tốn thêm 2,3 GB; nhét chữ OCR cao nhất (33,33%) | ✅ **CHỌN** |
| **Qwen2-VL-2B** | **9,15 s/ảnh** ⁴ (P50 8,527 · P95 13,437 s) | **2,005 GB** ⁴ | JSON hợp lệ 77,46% (275/**355**) ⁴ | Nhanh nhất, nhẹ nhất — chạy được cả GPU 4GB | 80/355 ảnh lỗi; `caption_en` chỉ 72,0%; vòng vo 22,91% | 🔄 Đường lui khi GPU dưới 6GB |
| **Vintern-1B-v3.5** | *0,0 s* ❌ số giả | *0,0 GB* ❌ số giả | *100%* ❌ số giả | Tiếng Việt tốt nhất theo đo của Phần 2; nhẹ nhất | **Chưa từng sinh được caption** — nạp được sau khi ghim `transformers <4.50`, nhưng hỏng ở tầng xử lý ảnh (mục 7.2) | ❌ Chưa dùng được |

> **Đổi model được chọn (16/08, kernel v19).** Bản trước chọn Qwen2-VL-2B với lý do
> "model DUY NHẤT cho caption thật". Lý do đó **không còn đúng**: Qwen2.5-VL-3B sập là do
> `do_sample=True` bốc thăm trên phân phối `float16` có `nan`, không phải lỗi model
> (mục 7.2). Tắt lấy mẫu xong nó chạy 342/355 và thắng ở 6/10 chỉ số.
>
> Cái giá phải trả — chậm hơn 2,7 s/ảnh, tốn thêm 2,3 GB — nằm trong khả năng: 4,3 GB
> chỉ chiếm 30% của T4 14,56 GB.
| **Qwen2.5-VL-7B** | CHỜ ĐO | CHỜ ĐO | MMBench 82,6 ² | Chất lượng cao nhất nhóm <7B | Cần ≥12GB VRAM | Chỉ khả thi trên Kaggle P100/T4 |
| **MiniCPM-V-4.0** | CHỜ ĐO | CHỜ ĐO | MMBench ~78–80 ² | Chỉ 3GB VRAM | Không fine-tune tiếng Việt | Đường lui khi GPU yếu |

### Cập nhật 17/08 — Vintern chạy được thật, bảng lên 4 model ⁵

Số dưới đây đo cùng ngày, cùng T4, cùng 355 ảnh, prompt v3 (thêm luật cấm tên riêng).
Chi tiết: `plans/reports/benchmark-260817-0615-4-model-va-13-ca-loi.md`.

| Mô hình | Latency | VRAM | JSON hợp lệ | Nhét chữ OCR | Vòng vo | recall@1 | Chép mẫu |
|---|---|---|---|---|---|---|---|
| **Qwen2.5-VL-7B** ⁶ | 12,411 s (P50 12,271 · P95 15,253) | 6,798 GB | **99,72%** (354/355) | **8,47%** | **6,50%** | 0,9520 | 0,00% |
| **Vintern-3B-R-beta** | 10,636 s (P50 10,326 · P95 15,136) | 2,841 GB | 97,46% (346/355) | 22,25% | 37,28% | **0,9769** | 0,00% |
| **Qwen2.5-VL-3B** | 12,118 s (P50 11,768 · P95 15,607) | 3,960 GB | 96,34% (342/355) | 34,80% | 9,65% | 0,9737 | 0,00% |
| **Qwen2-VL-2B** | **9,126 s** (P50 8,884 · P95 12,467) | **2,052 GB** | 78,31% (278/355) | 26,26% | 16,91% | 0,8597 | 5,04% |
| **Vintern-1B-v3.5** | — | — | **0%** (0/355) | — | — | — | — |

**Qwen2.5-VL-7B thắng gần như toàn diện**: JSON hợp lệ 99,72% (chỉ 1 ảnh lỗi trên 355),
nhét chữ thấp nhất, vòng vo thấp nhất. Giá phải trả là 6,798 GB — gấp 1,7 lần bản 3B, và
model có 8,29B tham số nên **vượt mốc "<7B" của đề bài**. recall@1 0,9520 thấp hơn 3B một
chút, đủ nhỏ để không đảo kết luận.

**Vintern-3B là phát hiện đáng chú ý nhất.** Lần đầu một model Vintern sinh caption thật —
mọi số Vintern trong bản trước đều là mock. Nhẹ nhất trong nhóm chạy được (2,841 GB),
recall@1 cao nhất bảng. Điểm yếu nặng: **vòng vo 37,28%**, gấp gần 6 lần Qwen-7B.

**Chép tên riêng giảm theo kích thước model** — đây là kết quả có ích nhất cho hướng đi tiếp:

| Model | Ca chép tên riêng |
|---|---|
| Qwen2.5-VL-3B | 113/342 (33,04%) |
| Vintern-3B | 59/346 (17,05%) |
| **Qwen2.5-VL-7B** | **25/354 (7,06%)** |

Thêm luật cấm vào prompt đổi được 111 → 113 ca (không đổi). Đổi sang model lớn hơn giảm
**4,7 lần**. Kết luận: đây là giới hạn năng lực model, không phải chuyện diễn đạt prompt.

**Chưa đổi model được chọn.** Qwen-7B tốt hơn về chất lượng nhưng vượt mốc tham số đề bài;
Vintern-3B nhẹ và tiếng Việt tốt nhưng vòng vo cao. Cần đọc caption thật bằng mắt trước khi
quyết, không quyết bằng bảng số.

**Vintern-1B 0% — không phải model hỏng.** Nó sinh JSON đúng cú pháp nhưng tự đặt tên trường
tiếng Việt (`"vật thể"`, `"câu tiếng Việt mô tả"`) thay vì khoá quy định. Model 1B không đủ
sức bám khuôn. Có 226/355 ca lưu được `raw_text` làm bằng chứng.

⁵ Đo 17/08/2026, kernel `notebookdd8236fd34` v5 + `notebook4764945a8d` v20, commit `328a8a7`
(xác nhận bằng dòng `Commit:` trong log kernel).

⁶ **Tên model gây hiểu nhầm.** Đếm từ HuggingFace API 17/08: Qwen2.5-VL-7B-Instruct có
**8.292.166.656** tham số, tức **vượt mốc "<7B"** của đề bài dù tên ghi 7B. Các model khác:
Qwen2.5-VL-3B 3,75B · MiniCPM-V-4 4,06B · Vintern-3B-R-beta 3,71B. Bản trước ghi "7B" theo
tên model, không phải theo số đếm.

### Bản 7B sửa được cả 13 ca lỗi của bản 3B

13 ảnh làm bản 3B sinh ra 320 dấu chấm than **đều chạy sạch trên bản 7B**. Ca lỗi duy nhất
của 7B là `362.jpg` — không nằm trong 13 ca đó, và hỏng theo kiểu hoàn toàn khác:

```
{"doi_tuong": ["cục nguồn điện", "ống dẫn điện", "hình vẽ hóa học",
 "hình vẽ điện phân", "hình vẽ điện phân", "hình vẽ điện phân", ... (954 ký tự)
```

JSON mở đúng cấu trúc rồi model lặp một cụm tới hết trần token. **Đây mới thật sự là "bị cắt
vì quá dài"** — khác hẳn dạng sập token `!` của bản 3B. Với ca này, nâng `MAX_NEW_TOKENS`
hoặc thêm `repetition_penalty` là hướng hợp lý; với 13 ca kia thì không.

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

Prompt v2 chạy lại trên **355 ảnh** cho **77,46%** (275/355, kernel v19). Tỷ lệ thấp hơn
con số 85,9% ở bộ 92 ảnh, nhưng **không so trực tiếp được**: bộ 92 ảnh lấy rải đều, bộ 355
gồm cả những ca khó hơn. Latency (9,131 → 9,15 s) và VRAM (1,946 → 2,005 GB) gần như không
đổi, cho thấy phần chênh đến từ độ khó của ảnh chứ không phải tài nguyên.

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

> ### Kết quả âm 17/08: cấm tên riêng bằng prompt KHÔNG hiệu quả
>
> Chỉ số "nhét chữ OCR 33,33%" là **hợp của ba phép kiểm**. Tách ra trên 342 caption thật:
> 111/114 ca (97%) là model **chép tên riêng người** vào caption — *"Cô Võ Hậu đang giảng
> dạy…"* — chứ không phải nhét chữ biển hiệu. Prompt cũ có luật cấm nhét chữ nhưng chỉ áp
> cho trường `doi_tuong`, nơi chỉ chiếm 0,88%.
>
> Đã thêm luật cấm tên riêng cho mọi trường (prompt v3, +24,3% độ dài). Đo lại trên cùng
> 355 ảnh, cùng model:
>
> | Thành phần | Trước | Sau | Chênh |
> |---|---|---|---|
> | Vật thể không dấu | 3 (0,88%) | 5 (1,46%) | +2 |
> | Vật thể là chuỗi chữ | 20 (5,85%) | 12 (3,51%) | **−8** |
> | **Tên riêng** | **111 (32,46%)** | **113 (33,04%)** | **+2** |
> | **Hợp** | **114 (33,33%)** | **119 (34,80%)** | **+5** |
>
> Luật nhắm vào 97% của lỗi **gần như không ăn**. Đã loại trừ khả năng prompt không chạy:
> log kernel in `Commit: 328a8a7`, đúng commit chứa luật mới.
>
> Các chỉ số khác không tụt quá ngưỡng (JSON hợp lệ giữ 96,34%, vòng vo 10,53% → 9,65%,
> recall@1 0,9766 → 0,9737), nên **giữ prompt v3**. Nhưng **bỏ hướng sửa-bằng-prompt** cho
> tên riêng: dặn model đừng chép thì nó vẫn chép.
>
> **Cùng prompt đó, model lớn hơn lại tự sửa được** — đo cùng ngày, cùng 355 ảnh:
> Qwen-3B 33,04% → Vintern-3B 17,05% → **Qwen-7B 7,06%**. Prompt đổi được 2 ca; đổi model
> giảm 4,7 lần. Đây là **giới hạn năng lực model**, không phải chuyện diễn đạt prompt.
>
> Hai hướng còn lại, theo thứ tự ưu tiên: (1) dùng model lớn hơn nếu VRAM cho phép,
> (2) lọc ở tầng validator — đối chiếu OCR để xoá tên riêng sau khi sinh.

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

✅ **Đã ghim** (16/08): `requirements.txt` là `transformers>=4.51,<5`, `kaggle_smoke.ipynb`
bỏ `pip install -U`. Mốc này cho Qwen — Vintern cần bản cũ hơn nên phải chạy môi trường riêng.

#### Cập nhật 16/08 tối — chẩn đoán được xác nhận, và lộ ra tầng hỏng thứ hai

Chạy thử trên Kaggle T4 với `transformers 4.49` (ghim `>=4.37,<4.50`):

| Tầng | Kết quả |
|---|---|
| 1. Nạp model | ✅ **NẠP ĐƯỢC** — `InternVLChatModel`, không còn rơi về mock |
| 2. Sinh caption | ❌ Hỏng — nhưng lỗi **đổi bản chất** qua từng lần sửa |
| 3. Chất lượng | Chưa đo được |

Chẩn đoán "xung đột phiên bản `transformers`" ở trên **đúng** — đây là bằng chứng trực tiếp
đầu tiên, thay cho suy luận gián tiếp.

Tầng 2 đi qua ba trạng thái:

1. `TypeError: _batch_encode_plus() got an unexpected keyword argument 'images'`
   → `AutoProcessor` của Vintern trả **tokenizer thuần**, không xử lý được ảnh. Đường chung
   `processor(text=..., images=...)` không dùng được cho họ InternVL.
2. Viết `vlm/adapter_internvl.py` (ảnh → tensor 448×448 → `model.chat()`), nhưng lỗi cũ lặp
   nguyên xi → adapter **chưa từng được gọi**: nó chỉ cắm ở nhánh `backend="auto"`, còn
   benchmark truyền thẳng `backend="transformers"`.
3. Sửa định tuyến → lỗi đổi thành `ValidationError: KeyframeMetadata` —
   **model đã sinh ra text thật**, chỉ là chưa đúng khuôn JSON.

→ Adapter hoạt động. Việc còn lại là chỉnh prompt cho InternVL: nó không có kênh `system`
riêng, hiện đang ghép cả system + user vào một câu hỏi, nhiều khả năng làm model bỏ qua
ràng buộc định dạng. **Chưa sửa** — xem mục 11.

**2. Qwen2.5-VL-3B: sập giữa chừng.**

Chạy một ảnh lẻ thì tốt (mục 7.1: 9,65 s, caption đúng). Nhưng chạy liên tiếp
thì sập sau 4 ảnh:

```
AcceleratorError: CUDA error: device-side assert triggered
```

Lỗi lặp lại ở 88/92 ảnh còn lại.

> ⚠️ **Đính chính 16/08/2026 — chẩn đoán ban đầu SAI.** Bản đầu của mục này ghi *"dấu hiệu
> điển hình của tràn chỉ số trong kernel khi xử lý ảnh có kích thước khác nhau"* và đề xuất
> sửa bằng `max_pixels`. **Đọc log đầy đủ cho thấy lỗi nằm ở tầng khác hẳn.**
>
> Dòng thật ngay trước khi model sập (log Kaggle Version 1):
>
> ```
> /pytorch/aten/src/ATen/native/cuda/TensorCompare.cu:109: _assert_async_cuda_kernel:
> Assertion `probability tensor contains either `inf`, `nan` or element < 0` failed.
> ```
>
> Đây là assert của `torch.multinomial` — hàm **bốc thăm token từ phân phối xác suất**,
> không liên quan gì tới kích thước ảnh.
>
> **Chuỗi nhân quả:**
> 1. `vlm/adapters.py` đặt `TEMPERATURE = 0.3` → `do_sample=True`
> 2. `do_sample=True` bắt model bốc thăm ngẫu nhiên thay vì lấy token xác suất cao nhất
> 3. Model chạy `float16` (`vlm/model_loader.py:116`); phân phối của model 3B tràn số → `nan`
> 4. `torch.multinomial` gặp `nan` → assert → sập
>
> Qwen2-VL-2B không sập vì nhỏ hơn nên ít tràn hơn — **may, không phải tốt hơn**.
>
> → **`max_pixels` không liên quan.** Đừng tốn GPU cho hướng đó.
> → Cách sửa: `do_sample=False` (commit `d37bdc2`). Sinh JSON có cấu trúc thì lấy token
> xác suất cao nhất vừa ổn định vừa đúng hơn bốc thăm.
>
> **Chưa chạy lại để xác nhận** — kế hoạch ở `plans/260816-1900-dong-bo-3-model-355-anh/`.
> Nếu chạy lại vẫn sập thì chẩn đoán này cũng sai, và phải đọc log lần nữa.

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

### 7.3. Đo chất lượng caption bằng công cụ tự động — n=617

Dữ liệu: `results/sample_results.json` — **709 mục**. Thành phần: `qwen25vl-3b` 342 mục
· `qwen2vl-2b` 275 mục (cả hai thật, cùng 355 ảnh, kernel v19) · `vintern-1b` 92 mục
(toàn mock, bị bộ đo tự loại). Sau khi loại mock còn **617 caption dùng được**.

Công cụ: `quality/danh_gia_chat_luong.py`. Báo cáo máy:
`results/quality_report_2model_355.json`, và từng model ở `quality_<model>_355.json`.

**Đo riêng từng model** — đây mới là số so sánh được, đo gộp chỉ cho trung bình vô nghĩa:

| Chỉ số | **Qwen2.5-VL-3B** (n=342) | Qwen2-VL-2B (n=275) |
|---|---|---|
| recall@1 | **0,9766** | 0,9491 |
| MRR | **0,9878** | 0,9724 |
| Chép few-shot | **0,00%** | 1,82% |
| Nhét chữ OCR | 33,33% | **29,82%** |
| Vòng vo (TTR) | **10,53%** | 22,91% |
| Ngôn ngữ lạ | **2,34%** | 1,82% |

Model được chọn thắng 4/6. Hai chỗ thua đều nhỏ; riêng **nhét chữ OCR là lỗi lớn nhất
của cả hai** và model được chọn còn tệ hơn 3,5 điểm — việc cần sửa tiếp theo.

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

### **Qwen2.5-VL-3B-Instruct** — chọn theo dữ liệu thực đo

**Lý do chọn:** thắng Qwen2-VL-2B ở **6/10 chỉ số**, trên cùng 355 ảnh, cùng một lượt chạy,
cùng cấu hình. Hai chỉ số nó thua (tốc độ, VRAM) đều không phải ràng buộc thật trên T4.

| Tiêu chí | **Qwen2.5-VL-3B** | Qwen2-VL-2B | Chênh |
|---|---|---|---|
| Tỷ lệ JSON hợp lệ | **96,34%** (342/355) | 77,46% (275/355) | **+18,9 điểm** |
| `caption_en` có thật | **100%** (342/342) | 72,0% (198/275) | **+28 điểm** |
| Vòng vo (TTR) | **10,53%** | 22,91% | giảm hơn nửa |
| Chép ví dụ mẫu | **0,00%** | 1,82% | sạch hoàn toàn |
| recall@1 | **0,9766** | 0,9491 | +0,0275 |
| MRR | **0,9878** | 0,9724 | +0,0154 |
| Nhét chữ OCR | 33,33% | **29,82%** | thua 3,5 điểm |
| Latency | 11,824 s/ảnh | **9,15 s/ảnh** | chậm hơn 2,7 s |
| VRAM đỉnh | 4,304 GB | **2,005 GB** | tốn thêm 2,3 GB |
| Caption TB | **26,0 từ** | 24,3 từ | dài hơn chút |

**Vì sao chấp nhận chậm hơn và nặng hơn:** 4,3 GB chỉ chiếm 30% của T4 14,56 GB — còn thừa
chỗ. Chênh 2,7 s/ảnh trên 127.000 keyframe là ~95 giờ GPU, đáng kể, nhưng đổi lại **thêm
19 điểm JSON hợp lệ** nghĩa là ít hơn hẳn số ảnh phải chạy lại. Tính ròng vẫn lợi.

**Điểm quyết định là `caption_en` 100%.** Schema của nhóm
(`system1/schemas/shot_captions.schema.json`) bắt buộc cả `caption_vi` lẫn `caption_en`.
Qwen2-VL-2B để 28% mục ở `status="partial"`; Qwen2.5-VL-3B không mục nào.

**Đường lui:** Qwen2-VL-2B vẫn giữ trong registry, đổi bằng một tham số. Dùng khi GPU
dưới 6 GB.

⚠️ **Ba điểm còn treo:**

1. **Chưa qua cổng kiểm tiếng Việt.** Vintern-1B (mốc đối chứng bắt buộc) vẫn chưa sinh
   được caption. Kế hoạch ban đầu yêu cầu so sánh này trước khi chốt hẳn.
2. **Nhét chữ OCR là lỗi lớn nhất và model được chọn còn tệ hơn** — 33,33% so với 29,82%.
   Việc đọc chữ thuộc Phần 2; chặn ở tầng validator là việc ưu tiên tiếp theo.
3. **13 ca lỗi còn lại đều là JSON không parse được** — nguyên nhân đã tìm ra 17/08 bằng
   cách chạy lại 13 ảnh và lưu nguyên văn output: model sinh **320 dấu chấm than liên tiếp**
   (`!!!!…`), không lẫn ký tự nào khác, giống hệt nhau ở cả 13 ảnh. Không phải caption bị
   cắt — độ dài trùng `MAX_NEW_TOKENS` chỉ vì model lặp token `!` (id 0) tới hết trần.
   **Nâng trần token vô ích.** Chi tiết ở
   `plans/reports/benchmark-260817-0615-4-model-va-13-ca-loi.md`.

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
| Chạy thử ≥100 ảnh | ✅ **355 ảnh × 2 model Qwen** — Qwen2.5-VL-3B thành công 342 (96,34%), Qwen2-VL-2B 275 (77,46%). Kaggle T4, 16/08/2026, kernel v19, `data/keyframes_aic/` |
| Hàm `generate_json(image)` | ✅ `vlm/generate.py` — đã chạy thật trên keyframe AIC |
| `sample_results.json` | ✅ **709 mục** = 342 Qwen2.5-VL-3B + 275 Qwen2-VL-2B (cùng 355 ảnh) + 92 Vintern-mock (bộ 92 ảnh cũ). File chỉ lưu ca thành công; 13 + 80 ca lỗi nằm ở `checkpoint_*.json` |
| Bảng benchmark 7 cột | ✅ mục 3, số thực đo (prompt v2) |
| Pull Request | ✅ **Đã mở — [PR #29](https://github.com/awun0105/Multimodal-Agentic-Retrieval-Engine/pull/29)**, base `system1-notebook01` theo tiền lệ PR #26 của Phần 2 |

#### Chuỗi số — đọc kỹ trước khi trích dẫn

```
355 ảnh trong data/keyframes_aic/  (kernel v19, cùng một lượt chạy)
 ├─ Qwen2.5-VL-3B  ├─ 342 thành công (96,34%)  → sample_results.json
 │                 └─  13 lỗi        ( 3,66%)  → checkpoint_qwen25vl-3b.json [KHÔNG commit]
 └─ Qwen2-VL-2B    ├─ 275 thành công (77,46%)  → sample_results.json
                   └─  80 lỗi        (22,54%)  → checkpoint_qwen2vl-2b.json  [KHÔNG commit]

Vintern-1B: 92 mục mock từ bộ ảnh cũ — không phải output model thật.
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

1. **Giảm lỗi nhét chữ OCR (33,33% ở model được chọn)** — lỗi lớn nhất còn lại, và
   Qwen2.5-VL-3B còn tệ hơn Qwen2-VL-2B 3,5 điểm. Chặn ở tầng validator, không chỉ dựa
   vào prompt (mục 7.3). Việc đọc chữ vốn thuộc Phần 2.
2. **Chỉnh prompt cho Vintern-1B.** Adapter InternVL đã chạy được (`vlm/adapter_internvl.py`),
   model sinh ra text thật nhưng chưa đúng khuôn JSON. InternVL không có kênh `system` riêng —
   hiện ghép system + user vào một câu hỏi, cần tách hoặc rút gọn. Xem mục 7.2.
3. **13 ca lỗi còn lại của Qwen2.5-VL-3B** — đã kiểm 17/08, giả thuyết "caption bị cắt ở
   `MAX_NEW_TOKENS = 320`" **sai**. Nguyên văn output là 320 dấu chấm than liên tiếp, cả 13
   ảnh như một. Đây là dạng sập token của Qwen2-VL/2.5-VL, không phải caption dài. Hướng
   sửa: ép JSON lúc sinh token (XGrammar) hoặc đổi độ phân giải ảnh — không phải nâng trần.
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
> Dataset đã dựng: 261 train + 29 eval.
>
> ⚠️ **Cách ly dữ liệu — bắt buộc đọc trước khi đo model đã train.** Đếm lại trực tiếp
> trên dataset Kaggle (17/08), đối chiếu từng tên file: **290 trong 355 ảnh benchmark có
> nhãn sẵn** — 261 trong `train.jsonl`, 29 trong `eval.jsonl`. Đo model sau khi nạp LoRA
> trên đúng 355 ảnh này sẽ cho điểm đẹp giả tạo, vì model đã thấy nhãn lúc train.
>
> Tập sạch thật sự chỉ còn **65 ảnh**, liệt kê ở `data/holdout-65-anh-sach.txt`.
> Chạy bằng `--anh-list data/holdout-65-anh-sach.txt`.
>
> Con số "60 ảnh holdout" ở bản trước là ước lượng, không phải số đếm. 65 ảnh là ít cho
> một phép đo tin cậy — muốn so trước/sau LoRA cho chắc thì phải lấy thêm keyframe ngoài
> 355 ảnh này.
>
> Bảng benchmark mục 3 **không dính lỗi này**: mọi số đều đo trên model gốc chưa nạp LoRA,
> và notebook chỉ trỏ vào thư mục `images/` nên không đọc `train.jsonl` / `eval.jsonl`.

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
| **Qwen2.5-VL-3B: 96,34% JSON hợp lệ / 11,824 s / 4,304 GB** (355 ảnh, mục 3) | ✅ **Đo thật** Kaggle T4 16/08/2026, kernel v19, `do_sample=False`. Model được chọn |
| Qwen2-VL-2B: 77,46% JSON hợp lệ / 9,15 s / 2,005 GB (355 ảnh, mục 3) | ✅ **Đo thật** cùng lượt chạy v19 — cùng ảnh, cùng cấu hình, so cặp trực tiếp được |
| Qwen2-VL-2B: 77,18% / 9,414 s / 2,006 GB (355 ảnh, kernel v18) | ✅ **Đo thật**, lượt trước khi tắt lấy mẫu. Chênh 0,28 điểm — tắt lấy mẫu gần như không ảnh hưởng model 2B |
| Qwen2-VL-2B: 85,9% JSON hợp lệ / 9,131 s / 1,946 GB (prompt v2, 92 ảnh) | ✅ **Đo thật**, lần chạy trước trên bộ 92 ảnh — giữ lại để so cặp v1/v2, không còn là số hiện hành |
| Qwen2-VL-2B: 93,5% JSON hợp lệ / 8,51 s / 1,84 GB (prompt v1, 92 ảnh, mục 7.2) | ✅ **Đo thật**, lần chạy đầu, không còn là số hiện hành |
| Qwen2.5-VL-3B: 4,3% (4/92) — số CŨ | ✅ Đo thật, nhưng **đã lỗi thời**. Đo khi còn `do_sample=True`. Sau khi tắt lấy mẫu (commit `d37bdc2`), model đạt **96,34% (342/355)** — xác nhận chẩn đoán ở mục 7.2. Giữ lại để thấy mức cải thiện |
| Vintern-1B: 100% / 0,0 s / 0,0 GB | ❌ **Số giả** — mock, model chưa từng nạp được |
| recall@1 = 0,9496 / recall@5 = 1,000 / MRR = 0,9727 (n=278) | ✅ **Đo thật**, mục 7.3 |
| Nhét OCR 29,86% / Vòng vo 23,02% / Chép few-shot 1,80% / Ngôn ngữ lạ 1,80% (n=278) | ✅ **Đo thật** bằng bộ đo hiện hành trên `sample_results.json` sau lần chạy 355 ảnh. Bộ 92 ảnh cũ (n=83) cho 30,12% / 20,48% / 1,20% / 2,41% — cùng bộ đo, chạy lại từ bản sao lưu |
| Chữ Hán lẫn caption: 2/79 (2,5%) | ⚠️ Đếm tay bằng regex **trên bộ 79 caption cũ** — chưa đếm lại trên 274 caption mới |
| `sample_results.json`: 709 mục | ✅ **Đo thật** — 342 Qwen2.5-VL-3B + 275 Qwen2-VL-2B (cùng 355 ảnh, kernel v19) + 92 Vintern-mock (bộ 92 ảnh cũ) |
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
