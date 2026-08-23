# Quy Tắc Cá Nhân Của User (Personal User Rules) - Dev Branch Aligned

## 1. Tập Trung Vào Kiến Trúc Hệ Thống (Architectural Focus)
- **Tập trung vào Kiến trúc & Luồng Dữ Liệu:** Bỏ qua các tính toán và công thức toán học phức tạp. Giải thích rõ ràng về cấu trúc mô hình, sơ đồ luồng (data flow), cách các thành phần liên kết với nhau, và ưu nhược điểm kiến trúc.
- **Code là công cụ thực thi của Agent:** Hạn chế trình bày code thô dài dòng; tập trung vào mô hình hóa thành phần, luồng xử lý và kết quả thực thi.
- **Bắt buộc cung cấp BẰNG CHỨNG (Empirical Evidence):** Sau MỖI BƯỚC làm việc, AI Agent PHẢI chạy lệnh kiểm thử và trưng ra **bằng chứng cụ thể** (Log Terminal, dữ liệu output mẫu, kết quả benchmark) để User kiểm chứng trực tiếp.

## 2. Quy Tắc Tuân Thủ Hợp Đồng Dữ Liệu Chi Nhánh `dev` (Data Contracts Alignment)
- **Tài liệu chuẩn làm mốc (Canonical Docs):** Mọi thay đổi code hoặc schema phải tham chiếu trực tiếp đến `docs/architecture/data-contracts.md` và `docs/README_CANONICAL_MAP.md` trên nhánh `dev`.
- **Chuẩn hóa đặt tên reference:**
  - `video_ref`: Reference logic cho video thô.
  - `keyframe_ref`: Reference logic cho ảnh keyframe.
  - `thumbnail_ref`: Reference logic cho ảnh thumbnail.
- **Mô hình Embedding chuẩn:** Sử dụng **SigLIP Base** (`google/siglip-base-patch16-224`) làm mô hình mặc định. Lưu trữ index tại `indexes/siglip.faiss` và tra cứu qua `vector_map` + `embeddings_meta` trong SQLite.

## 3. Tối Ưu Tốc Độ Truy Vấn & Sub-Agent Cải Tiến Prompt
- **Offline Pre-processing (System 1):** Toàn bộ các công đoạn nặng (VLM captioning, OCR, ASR, SigLIP embedding, FAISS indexing) PHẢI thực hiện offline ở System 1.
- **Live Search (System 2):** Thời gian phản hồi live search trực tiếp phải < 200ms.
- **Prompt Optimizer Sub-Agent:**
  - Xây dựng Sub-Agent/Local Rules để làm giàu prompt (bổ sung bối cảnh, đối tượng, màu sắc).
  - Hiển thị/xác nhận lại Prompt đã làm giàu với User trước khi thực hiện tìm kiếm chính thức.

## 4. Kiến Trúc Song Song Hybrid Local + Cloud API (Dual-Stream)
- **Stream A (Local Model - Fast Path):** Phản hồi siêu nhanh với SigLIP Base / FAISS tại Local (< 100ms) để hiển thị ngay kết quả sơ bộ trên Web UI.
- **Stream B (Cloud API Model - High Accuracy Path):** Gọi Gemini / Claude API song song để làm giàu Prompt và Re-rank top K kết quả chính xác cao nhất.
- **Cơ chế Fallback:** Tự động dùng kết quả Stream A (Local) nếu kết nối API Cloud chập chờn.

## 5. Nhật Ký Giao Tiếp & Ghi Nhớ Bối Cảnh (Notes & Communication Logs)
- Lưu trữ nhật ký giao tiếp, bài học và tiến độ từng giai đoạn vào thư mục `.agents/notes/`.
- Định dạng nội dung rõ ràng để dễ dàng Handover hoặc Cross-Validation với các AI Agent khác.
## 6. Giao tip vA XAc nh-n Tr>c Khi Thc Thi (Pre-execution Clarification)
- **B_t buTc gii thA-ch tr>c:** Phi thA'ng bAo khAi quAt cAc b>c d <nh lAm vA YAU C^U User xAc nh-n "ng A1 tr>c khi chy bt k lnh / script thc thi nAo (lAm cho User hiu rA bn c n chy gA  "ng A1).

## 7. Quy Chucn Vit Code (Cloud & Documentation)
- **Ti u hA3a Cloud (Kaggle/Colab):** Khi vit code cho mi tr?ng Cloud, phi b trA- cu trAc linh hot (Parallelism) ti u cho c Dual GPU (DataParallel) ln TPU (PyTorch-XLA). LuA'n tA-ch hp ch T DEBUG_MODE = True/False  chy th test vi size nh? tr>c khi chy toAn bT.
- **Ti liu hA3a chuyAn nghip:** Trong m?i file code .py hoc .ipynb, phi cA3 comment h>ng dn s- dng c th, chucn mc vA chuyAn nghip. Uu ti�n dnh dng .ipynb khi thit k kch bn Cloud (Kaggle/Colab) cho trc quan.
- **Handover Notes:** B_t buTc lu tin T vA h>ng dn vAo th mc .agents/notes/handover_log.md  bAn giao cho Agent di sau d. dAng tip qun.
