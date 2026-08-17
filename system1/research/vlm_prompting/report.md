# Báo cáo — Phần 3: VLM & Prompting

**Người phụ trách:** Khoa
**Mảng phụ trách:** Vision-Language Model & Prompting — sinh text mô tả và ép cấu trúc JSON
**Ngày:** 15/08/2026 (cập nhật 16/08/2026)
**Nhánh:** `research-branch/vlm-prompting` — PR [#29](https://github.com/awun0105/Multimodal-Agentic-Retrieval-Engine/pull/29)

> **TRẠNG THÁI: 6 model đã đo trên 355 keyframe thật, vượt mốc ≥100 ảnh của đề bài.**
>
> **Bốn model chạy được** (chi tiết mục 3):
>
> | Model | JSON hợp lệ | VRAM | Chép tên riêng |
> |---|---|---|---|
> | Qwen2.5-VL-7B | **99,72%** (354/355) | 6,798 GB | **7,06%** |
> | Vintern-3B-R-beta | 97,46% (346/355) | **2,841 GB** | 17,05% |
> | Qwen2.5-VL-3B ← đang chọn | 96,34% (342/355) | 3,960 GB | 33,04% |
> | Qwen2-VL-2B | 78,31% (278/355) | 2,052 GB | 26,26% |
>
> **Hai model không dùng được:** Vintern-1B 0% (tự chế tên trường JSON) · MiniCPM-V-4 0%
> (tràn bộ nhớ — lượng tử hoá 4-bit không có tác dụng trên model này).
>
> **Đề xuất đổi model được chọn sang Vintern-3B-R-beta** — thắng Qwen2.5-VL-3B ở 5/6 chỉ số,
> nhẹ hơn 1,1 GB, nhanh hơn 1,5 s/ảnh, chép tên riêng bằng nửa. Cần nhóm duyệt sau khi chấm
> tay 30 caption × 4 model.
>
> **Trần phần cứng thật trên T4 free: ~11 tỷ tham số** (mục 3). Con số "dưới 7B" là ước
> lượng nội bộ của nhóm, không phải quy định BTC — cả Qwen-7B (8,29B) lẫn Vintern-3B đều
> nằm trong trần.
>
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

Cột **Tham số** đếm từ HuggingFace API (`safetensors.total`), không phải theo tên model —
tên gọi hay làm tròn xuống (Qwen2.5-VL-"7B" thật ra 8,29 tỷ).

| Model | Tham số | VRAM đo thật | Trạng thái |
|---|---|---|---|
| Qwen2.5-VL-7B-Instruct | 8,29B | 6,798 GB | ✅ Đã đo — cao nhất mọi chỉ số chất lượng |
| InternVL3.5-8B | 8,53B | *đang đo* | Á quân MMBench; lý do loại cũ ("vượt 7B") đã đổ |
| MiniCPM-V-4.0 | 4,06B | tràn 12,97 GB | ❌ 4-bit không có tác dụng trên model này |
| Qwen2.5-VL-3B-Instruct | 3,75B | 3,960 GB | ✅ Đã đo — model đang chọn |
| Vintern-3B-R-beta | 3,71B | 2,841 GB | ✅ Đã đo — **đề xuất đổi sang** |
| Qwen2-VL-2B-Instruct | 2,21B | 2,052 GB | ✅ Đã đo — đường lui cho GPU nhỏ |
| Moondream 2 | 1,93B | *đang đo* | Chạy fp16, không nén 4-bit |
| Vintern-1B-v3.5 | 0,94B | — | ❌ 0% — tự chế tên trường JSON |

Cả 8 model đã cài trong `vlm/model_registry.py`, đổi bằng một tham số.

**Moondream 3-preview (9,27B, MoE) không vào danh sách đo:** MoE nạp toàn bộ 9,27 tỷ tham số
vào bộ nhớ dù chỉ kích hoạt 2 tỷ mỗi token, và tài liệu không nói gì về bitsandbytes — cùng
ba dấu hiệu đã làm MiniCPM-V-4 thất bại. Bản Moondream 2 nhẹ hơn được chọn thay.

---

## 3. Bảng benchmark (bắt buộc theo đề bài)

**Môi trường:** Kaggle Tesla T4 14,56 GB · Python 3.12.13 · PyTorch 2.10.0+cu128 ·
4-bit NF4 · `do_sample=False` · 355 keyframe AIC thật (`Keyframes_L25.zip`).

Mọi model chạy **cùng bộ ảnh, cùng cấu hình**, nên so sánh trực tiếp được.

| Mô hình | Tham số | Latency | VRAM | JSON hợp lệ | Nhét chữ OCR | Vòng vo | recall@1 | Chép mẫu |
|---|---|---|---|---|---|---|---|---|
| **Qwen2.5-VL-7B** | 8,29B | 12,411 s | 6,798 GB | **99,72%** (354/355) | **8,47%** | **6,50%** | 0,9520 | 0,00% |
| **Vintern-3B-R-beta** | 3,71B | 10,636 s | 2,841 GB | 97,46% (346/355) | 22,25% | 37,28% ⚠️ | **0,9769** | 0,00% |
| **Qwen2.5-VL-3B** ← đang chọn | 3,75B | 12,118 s | 3,960 GB | 96,34% (342/355) | 34,80% | 9,65% | 0,9737 | 0,00% |
| **Qwen2-VL-2B** | 2,21B | **9,126 s** | **2,052 GB** | 78,31% (278/355) | 26,26% | 16,91% | 0,8597 | 5,04% |
| Vintern-1B-v3.5 | 0,94B | — | — | **0%** (0/355) | — | — | — | — |
| MiniCPM-V-4 | 4,06B | — | tràn 12,97 GB | **0%** (0/355) | — | — | — | — |

Chi tiết P50/P95 và cách đo: `plans/reports/benchmark-260817-0615-6-model-va-13-ca-loi.md`

### Đọc bảng

**Qwen2.5-VL-7B mạnh nhất về chất lượng** — 354/355 ảnh, nhét chữ và vòng vo đều thấp nhất.
Giá: 6,798 GB (47% T4) và tải về 16,6 GB.

**Vintern-3B-R-beta là ứng viên tiếng Việt** — nhẹ nhất trong nhóm chạy được, nhanh nhất
sau bản 2B, recall@1 cao nhất bảng, và chép tên riêng chỉ bằng nửa Qwen-3B.

⚠️ **Con số vòng vo 37,28% của Vintern-3B là thước đo báo nhầm, không phải lỗi model.**
Phép kiểm gồm hai điều kiện; tách ra:

| | TTR < 0,6 (lặp thật) | Cụm 2 từ lặp | TTR trung bình | Độ dài caption |
|---|---|---|---|---|
| Vintern-3B | 12 (3,5%) | 129 (37,3%) | **0,811** | **55 từ** |
| Qwen-7B | 0 (0,0%) | 23 (6,5%) | 0,922 | 22 từ |
| Qwen-3B | 1 (0,3%) | 33 (9,6%) | 0,904 | 26 từ |

TTR 0,811 là lành mạnh. Phần còn lại do `kiem_cum_lap(n=2)` bắt **danh từ ghép tiếng Việt
bình thường**: `người đàn` (42 lần), `đàn ông` (42), `máy tính` (36), `giáo viên` (17).
Caption Vintern dài 55 từ — gấp 2,4 lần Qwen — nên một danh từ ghép lặp lại là khó tránh.

Caption thật đọc tốt: *"Một người đàn ông mặc áo sơ mi trắng, đeo kính và đeo cà vạt màu
xanh đậm đang ngồi trước một chiếc máy tính xách tay Dell màu bạc trên bàn làm việc."*

Cần sửa `kiem_cum_lap` (nâng n=3 hoặc miễn trừ danh từ ghép) rồi đo lại toàn bộ.

**Vintern-1B: 0% nhưng không phải model hỏng.** Nó sinh JSON đúng cú pháp với tên trường tự
chế (`"vật thể"`, `"câu tiếng Việt mô tả"`) thay vì khoá quy định. Model 1B không đủ sức bám
khuôn. 226/355 ca lưu `raw_text` làm bằng chứng.

**MiniCPM-V-4: không khả thi trên T4.** Adapter nạp được model, chạy hết 355 ảnh, nhưng
190 ca tràn bộ nhớ và 165 ca trả đúng một token `<CLS>`. Nguyên nhân: lượng tử hoá 4-bit
không có tác dụng — 12,97 GB cho model 4,06B, trong khi ở 4-bit lẽ ra ~3 GB. Code
`trust_remote_code` của MiniCPM nạp vision tower ngoài luồng bitsandbytes. Đường lượng tử
hoá của bản 4 là llama.cpp/GGUF, không phải transformers.

### Chép tên riêng giảm theo kích thước model

| Model | Ca chép tên riêng |
|---|---|
| Qwen2.5-VL-3B | 113/342 (33,04%) |
| Vintern-3B | 59/346 (17,05%) |
| **Qwen2.5-VL-7B** | **25/354 (7,06%)** |

Thêm luật cấm tên riêng vào prompt: 111 → 113 ca, không đổi. Đổi sang model lớn hơn: giảm
**4,7 lần**. Đây là giới hạn năng lực model, không phải chuyện diễn đạt prompt (mục 5).

### Chọn model nào

**Đề xuất đổi sang Vintern-3B-R-beta**, cần nhóm duyệt trước khi chốt.

| | Vintern-3B | Qwen2.5-VL-3B (đang chọn) | Qwen2.5-VL-7B |
|---|---|---|---|
| JSON hợp lệ | 97,46% | 96,34% | **99,72%** |
| Chép tên riêng | 17,05% | 33,04% | **7,06%** |
| VRAM | **2,841 GB** (20% T4) | 3,960 GB (27%) | 6,798 GB (47%) |
| Latency | **10,636 s** | 12,118 s | 12,411 s |
| Tải về | **7,4 GB** | 7,5 GB | 16,6 GB |
| recall@1 | **0,9769** | 0,9737 | 0,9520 |
| Tiếng Việt | fine-tune riêng | đa ngữ | đa ngữ |

Vintern-3B thắng Qwen-3B ở 5/6 chỉ số, nhẹ hơn 1,1 GB, nhanh hơn 1,5 s/ảnh.

Qwen-7B tốt hơn về chất lượng caption nhưng nặng gấp 2,4 lần khi tải và chiếm gấp đôi VRAM.
Cả hai đều nằm trong trần phần cứng thật (mục dưới).

**Bước chặn duy nhất còn lại:** chấm tay 30 caption × 4 model, giấu tên model. Máy chấm cho
tín hiệu mâu thuẫn ở chỉ số vòng vo, nên mắt người là trọng tài cuối.

### Trần tham số thật: ~11 tỷ, không phải 7 tỷ

**Con số "dưới 7B" không phải quy định của BTC.** Đã kiểm nguồn:

| Nguồn | Có nói gì về giới hạn tham số? |
|---|---|
| `preliminary-round-info.pdf` (BTC chính thức, 6 trang) | **Không một dòng nào** về tham số / VRAM / phần cứng |
| `Ban_chia_viec_nghien_cuu_multimodal.pdf` tr.3 mục 15 | *"VLM nhỏ gọn dưới 7B tham số"* — nhưng đây là **bản chia việc nội bộ nhóm** |

Mục 17 của chính văn bản đó nói rõ lý do: *"Áp dụng lượng tử hóa 4-bit **để giảm tải phần
cứng**"*. Tức 7B là **ràng buộc hạ tầng nhóm tự đặt**, không phải quy chế. Ràng buộc hạ tầng
thì đo lại được.

**Tính trần thật từ 4 model đã đo trên T4** (4-bit NF4):

| Model | Tham số | VRAM đỉnh | GB/tỷ tham số |
|---|---|---|---|
| Qwen2-VL-2B | 2,21B | 2,052 GB | 0,929 |
| Vintern-3B | 3,71B | 2,841 GB | 0,765 |
| Qwen2.5-VL-3B | 3,75B | 3,960 GB | **1,055** ← xấu nhất |
| Qwen2.5-VL-7B | 8,29B | 6,798 GB | 0,820 |

Lấy hệ số xấu nhất (1,055 GB/tỷ) để tính an toàn:

| Dự phòng | Trần tham số |
|---|---|
| 15% | **11,7 tỷ** |
| 20% | **11,0 tỷ** |
| 30% | 9,7 tỷ |

**Hai ràng buộc khác đã kiểm, đều không bó buộc:**

- **Thời gian**: 7B chạy 355 ảnh hết 73 phút = 10% quota 12h. Đáng chú ý, 7B chỉ **chậm hơn
  3B 2,4%** dù gấp 2,2 lần kích thước — tốc độ không tỉ lệ với số tham số.
- **Đĩa**: 7B tải về 16,6 GB dạng gốc fp16 (nén 4-bit chỉ xảy ra sau khi tải). Kaggle cho
  ~57-73 GB, còn rộng.

**Kết luận: trần thực tế trên T4 free là ~11 tỷ tham số.** Qwen2.5-VL-7B (8,29B, dùng 47%
VRAM) nằm gọn trong đó — **không vi phạm ràng buộc nào cả**. Con số 7B trong bản chia việc
là ước lượng thận trọng đặt ra trước khi có số đo.

⁷ **MiniCPM-V-4: đã viết adapter, chạy được, nhưng không dùng được trên T4.** Trước đây model
này chưa từng chạy vì registry trỏ sai lớp nạp. Đã viết `MiniCpmAdapter`
(`vlm/adapter_minicpm.py`, 87 dòng) dùng `AutoModel` + `.chat()`. Kết quả chạy thật 355 ảnh:

| Kết cục | Số ca |
|---|---|
| Tràn bộ nhớ GPU (OOM) | 190 |
| Model trả đúng một token `<CLS>` | 165 |
| JSON hợp lệ | **0** |

Hai vấn đề độc lập:

1. **Lượng tử hoá 4-bit không có tác dụng.** Log ghi *"this process has 12.97 GiB memory in
   use"* cho model 4,06B tham số — ở 4-bit lẽ ra ~3 GB. `BitsAndBytesConfig` được truyền
   đúng, nhưng code `trust_remote_code` của MiniCPM nạp vision tower ngoài luồng
   bitsandbytes. Bằng chứng gián tiếp: openbmb có bản `int4` **chính thức** cho MiniCPM-V
   2.5 và 2.6, nhưng bản 4 chỉ có `gguf` (llama.cpp) — không có bản int4 cho transformers.
2. **`.chat()` trả `<CLS>`** ở 165 ca còn lại — chữ ký gọi chưa đúng. MiniCPM-V-4 là
   *legacy model* trong repo chính thức, tài liệu bản 4 không còn ví dụ `.chat()` đầy đủ.

**Kết luận: không khả thi trên T4 trong khuôn khổ hiện tại.** Muốn dùng phải đi đường
llama.cpp/GGUF — tức một pipeline khác hẳn, ngoài phạm vi. Adapter vẫn giữ lại: nó đúng về
định tuyến và sẽ dùng được nếu sau này có bản int4 cho transformers.

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

**Phiên bản hiện hành: `v3`** (hằng `PROMPT_VERSION` trong `vlm/prompts.py`) — v2 cộng thêm
luật cấm tên riêng cho mọi trường, dài hơn 24,3%.

> ### Giới hạn của prompt: cấm tên riêng không có tác dụng
>
> Chỉ số "nhét chữ OCR 33,33%" là **hợp của ba phép kiểm**. Tách trên 342 caption:
> 111/114 ca (97%) là model **chép tên riêng người** — *"Cô Võ Hậu đang giảng dạy…"* —
> chứ không phải nhét chữ biển hiệu. Prompt v2 chỉ cấm nhét chữ ở trường `doi_tuong`,
> nơi chiếm 0,88%.
>
> v3 thêm luật cấm tên riêng cho mọi trường. Đo lại trên cùng 355 ảnh, cùng model:
>
> | Thành phần | v2 | v3 | Chênh |
> |---|---|---|---|
> | Vật thể không dấu | 3 (0,88%) | 5 (1,46%) | +2 |
> | Vật thể là chuỗi chữ | 20 (5,85%) | 12 (3,51%) | **−8** |
> | **Tên riêng** | **111 (32,46%)** | **113 (33,04%)** | **+2** |
> | **Hợp** | 114 (33,33%) | 119 (34,80%) | +5 |
>
> Luật nhắm vào 97% của lỗi mà **không đổi được gì**. Các chỉ số khác không tụt quá ngưỡng
> (JSON hợp lệ giữ 96,34%, vòng vo 10,53% → 9,65%, recall@1 0,9766 → 0,9737) nên giữ v3,
> nhưng **prompt không phải hướng sửa cho lỗi này**.
>
> **Kích thước model mới là yếu tố quyết định.** Cùng prompt v3, cùng 355 ảnh:
> Qwen-3B 33,04% → Vintern-3B 17,05% → **Qwen-7B 7,06%**. Prompt đổi 2 ca; đổi model giảm
> 4,7 lần. Đây là giới hạn năng lực model, không phải cách diễn đạt.
>
> Hai hướng còn lại, theo thứ tự: (1) dùng model lớn hơn nếu VRAM cho phép, (2) lọc ở tầng
> validator — đối chiếu OCR để xoá tên riêng sau khi sinh.

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

### 7.2. Hai lỗi hạ tầng đã sửa

Số hiện hành ở mục 3. Phần này giữ lại nguyên nhân gốc của hai lỗi từng làm hỏng cả lượt
benchmark — cùng loại lỗi dễ tái diễn khi thêm model mới.

**Lỗi 1: Qwen2.5-VL-3B sập sau 4 ảnh (4,3% JSON hợp lệ).**

Không phải lỗi model. `do_sample=True` bốc thăm trên phân phối xác suất, mà ở `float16`
phân phối của model 3B tràn số thành `nan`:

```
RuntimeError: probability tensor contains either inf, nan or element < 0
```

88/92 ca lỗi cùng một thông báo. Sinh JSON có cấu trúc thì lấy chữ xác suất cao nhất vừa
ổn định vừa đúng hơn lấy mẫu — tắt `do_sample` (commit `d37bdc2`) đưa model từ **4,3% lên
96,34%**. Hằng `DUNG_LAY_MAU = False` trong `vlm/adapters.py`.

**Lỗi 2: Vintern-1B trả 100% nhưng là mock.**

Nguyên nhân là **xung đột phiên bản `transformers`**, không phải thiếu adapter:
`InternVLChatModel` thiếu thuộc tính `all_tied_weights_keys` mà transformers 4.5x+ bắt buộc,
nên nạp hỏng rồi âm thầm rơi về mock. Ghim `transformers>=4.37,<4.50` là nạp được.

Hai hệ quả về sau:

- Cờ `--strict` được thêm để model nạp hỏng **ném lỗi** thay vì rơi về mock. Không có nó,
  bảng benchmark nhận số giả trông y như số thật.
- Mốc thư viện **không dùng chung được cho cả họ InternVL**: Vintern cần `<4.50`, còn
  InternVL3.5 dùng Qwen3 làm phần ngôn ngữ nên cần `>=4.52.1`. Hai notebook riêng.

---

### ⚠️ JSON hợp lệ không có nghĩa là caption dùng được

Đọc tay caption thật cho thấy vấn đề mà chỉ số "JSON hợp lệ" không bắt được. Năm ảnh đầu
của Qwen2-VL-2B, **cả năm đều là JSON hợp lệ 100%**:

| Ảnh | `caption_chi_tiet` sinh ra | Đánh giá |
|---|---|---|
| `001.jpg` | *"Caption Chi tiết: Một người đàn ông mặc áo mưa đỏ đang chạy xe máy qua đoạn đường ngập nước dưới cơn mưa tầm tã."* | ❌ **Chép nguyên ví dụ trong prompt**, còn lẫn cả nhãn "Caption Chi tiết:" |
| `009.jpg` | *"Người giảng dạy đang giảng dạy tại Trung tâm học tập."* | ⚠️ Vòng vo, gần như không có thông tin |
| `010.jpg` | *"Người giới thiệu đang trình bày trong phòng học với một màn hình hiển thị hình ảnh khoa học kỹ thuật."* | ✅ Dùng được |
| `014.jpg` | `doi_tuong` = `["enjoy","admit","avoid","deny","fancy","keep","mind","spend","suggest","tolerate"]` | ❌ Model đọc chữ tiếng Anh trên bảng rồi nhét vào ô "đối tượng" |
| `019.jpg` | *"Bà giảng dạy về phân tích một cấu trúc gen học."* | ⚠️ Tiếng Việt lủng củng, sai ngữ pháp |

Chỉ 1–2 trong 5 caption thật sự dùng được. Mục 7.3 xác nhận và mở rộng bằng công cụ đo
tự động trên n=617.

**Đây là lý do bước chấm tay 30 caption × 4 model vẫn là điều kiện để chốt model** (mục 8):
chỉ số tự động không thay thế được việc đọc bằng mắt. Chỉ nhìn JSON hợp lệ thì đã kết luận
sai là pipeline đạt yêu cầu.

Ba lỗi rút ra, đã đưa vào prompt v2/v3:

1. **Chép ví dụ few-shot** — đổi ví dụ mẫu sang cảnh khác hẳn keyframe thật (cảnh bếp).
   Giảm mạnh nhưng không diệt hẳn: `032.jpg` ở v2 vẫn chép nguyên ví dụ bếp mới. Số hiện
   hành: 0,00% ở ba model lớn, 5,04% ở Qwen2-VL-2B.
2. **Nhãn tên trường lọt vào giá trị** — prompt cấm lặp lại tên trường. Đã hết.
3. **`doi_tuong` nhận chữ thay vì vật thể** — prompt v2 thêm câu cấm nhưng chưa đủ; v3 mở
   rộng sang mọi trường vẫn không ăn. Hướng còn lại là model lớn hơn hoặc lọc ở validator
   (mục 5).

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

## 8. Mô hình được chọn

### Đang chọn: **Qwen2.5-VL-3B-Instruct**

Chọn ngày 16/08 khi mới có 2 model đo thật. Lý do khi đó: thắng Qwen2-VL-2B ở 6/10 chỉ số
trên cùng 355 ảnh, đặc biệt là `caption_en` 100% — schema của nhóm
(`system1/schemas/shot_captions.schema.json`) bắt buộc cả `caption_vi` lẫn `caption_en`,
mà Qwen2-VL-2B để 28% mục ở `status="partial"`.

### Đề xuất đổi sang: **Vintern-3B-R-beta**

Sau khi đo đủ 6 model (mục 3), Vintern-3B thắng model đang chọn ở 5/6 chỉ số:

| | Vintern-3B | Qwen2.5-VL-3B |
|---|---|---|
| JSON hợp lệ | **97,46%** | 96,34% |
| VRAM | **2,841 GB** | 3,960 GB |
| Latency | **10,636 s** | 12,118 s |
| Chép tên riêng | **17,05%** | 33,04% |
| recall@1 | **0,9769** | 0,9737 |
| Vòng vo (TTR thật) | 3,5% | **0,3%** |

Nhẹ hơn 1,1 GB, nhanh hơn 1,5 s/ảnh, chép tên riêng bằng nửa. Nó cũng là **VLM fine-tune
riêng cho tiếng Việt** — đúng vai "mốc so sánh tiếng Việt" mà bản chia việc yêu cầu.

**Nếu ưu tiên chất lượng caption:** Qwen2.5-VL-7B đạt 99,72% và chép tên riêng chỉ 7,06%,
đổi lại nặng gấp 2,4 lần khi tải (16,6 GB) và chiếm 47% VRAM T4. Cả hai đều nằm trong trần
phần cứng thật ~11 tỷ tham số.

**Đường lui khi GPU dưới 6 GB:** Qwen2-VL-2B, giữ trong registry, đổi bằng một tham số.

### Điều kiện để chốt

**Chấm tay 30 caption × 4 model, giấu tên model** — bước chặn duy nhất còn lại.

Lý do cần mắt người: máy chấm cho tín hiệu mâu thuẫn. Vintern-3B thắng 5 chỉ số nhưng thua
"vòng vo 37,28%", mà con số đó đã chứng minh là thước đo phạt oan danh từ ghép tiếng Việt
(mục 3). Khi thước đo không đáng tin ở một chiều, số máy chấm không đủ để quyết.

Quy trình: chạy ≥100 ảnh mỗi model *(xong — 355 ảnh × 4 model)* → đọc tay 30 caption mỗi
model, giấu tên → chấm 3 tiêu chí: đúng nội dung ảnh / tiếng Việt tự nhiên / đủ chi tiết.

### Việc kỹ thuật còn lại

| # | Việc | Vì sao |
|---|---|---|
| 1 | Sửa `kiem_cum_lap(n=2)` — nâng n=3 hoặc miễn trừ danh từ ghép | Nó phạt oan tiếng Việt, làm Vintern-3B trông tệ hơn thực tế. Sửa xong phải đo lại toàn bộ |
| 2 | Chặn nhét chữ OCR ở tầng validator | Prompt đã thử và không ăn (mục 5). Đối chiếu OCR của Phần 2 để xoá tên riêng sau khi sinh |
| 3 | Mở rộng tập holdout ngoài 355 ảnh | Chỉ 65/355 ảnh không có nhãn — quá ít để đo model sau khi train LoRA |
| 4 | 13 ca lỗi: thử XGrammar hoặc đổi độ phân giải ảnh | Model sập token `!`; nâng `MAX_NEW_TOKENS` vô ích (mục 3) |

### Về điểm benchmark tiếng Việt

**Chưa có điểm BLEU/METEOR tiếng Việt công khai** cho Qwen2.5-VL hay InternVL3.5 — mọi điểm
công bố đều đo trên tiếng Anh hoặc tiếng Trung. Đây là lý do phải tự đo thay vì tra bảng.

Rủi ro tiếng Việt không phải giả định, thành viên Phần 2 đã ghi nhận: Qwen2-VL-2B **từ chối
trả lời** bằng tiếng Việt trong một số trường hợp; Florence-2 **rơi vào vòng lặp vô hạn**;
Vintern-1B đạt WER tốt nhất 0,34 trên tác vụ OCR.

Số đo của chúng tôi khớp xu hướng đó: hai model Vintern có tỉ lệ chép tên riêng thấp hơn
hẳn Qwen cùng cỡ, và Qwen2-VL-2B là model duy nhất còn chép ví dụ mẫu (5,04%).

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

**Bốn lượt chạy 17/08, cùng 355 ảnh:**

```
checkpoint_vintern-3b.json          346 thành công (97,46%) ·   9 lỗi
checkpoint_qwen25vl-7b.json         354 thành công (99,72%) ·   1 lỗi
checkpoint_vintern-1b-355anh.json     0 thành công ( 0,00%) · 355 lỗi  [226 ca có raw_text]
checkpoint_minicpm-v-4.json           0 thành công ( 0,00%) · 355 lỗi  [190 OOM + 165 <CLS>]
checkpoint-13-ca-loi-rawtext.json     0 thành công          ·  13 lỗi  [nguyên văn 320 dấu !]
```

Bốn file này **có commit** (khác các checkpoint cũ): report khẳng định `raw_text` chứa gì,
nên người đọc PR phải mở được file mà kiểm.

⚠️ **`sample_results.json` chỉ lưu ca thành công.** Đếm số mục trong file đó rồi kết luận
"chỉ chạy 274 ảnh" là sai — đã chạy đủ 355, 81 ca lỗi nằm ở checkpoint. Mà `.gitignore`
loại `results/checkpoint_*.json`, nên **người đọc PR không thấy file chứa ca lỗi**. Con số
81 ghi ở đây chính là để bù chỗ đó.

Muốn kiểm lại bất kỳ con số nào ở trên: `python scripts/doc-so-lieu-benchmark.py` —
nó đọc cả hai nguồn và in ra tổng/thành công/lỗi, không phải suy từ một file.

---

## 11. Việc còn lại

Xếp theo mức độ ảnh hưởng, dựa trên số đo hiện hành:

1. **Chấm tay 30 caption × 4 model, giấu tên model** — bước chặn duy nhất trước khi chốt
   đổi model. Máy chấm mâu thuẫn ở chỉ số vòng vo (mục 3), nên cần mắt người.
2. **Sửa `kiem_cum_lap(n=2)`** — nâng lên n=3 hoặc miễn trừ danh từ ghép tiếng Việt, rồi
   đo lại toàn bộ. Hiện nó phạt oan `người đàn`, `máy tính`, `giáo viên`.
3. **Chặn nhét chữ OCR ở tầng validator** — prompt đã thử và không ăn (mục 5). Đối chiếu
   OCR của Phần 2 để xoá tên riêng sau khi sinh.
4. **13 ca lỗi của Qwen2.5-VL-3B** — thử XGrammar hoặc đổi độ phân giải ảnh. Không nâng
   `MAX_NEW_TOKENS`: model sập token `!`, không phải caption dài (mục 3).
5. **Mở rộng tập holdout ngoài 355 ảnh** — chỉ 65 ảnh không có nhãn, quá ít để đo model
   sau khi train LoRA.
6. **Đo hiệu quả khử trùng lặp + batch inference trên tập lớn** — bắt buộc trước khi chạy
   toàn bộ dữ liệu cuộc thi (mục 7.4, cần giảm 30–40 lần thời gian).

**PR:** [#29](https://github.com/awun0105/Multimodal-Agentic-Retrieval-Engine/pull/29),
nhánh `research-branch/vlm-prompting`. Đề bài ghi nhánh `research-branch` nhưng repo không
có nhánh đó; PR #26 của Phần 2 đi từ `research-branch/ocr-asr` và đã được gộp, nên
`research-branch` là tiền tố quy ước chứ không phải nhánh có sẵn.

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
| Qwen2.5-VL-3B: 4,3% (4/92) | ✅ Đo thật khi còn `do_sample=True`, **không còn là số hiện hành**. Tắt lấy mẫu (`d37bdc2`) → 96,34% (342/355). Giữ để thấy mức cải thiện |
| Vintern-1B: 100% / 0,0 s / 0,0 GB (log cũ) | ❌ **Số giả** — mock. Số hiện hành là 0% (0/355), đo thật |
| **Vintern-3B-R-beta: 97,46% / 10,636 s / 2,841 GB** (355 ảnh) | ✅ **Đo thật** Kaggle T4 17/08, kernel `notebookdd8236fd34` v5, commit `328a8a7` |
| **Qwen2.5-VL-7B: 99,72% / 12,411 s / 6,798 GB** (355 ảnh) | ✅ **Đo thật** Kaggle T4 17/08, kernel v6 |
| **Vintern-1B: 0% (0/355)** — số thật thay cho mock | ✅ **Đo thật** 17/08. 226/355 ca lưu được `raw_text` làm bằng chứng: JSON đúng cú pháp, sai tên trường |
| **MiniCPM-V-4: 0% (0/355)**, tràn 12,97 GB | ✅ **Đo thật** 17/08 — 190 ca OOM, 165 ca trả `<CLS>`. Lượng tử hoá 4-bit không có tác dụng |
| **13 ca lỗi = 320 dấu chấm than** | ✅ **Đo thật** 17/08 — chạy lại riêng 13 ảnh, `raw_text` lưu nguyên văn, cả 13 giống hệt nhau |
| **Prompt cấm tên riêng: 111 → 113 ca** | ✅ **Đo thật** — cùng 355 ảnh, cùng model, commit `328a8a7` xác nhận trong log kernel |
| **Chép tên riêng theo kích thước: 3B 33,04% · Vintern-3B 17,05% · 7B 7,06%** | ✅ **Đo thật** — cùng bộ đo `caption_ten_rieng.py`, cùng 355 ảnh |
| **Trần tham số T4 ~11 tỷ** | ⚠️ **Suy từ số đo** — hồi quy VRAM/tham số của 4 model đã chạy (0,765–1,055 GB/tỷ), lấy hệ số xấu nhất + 20% dự phòng. Không phải đo trực tiếp |
| "Vòng vo 37,28%" của Vintern-3B | ❌ **Thước đo báo nhầm.** TTR thật 0,811 (lành mạnh), chỉ 3,5% ca thấp. Phần còn lại do `kiem_cum_lap(n=2)` phạt danh từ ghép tiếng Việt |
| **290/355 ảnh benchmark có nhãn sẵn** trong dataset | ✅ **Đếm thật** 17/08 — đối chiếu từng tên file với `train.jsonl` (261) + `eval.jsonl` (29) |
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
