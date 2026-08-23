# Đề xuất bổ sung mô hình Multimodal Embedding cho AIC 2026

**Bối cảnh:** Pipeline benchmark trên Google Colab (GPU T4), bài toán Video Retrieval (keyframe ảnh + truy vấn văn bản Tiếng Việt, dịch sang tiếng Anh qua API).

**Baseline đang test:** SigLIP Base, CLIP Base, Jina CLIP v2, ViCLIP-OT, SigLIP so400m.

**Mốc so sánh:** Jina CLIP v2 (≈865M tham số, text tower Jina-XLM-RoBERTa hỗ trợ ~89 ngôn ngữ, vision tower EVA02-L, ảnh resize cố định 512×512, cần `trust_remote_code=True`, hỗ trợ Matryoshka embedding tới 1024-dim).

---

## Nhóm 1 — Đa ngôn ngữ / Tiếng Việt (ưu tiên cao)

| Mô hình | Quy mô & VRAM (ước tính FP16, T4 16GB) | Tốc độ | Tương thích HF AutoModel | So với Jina CLIP v2 |
|---|---|---|---|---|
| **google/siglip2-so400m-patch16-naflex** (hoặc bản `base`) | ~400M tham số → ~1–1.5GB weights. NaFlex xử lý ảnh theo tỷ lệ gốc nên VRAM/tốc độ dao động theo độ phân giải ảnh input | Nhanh, dual-encoder thuần túy — tương đương lớp SigLIP so400m đang test | **Native, hoàn hảo**: `AutoModel.from_pretrained(...)` + `AutoProcessor`, không cần code ngoài | Là bản nâng cấp trực tiếp của SigLIP (thêm self-distillation, dense prediction) và **đa ngôn ngữ thật sự**. NaFlex giữ nguyên tỷ lệ khung hình — lợi thế khi keyframe có nhiều tỷ lệ khác nhau, trong khi Jina CLIP v2 resize cố định 512×512 |
| **facebook/metaclip-2-worldwide-huge-378** (hoặc bản `s16` nhỏ hơn nếu ưu tiên tốc độ) | ViT-H/14 ≈ 1B tham số → ~2GB weights; bản `s16` distilled chỉ vài trăm MB | Bản Huge chạy tốt trên T4 với batch vừa phải; bản S16 rất nhanh, phù hợp scan số lượng lớn keyframe | **Native**, đã merge vào `transformers` (từ 8/2025): `AutoModel`/`AutoProcessor` chuẩn | Huấn luyện trên dữ liệu **300+ ngôn ngữ**, công bố vượt mSigLIP và SigLIP-2 trên các benchmark đa ngôn ngữ (XM3600, CVQA, Babel-ImageNet). Không có Matryoshka/instruction như Jina, nhưng có nhiều size (S/B/L/H/Giant) để tune trade-off tốc độ/độ chính xác |
| **Qwen/Qwen3-VL-Embedding-2B** | 2B tham số → ~4GB weights, nhưng do kiến trúc VLM sinh nhiều visual token hơn CLIP thuần → thực tế cần **6–8GB+ VRAM khi batch lớn** | Chậm hơn đáng kể (forward pass kiểu LLM, không phải dual-tower nhẹ) | Qua `sentence-transformers` (`SentenceTransformer(...)`) hoặc `AutoModelForMultimodalLM` (`transformers>=4.57`, `qwen-vl-utils`) — **không phải AutoModel/AutoProcessor kiểu CLIP truyền thống** | Hỗ trợ 30+ ngôn ngữ, SOTA trên MMEB-V2 (75.0 Image Overall bản 2B, vượt GME-2B/7B), Matryoshka (64–2048 dim), instruction-aware. Nhược điểm: nặng và chậm hơn nhiều so với Jina CLIP v2 — không phù hợp để encode toàn bộ index, nên dùng làm **reranker giai đoạn 2** |

## Nhóm 2 — Chỉ tiếng Anh (đáng cân nhắc vì đã dịch VN→EN)

| Mô hình | Quy mô & VRAM | Tốc độ | Tương thích HF AutoModel | So với Jina CLIP v2 |
|---|---|---|---|---|
| **Meta Perception Encoder — PE-Core** (bản `L14` hoặc `B16`; bản `G` ~2B quá nặng cho T4) | B16 ~200M (~0.5GB), L14 ~300–400M (~1GB) | Rất nhanh ở size B/L | **Không native** — dùng qua `open_clip` hoặc `timm`, chưa vào `transformers` chuẩn | Thiết kế đặc biệt cho **cả ảnh lẫn video** (fine-tune trên dữ liệu video tổng hợp), công bố vượt SigLIP2 trên zero-shot classification/retrieval kể cả video. Vì dataset AIC là keyframe cắt từ video, đặc tính "video-aware" này có thể cho embedding sát ngữ cảnh sự kiện hơn CLIP/SigLIP thuần ảnh tĩnh. Nhược điểm: chỉ tiếng Anh, phải tự viết pipeline `open_clip` thay vì `AutoModel` sẵn có |
| **Apple DFN5B-CLIP (ViT-H/14)** | ~1B tham số (~2GB weights) | Tương đương SigLIP so400m | Qua `open_clip`, không native `transformers` AutoModel | Huấn luyện bằng Data Filtering Networks (lọc dữ liệu chất lượng cao), vẫn là baseline zero-shot rất mạnh trên ImageNet/retrieval tiếng Anh. Đưa vào để có điểm đối chứng "CLIP tiếng Anh thuần, độ chính xác cao" — nhưng khó có lợi thế rõ rệt so với PE-Core/SigLIP2/MetaCLIP2 để bù cho việc không đa ngôn ngữ |

---

## Gợi ý ưu tiên triển khai

1. **SigLIP2 so400m-naflex** và **MetaCLIP2-worldwide-huge** — ưu tiên cao nhất: native AutoModel, VRAM nhẹ, batch lớn trên T4, là bản nâng cấp trực tiếp của SigLIP đang có sẵn trong benchmark → dễ so sánh apples-to-apples.
2. **PE-Core (L14)** — đáng thử vì đặc tính video-aware hợp với bản chất keyframe từ video, dù phải tốn công tích hợp `open_clip`.
3. **Qwen3-VL-Embedding-2B** — không dùng để encode toàn bộ index (quá chậm/nặng cho quy mô thi đấu), nhưng đáng thử làm **reranker top-k** sau khi CLIP/SigLIP đã lọc ra top 100–200 ứng viên, vì độ chính xác retrieval (đặc biệt Image RET/Image QA) cao hơn hẳn nhóm dual-encoder.

*Lưu ý: các số liệu VRAM là ước tính dựa trên số tham số ở độ chính xác FP16, chưa tính overhead activation/batch — nên benchmark thực tế trên chính pipeline Colab T4 trước khi chốt.*
