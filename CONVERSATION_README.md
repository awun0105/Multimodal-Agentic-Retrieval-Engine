# Sổ Cái Bàn Giao & Quản Trị Hệ Thống: Danh Mục Tính Năng & Giải Pháp Kỹ Thuật (System Master Ledger & Feature Registry)

Tài liệu này là **Kênh Bàn Giao & Quản Trị Trung Tâm (Central Master Ledger)** lưu trữ toàn bộ các yêu cầu từ Người dùng, các quyết định kiến trúc, danh mục tính năng hoàn chỉnh, và các hướng giải quyết kỹ thuật được xây dựng bởi AI Agent xuyên suốt dự án **Multimodal Agentic Retrieval Engine (AIC 2026)**.

---

## 1. Quy Định Vận Hành Kênh Bàn Giao (Ledger Governance Rules)

1. **Nguồn Sự Thật Duy Nhất Cho Tiến Trình Bàn Giao:** Mọi tính năng mới, cải tiến thuật toán, hoặc cấu trúc dữ liệu sau khi được hoàn thiện và kiểm nghiệm bắt buộc phải được ghi nhận vào tài liệu này.
2. **Nguyên Tắc Kiểm Tra Trùng Lặp (Deduplication Check):** Trước khi cập nhật hoặc đề xuất giải pháp mới, AI Agent phải rà soát các mục gần nhất trong tài liệu này để kiểm tra xem vấn đề đã được giải quyết hoặc có bị xung đột thông tin hay không.
3. **Tính Độc Lập & Sẵn Sàng Bàn Giao:** Mọi giải pháp ghi trong tài liệu phải kèm theo đường dẫn file mã nguồn cụ thể (`file:///`) và kết quả đo kiểm định lượng (Empirical Verification Metrics).

---

## 2. Danh Mục 15 Tính Năng Cốt Lõi & Hướng Giải Quyết Kỹ Thuật (Feature & Solution Registry)

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        HỆ THỐNG TÍNH NĂNG ĐA TẦNG CỦA DỰ ÁN                            │
├─────────────────────────┬────────────────────────────┬─────────────────────────────────┤
│ TẦNG TIỀN XỬ LÝ (SYS 1) │ TẦNG TÌM KIẾM (SYS 2)      │ TẦNG QUẢN TRỊ & SUB-AGENTS      │
│ - 1. Packet Counting    │ - 10. VirtualBlobReader    │ - 14. Ma trận phân task 3 vai trò│
│ - 2. Adaptive Keyframe  │ - 11. Hybrid Dual-Stream   │ - 15. Khung kiểm định 5 tiêu chuẩn│
│ - 3. Flat Blank Filter  │ - 12. Interactive Cockpit  │                                 │
│ - 4. Spatio-Temp Dedupl │ - 13. Unified Master CLI   │                                 │
│ - 5. YOLOv8 ByteTrack   │                            │                                 │
│ - 6. SigLIP Base L2 Norm│                            │                                 │
│ - 7. Lower Thirds OCR   │                            │                                 │
│ - 8. faster-whisper ASR │                            │                                 │
│ - 9. SQLite FTS5 + FAISS│                            │                                 │
└─────────────────────────┴────────────────────────────┴─────────────────────────────────┘
```

### Feature 1: Giải Mã Frame Stream Tuyệt Đối Qua Packet Counting (Phase 00)
- **Vấn đề:** Ban tổ chức (BTC) decode video bằng ước lượng thời gian `pts_time * fps`, dẫn đến việc số thứ tự khung hình (`frame_id`) bị lệch từ 1 đến 5 frame so với video gốc khi nộp bài chấm điểm tự động.
- **Giải pháp từ Agent:** Sử dụng FFmpeg Packet Counting (`av_read_frame` packet iteration) để đếm chính xác từng packet thực tế, tạo bảng `frame_timeline/{video_id}.parquet` làm chuẩn mốc thời gian duy nhất cho toàn bộ hệ thống.
- **Mã nguồn:** [system1-kaggle-pipeline/src/frame_timeline.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/frame_timeline.py).

### Feature 2: Trích Xuất Keyframe Thích Ứng & Lọc Độ Nét Laplacian (Phase 01)
- **Vấn đề:** Lấy mẫu định kỳ cứng nhắc làm trôi mất khoảnh khắc cao trào (Action Climax), hoặc tạo ra nhiều khung hình bị nhòe chuyển động (Motion Blur).
- **Giải pháp từ Agent:**
  1. Phân tách cú máy thực tế bằng TransNet V2 / Histogram Correlation.
  2. Lấy mẫu đa dải tại các điểm 20%, 50%, 80% độ dài cú máy.
  3. Áp dụng bộ lọc phương sai Laplacian $\text{Var}(\nabla^2 I) \ge 40.0$. Nếu frame ứng viên bị nhòe, tự động quét tìm khung hình nét nhất trong phạm vi $\pm 2$ frame lân cận.
- **Mã nguồn:** [system1-kaggle-pipeline/src/adaptive_keyframe.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/adaptive_keyframe.py).

### Feature 3: Lọc Khung Hình Đơn Sắc Phẳng & Bóc Tách Ngày Tháng Tiêu Đề
- **Vấn đề:** Các khung hình chuyển cảnh đen/trắng đơn sắc làm rác cơ sở dữ liệu; câu hỏi KIS thường yêu cầu mốc ngày phát sóng.
- **Giải pháp từ Agent:**
  1. Thêm hàm `is_blank_or_solid_monochrome` dựa trên độ lệch chuẩn spatial std và text energy để loại bỏ hoàn toàn các khung hình đơn sắc.
  2. Thêm hàm `extract_date_info_from_title` bóc tách ngày tháng dạng `YYYY-MM-DD` hoặc `DD/MM/YYYY` từ siêu dữ liệu tiêu đề video.
- **Mã nguồn:** [system1-kaggle-pipeline/scripts/benchmark_runner.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts/benchmark_runner.py).

### Feature 4: Lọc Trùng Lặp Thích Ứng Không Gian - Thời Gian (Spatio-Temporal Deduplication)
- **Vấn đề:** Các cảnh tĩnh dài (ví dụ: người ngồi phỏng vấn, bài giảng) sinh ra quá nhiều keyframe giống nhau gây loãng kết quả tìm kiếm.
- **Giải pháp từ Agent:** 
  1. Xây dựng hàm `check_object_difference` kiểm tra xem giữa hai mốc có sự xuất hiện của class vật thể mới, thay đổi số lượng, hoặc chênh lệch độ tin cậy lớn (>0.25) hay không.
  2. Nếu khoảng cách thời gian liền kề dưới 3.0 giây (3 trang) và độ tương quan histogram màu sắc $> 0.88$ đồng thời không có thay đổi vật thể lớn, hệ thống sẽ loại bỏ frame trùng và giữ lại frame sắc nét nhất.
- **Mã nguồn:** [interactive-test-app/app.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/interactive-test-app/app.py) và [system1-kaggle-pipeline/scripts/benchmark_runner.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts/benchmark_runner.py).

### Feature 5: Theo Dõi & Đếm Vật Thể Động Trên Video (YOLOv8 + ByteTrack)
- **Vấn đề:** Phân tích tĩnh từng frame đơn lẻ dễ bị đếm trùng lặp và không nắm bắt được tính liên tục của đối tượng di chuyển.
- **Giải pháp từ Agent:**
  1. Tích hợp mô hình `yolov8n.pt` kết hợp thuật toán `ByteTrack` (`model.track`) chạy ở tần suất mẫu 5 FPS.
  2. Xây dựng bản đồ hành trình `active_tracks` ghi nhận `first_seen` và `last_seen` của từng `track_id` duy nhất.
  3. Thống kê số lượng vật thể *duy nhất* trong mỗi cú máy (shot-level deduplication), loại bỏ hoàn toàn hiện tượng đếm lặp khi quay cận cảnh.
- **Mã nguồn:** [system1-kaggle-pipeline/src/object_detector.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/object_detector.py).

### Feature 6: Trích Xuất Vector Nhúng SigLIP Base Chuẩn Hóa L2-Norm (Phase 02)
- **Vấn đề:** Mô hình CLIP ViT-B/32 cũ dùng hàm mất mát Softmax trên toàn batch gây bẫy gán nhầm thuộc tính màu sắc trong KIS (áo đỏ cạnh xe xanh).
- **Giải pháp từ Agent:** Chuyển sang mô hình **SigLIP Base (`google/siglip-base-patch16-224`)** sử dụng Sigmoid Loss độc lập trên từng cặp ảnh-chữ, trích xuất vector 768D và chuẩn hóa Euclidean $L_2\text{-Norm} = 1.0$ để tìm kiếm bằng tích vô hướng Inner Product trong FAISS.
- **Mã nguồn:** [system1-kaggle-pipeline/src/vector_extractor.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/vector_extractor.py).

### Feature 7: Bóc Tách Chữ Tiếng Việt & Phân Vùng Chân Trang (Lower Thirds OCR)
- **Vấn đề:** Bỏ sót các dòng chữ chạy tin vắn (Tickers) trong các bản tin HTV/VTV hoặc bảng tỉ số thể thao.
- **Giải pháp từ Agent:** Sử dụng EasyOCR quét chữ tiếng Việt có dấu, phân vùng quét chuyên biệt cho khu vực chân trang $y > 0.65$ và gắn cờ `is_lower_third = 1` trong cơ sở dữ liệu.
- **Mã nguồn:** [system1-kaggle-pipeline/src/ocr_extractor.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/ocr_extractor.py).

### Feature 8: Nhận Diện Lời Thoại Tiếng Việt Gắn Nhãn Mili-Giây (faster-whisper Large-V3)
- **Vấn đề:** Nhiễu âm thanh nhạc nền trong Talkshow/Gameshow làm ASR nhận diện sai chính tả tiếng Việt.
- **Giải pháp từ Agent:** Sử dụng `faster-whisper large-v3` trên GPU (CTranslate2 FP16) kết hợp bộ lọc giọng nói `vad_filter=True` và `initial_prompt` định hướng tin tức/thể thao tiếng Việt, liên kết mốc thời gian `[start_sec, end_sec]` với keyframe phục vụ Video Q&A.
- **Mã nguồn:** [system1-kaggle-pipeline/src/asr_transcriber.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/asr_transcriber.py).

### Feature 9: Đóng Gói Chỉ Mục Tìm Kiếm SQLite WAL FTS5 & FAISS SQ8 (Phase 03)
- **Vấn đề:** Truy vấn văn bản không dấu/có dấu bị chậm và chỉ mục vector tốn nhiều dung lượng RAM trên máy thi đấu.
- **Giải pháp từ Agent:**
  1. Tạo `runtime.sqlite` với bảng ảo FTS5 `text_documents_fts` sử dụng tokenizer `unicode61 remove_diacritics 2` gộp chung Tiêu đề, ASR, OCR và thuộc tính KIS.
  2. Xây dựng chỉ mục `siglip.faiss` lượng tử hóa 8-bit **FAISS SQ8** (`METRIC_INNER_PRODUCT`), giảm 4 lần dung lượng RAM mà vẫn giữ nguyên độ chính xác Cosine.
- **Mã nguồn:** [system1-kaggle-pipeline/src/db_builder.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/db_builder.py).

### Feature 10: Cơ Chế Đọc Ảo `VirtualBlobReader` & Chiến Thuật Zero Disk Waste
- **Vấn đề:** Môi trường Kaggle bị giới hạn nghiêm ngặt ở mức 20GB Disk. Việc giải nén hàng chục vạn ảnh tĩnh ra đĩa sẽ làm tràn bộ nhớ và mất nhiều giờ inode indexing.
- **Giải pháp từ Agent:** Gom toàn bộ ảnh vào tệp nhị phân duy nhất `keyframes.blob` chuẩn `ZIP_STORED` (chi phí giải nén CPU bằng 0). Xây dựng `VirtualBlobReader` đọc trực tiếp byte ảnh từ RAM qua `io.BytesIO`. Thư mục `/kaggle/working/` chỉ chứa 2 tệp xuất bản < 1GB.
- **Mã nguồn:** [test-mvp-kaggle/kaggle_mvp_runner.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/test-mvp-kaggle/kaggle_mvp_runner.py) và [monolith-mvp-app/mvp-app/app.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/monolith-mvp-app/mvp-app/app.py).

### Feature 11: Kiến Trúc Song Song Hybrid Dual-Stream (Local Fast Path + Cloud API)
- **Vấn đề:** Cần cân bằng giữa tốc độ phản hồi tức thì khi thi đấu trực tiếp và độ chính xác cao khi sử dụng mô hình ngôn ngữ lớn.
- **Giải pháp từ Agent:**
  - **Stream A (Local Model - Fast Path):** SigLIP Base / FAISS SQ8 chạy tại Local, phản hồi kết quả sơ bộ dưới 100ms.
  - **Stream B (Cloud API Model - High Accuracy Path):** Gọi Gemini 3.1 Pro / GPT-4o song song để dịch câu truy vấn, tối ưu hóa Prompt KIS và re-rank lại Top K trong 1-2 giây.
  - **Fallback Tự Động:** Nếu mất kết nối Internet hoặc API bị timeout, hệ thống tự động trả lời bằng kết quả Stream A an toàn.

### Feature 12: Giao Diện Đối Soát Side-by-Side Timeline Studio (4 Tabs)
- **Vấn đề:** Cần một giao diện trực quan cho người dùng đối soát chất lượng giữa dữ liệu BTC và System 1, kiểm thử tham số và thử nghiệm chuỗi sự kiện TRAKE.
- **Giải pháp từ Agent:** Xây dựng ứng dụng Gradio đa năng gồm 4 Tab:
  - **Tab 1:** So sánh Side-by-Side (BTC vs System 1) với dòng thời gian trung tâm, nút mở YouTube đúng giây, và trình soi metadata/objects.
  - **Tab 2:** Cấu hình tham số ngưỡng lọc và tùy chỉnh mô hình AI.
  - **Tab 3:** Tìm kiếm tương tác văn bản và lọc thuộc tính.
  - **Tab 4:** Trình giải bài toán chuỗi sự kiện TRAKE qua quy hoạch động (Dynamic Programming).
- **Mã nguồn:** [interactive-test-app/app.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/interactive-test-app/app.py).

### Feature 13: Trình Điều Phối Thống Nhất CLI Master Runner (`benchmark_runner.py`)
- **Vấn đề:** Các kịch bản kiểm thử bị phân mảnh thành nhiều file script rời rạc khó sử dụng.
- **Giải pháp từ Agent:** Quy hoạch toàn bộ vào một file duy nhất `benchmark_runner.py` hỗ trợ 3 chế độ: `--mode steps` (4 bài test dữ liệu thật), `--mode raw_video` (quét video MP4 thô), và `--mode 10_videos` (benchmark đối soát 10 video).
- **Mã nguồn:** [system1-kaggle-pipeline/scripts/benchmark_runner.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts/benchmark_runner.py).

### Feature 14: Kênh Phân Task 3 Vai Trò & Master Handover Prompt (Rule 11 & Rule 6)
- **Vấn đề:** Cần phân rã dự án thành các module độc lập và chuẩn hóa bối cảnh để giao việc cho các mô hình AI khác (Claude 3.5 Sonnet, GPT-4o, Gemini 3.1 Pro).
- **Giải pháp từ Agent:**
  1. Thiết lập Ma trận phân task 3 vai trò (Orchestration, Execution, Validation) kèm Hợp đồng dữ liệu JSON/Dict chuẩn tắc tại [system1_subagent_task_delegation.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/.agents/communication/system1_subagent_task_delegation.md).
  2. Tạo Master Handover Prompt sẵn sàng cho sao chép nguyên văn tại [subagent_master_handover_prompt.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/.agents/communication/subagent_master_handover_prompt.md).

### Feature 15: Khung Kiểm Định Tự Động 5 Tiêu Chuẩn Cho Sub-Agents
- **Vấn đề:** Cần đảm bảo các module do Sub-Agents phát triển đạt chuẩn chất lượng định lượng trước khi bàn giao cho User.
### Feature 16: Trích Xuất Keyframe Theo Sự Kiện Vật Thể (Object Enter/Exit Keyframe Tracking)
- **Vấn đề:** Lấy mẫu đều ở giữa cú máy (50%) dễ bỏ lỡ khoảnh khắc nhân vật/vật thể vừa xuất hiện hoặc rời đi trong các câu hỏi KIS/TRAKE.
- **Giải pháp từ Agent:** Sử dụng ByteTrack ghi nhận mốc `first_seen` và `last_seen`. Áp dụng Heuristic ức chế đám đông (Crowd Suppression): Khi $\le 5$ người, lấy keyframe tại mốc xuất hiện/biến mất (thời lượng $\ge 0.8\text{s}$); Khi $> 5$ người, chuyển sang lấy mẫu đều (20%, 50%, 80%) kết hợp bộ lọc Laplacian $\ge 40.0$.
- **Mã nguồn:** [src/object_detector.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/object_detector.py) và [scripts/steps/test_step1_event_keyframes.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts/steps/test_step1_event_keyframes.py).

### Feature 17: Video OCR Trực Tiếp & Khử Trùng Lặp Cấp Cú Máy (Shot-Level Deduplication)
- **Vấn đề:** Quét OCR video dễ sinh ra nhiều chuỗi trùng lặp làm phình to database và nhiễu tìm kiếm.
- **Giải pháp từ Agent:** Phân vùng không gian (chân trang $y > 0.65$ cho tin tức vs trung tâm cho biển báo $\text{conf} \ge 0.7$). Khử trùng lặp cấp cú máy qua Jaccard $\ge 0.85$ và quan hệ chuỗi con, giảm $>55\%$ chuỗi thừa và giữ dung lượng DB $< 50\text{MB}$.
- **Mã nguồn:** [src/ocr_extractor.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/ocr_extractor.py) và [scripts/steps/test_step2_video_ocr_dedup.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts/steps/test_step2_video_ocr_dedup.py).

### Feature 18: Cơ Sở Dữ Liệu ASR Phân Đoạn Theo Timestamp Phục Vụ Video QA
- **Vấn đề:** Các câu hỏi Video QA đòi hỏi tra cứu lời thoại tiếng Việt chính xác theo mốc giây.
- **Giải pháp từ Agent:** Tạo bảng `asr_segments` và bảng ảo `asr_fts` (FTS5 Unicode tiếng Việt) trong `runtime.sqlite`. Cho phép tra cứu câu hỏi có/không dấu trong $< 2\text{ms}$ và nhảy trực tiếp đến giây phát biểu tương ứng.
- **Mã nguồn:** [src/db_builder.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/db_builder.py) và [scripts/steps/test_step3_asr_timestamp_qa.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts/steps/test_step3_asr_timestamp_qa.py).

### Feature 19: Phân Loại Thể Loại Video Từ Metadata & Định Tuyến Trọng Số RRF (Genre Classifier)
- **Vấn đề:** Các thể loại video khác nhau (tin tức, giáo dục, thể thao, show) có trọng số tìm kiếm tối ưu khác nhau giữa Visual và Text.
- **Giải pháp từ Agent:** Xây dựng module `VideoGenreClassifier` nhận diện 5 nhóm (`news`, `education`, `sports`, `entertainment`, `general`) siêu nhanh ($< 0.1\text{ms}$) từ tiêu đề/mô tả để tự động điều chỉnh tỷ lệ điểm RRF (Dynamic Weight Routing).
- **Mã nguồn:** [src/genre_classifier.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/genre_classifier.py) và [scripts/steps/test_step4_genre_classifier.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts/steps/test_step4_genre_classifier.py).

### Feature 20: Quy Hoạch Hệ Sinh Thái Tài Liệu 5 Tầng & Chuẩn Hóa Agent Header Protocol
- **Vấn đề:** Các ghi chú kỹ thuật, hướng dẫn luồng và ràng buộc quy tắc bị phân tán, thiếu khối ngữ cảnh chuẩn tắc ở đầu tệp cho các AI Agent kế nhiệm.
- **Giải pháp từ Agent:** Quy hoạch 5 tầng tài liệu rõ ràng (`README.md`, `PIPELINE_FLOW_AND_VERIFICATION.md`, `KEYFRAME_PIPELINE_README.md`, `plans/`, `EXECUTION_MILESTONES.md` + `scripts/README.md`), đồng thời tích hợp khối chú thích **Agent Context & Protocol Header** chuẩn tắc vào đầu 100% các file Markdown giải thích rõ vai trò, các quy tắc áp dụng (Rule 1, 10, 11, 12, 13, 14), liên kết upstream/downstream và lệnh test tương ứng.
- **Mã nguồn:** Toàn bộ thư mục [system1-kaggle-pipeline/](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/).

### Feature 21: Hợp Nhất Timeline BTC-Self, Đếm Vật Thể 'Nhãn x Số lượng' & Khử Trùng Lặp Ảo Cắt Nghĩa (Step 5)
- **Vấn đề:** Cần đồng bộ chính xác trục thời gian giữa keyframe của BTC và System 1, đếm số lượng đối tượng rõ ràng (Cờ x 5, Người x 2...) để tối ưu hóa truy vấn KIS, đồng thời loại bỏ các ảnh trùng lặp trong cửa sổ trượt 3 frame nhưng không làm mất thông tin thời gian hoặc nội dung OCR mới.
- **Giải pháp từ Agent:**
  1. Hợp nhất mốc thời gian $|\Delta t| \le 0.05\text{s}$ giữa BTC và System 1 thành 1 bản ghi duy nhất, gán `btc_frame_idx`.
  2. Xây dựng bộ đếm chuẩn hóa `format_object_counts()` chuyển đổi sang định dạng `"Nhãn x Số lượng"`.
  3. Cửa sổ trượt 3 frame đo độ tương đồng thị giác ($\ge 0.92$) với quy tắc **Ngoại lệ OCR** (giữ lại frame độc lập nếu văn bản thay đổi).
  4. Cơ chế **Frame Cắt Nghĩa (Virtual Reference Frame)**: Zero Disk Waste (không nhân bản ảnh), lưu `delta_time_sec` (`+1.2s`, `-0.8s`) và hiển thị trên UI với khuôn viền màu tím Neon / Violet (`#bd93f9`).
- **Mã nguồn:** [src/timeline_synchronizer.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/timeline_synchronizer.py) và [scripts/steps/test_step5_timeline_merge_dedup.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts/steps/test_step5_timeline_merge_dedup.py).

### Feature 22: Nâng Cấp Interactive Studio 5 Tab, Quản Lý Lưu Trữ Persistence & Nén Ảnh WebP Tiết Kiệm Bộ Nhớ
- **Vấn đề:** Người dùng cần kiểm tra trực quan toàn bộ kết quả trên UI, xem lại các kết quả đã được lưu trữ trong hệ thống, xuất báo cáo CSV/JSON và tải ảnh mượt mà không làm quá tải bộ nhớ trình duyệt.
- **Giải pháp từ Agent:**
  1. Nâng cấp [interactive-test-app/app.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/interactive-test-app/app.py) thành Studio 5 tab: (1) Đối Soát Timeline Side-by-Side, (2) Quản Lý Lưu Trữ Persistence & Xuất Báo Cáo, (3) Khám Phá Step 1-5 (Genre, ASR QA, OCR, Frame Cắt Nghĩa viền tím), (4) Tìm Kiếm KIS Nhanh, (5) Studio Tùy Chỉnh Tham Số Đầu Vào.
  2. Tích hợp bộ nén WebP Base64 Thumbnail (140x78) kèm RAM caching `pil_to_base64_thumb()` giúp tiết kiệm $>90\%$ dung lượng bộ nhớ so với ảnh JPEG thô 1080p và loại bỏ hoàn toàn hiện tượng lag trình duyệt.
  3. Cơ chế xuất báo cáo đối soát ra `exported_benchmark_report.csv` và `exported_benchmark_report.json`.
- **Mã nguồn:** [interactive-test-app/app.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/interactive-test-app/app.py) và [interactive-test-app/launcher.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/interactive-test-app/launcher.py).



---

## 3. Bản Đồ Các Thành Phần Mã Nguồn (Component Map)

| Thành Phần | Vị Trí File Mã Nguồn | Mô Tả Chức Năng |
| :--- | :--- | :--- |
| **Ingestion Pipeline** | [system1-kaggle-pipeline/src/kaggle_runner.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/kaggle_runner.py) | Điều phối toàn bộ quy trình tiền xử lý 5 bước trên Kaggle. |
| **Timeline Synchronizer** | [system1-kaggle-pipeline/src/timeline_synchronizer.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/timeline_synchronizer.py) | Hợp nhất timeline BTC-Self, đếm vật thể & Frame Cắt Nghĩa viền tím. |
| **Genre Classifier**   | [system1-kaggle-pipeline/src/genre_classifier.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/genre_classifier.py) | Phân loại thể loại video từ metadata và cung cấp trọng số RRF. |
| **Frame Timeline** | [system1-kaggle-pipeline/src/frame_timeline.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/frame_timeline.py) | Packet counting giải mã mốc thời gian tuyệt đối. |
| **Shot Detection** | [system1-kaggle-pipeline/src/shot_detector.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/shot_detector.py) | Phân tách cú máy qua TransNet V2 / Histogram Correlation. |
| **Adaptive Keyframe** | [system1-kaggle-pipeline/src/adaptive_keyframe.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/adaptive_keyframe.py) | Lấy mẫu đa dải (20%-50%-80%) và bộ lọc độ nét Laplacian. |
| **Audio ASR** | [system1-kaggle-pipeline/src/asr_transcriber.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/asr_transcriber.py) | `faster-whisper large-v3` bóc tách lời thoại tiếng Việt có dấu. |
| **OCR Extractor** | [system1-kaggle-pipeline/src/ocr_extractor.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/ocr_extractor.py) | EasyOCR bóc tách chữ có dấu, phân vùng chân trang và khử trùng lặp shot. |
| **Object Detector** | [system1-kaggle-pipeline/src/object_detector.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/object_detector.py) | YOLOv8 + ByteTrack theo dõi vật thể và bắt keyframe Enter/Exit. |
| **Vector Extractor** | [system1-kaggle-pipeline/src/vector_extractor.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/vector_extractor.py) | SigLIP Base trích xuất vector nhúng 768D chuẩn hóa $L_2 = 1.0$. |
| **Semantic Enricher** | [system1-kaggle-pipeline/src/semantic_enricher.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/semantic_enricher.py) | Bóc tách 6 trường thuộc tính KIS chuyên sâu. |
| **DB & Index Builder**| [system1-kaggle-pipeline/src/db_builder.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/db_builder.py) | Đóng gói SQLite FTS5 Unicode (kèm asr_fts cho Video QA) và FAISS Index SQ8. |
| **Enhancement Plan**  | [system1-kaggle-pipeline/plans/KEYFRAME_ENHANCEMENT_PLAN_AND_SUBAGENT_TASKS.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/plans/KEYFRAME_ENHANCEMENT_PLAN_AND_SUBAGENT_TASKS.md) | Kế hoạch 4 bước nâng cấp và ma trận phân việc 3 vai trò cho Sub-Agents. |
| **Master CLI Runner** | [system1-kaggle-pipeline/scripts/benchmark_runner.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts/benchmark_runner.py) | Trình điều phối CLI đa năng (steps, raw_video, 10_videos). |
| **Validation Harness**| [system1-kaggle-pipeline/scripts/validate_subagent_pipeline.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts/validate_subagent_pipeline.py) | Khung kiểm định tự động 5 tiêu chuẩn cho Sub-Agents. |
| **Flow & Verification**| [system1-kaggle-pipeline/PIPELINE_FLOW_AND_VERIFICATION.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/PIPELINE_FLOW_AND_VERIFICATION.md) | Cẩm nang luồng vận hành đầu-cuối và ma trận kiểm định chất lượng tổng quan. |
| **Keyframe Pipeline** | [system1-kaggle-pipeline/KEYFRAME_PIPELINE_README.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/KEYFRAME_PIPELINE_README.md) | Sổ tay tổng kết nhánh xử lý Keyframe & Phân loại ranh giới dữ liệu Git/Local. |
| **Interactive Studio**| [interactive-test-app/app.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/interactive-test-app/app.py) | Giao diện Studio đối soát Side-by-Side và kiểm thử truy vấn. |
| **Studio BAT Launcher**| [start_interactive_test_app.bat](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/start_interactive_test_app.bat) + [launcher.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/interactive-test-app/launcher.py) | Trình khởi chạy 1-click nhấp đúp chuột, tự động giải phóng port 7860 và hot reload. |
| **Kaggle 1-Click**    | [system1-kaggle-pipeline/notebooks/kaggle_master_pipeline.ipynb](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/notebooks/kaggle_master_pipeline.ipynb) | Notebook chạy trọn gói System 1 trên Kaggle GPU kép / TPU. |

---

## 4. Bảng Bằng Chứng Thực Nghiệm Định Lượng (Empirical Proof Matrix)

| Hạng Mục Kiểm Định | Kết Quả Định Lượng | Trạng Thái | Bằng Chứng Lưu Trữ |
| :--- | :--- | :--- | :--- |
| **Cắt cú máy video thô (`L21_V001.mp4`)** | 257 cú máy từ 37,849 frames (1,513.9s), tốc độ **203.1 fps**. | **ĐẠT** | [L21_V001_shots.csv](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/test_output/raw_video/L21_V001_shots.csv) |
| **Độ sắc nét Laplacian** | Điểm sắc nét trung bình đạt **548.88** (không có frame < 40.0). | **ĐẠT** | `test_output/raw_video/L21_V001/` |
| **Benchmark 5 video đầu L21** | Trích xuất thành công **300 keyframes** tối ưu trong 344s. | **ĐẠT** | [benchmark_summary.csv](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/test_output/side_by_side_benchmark/benchmark_summary.csv) |
| **Step 1 Test: Event Keyframes** | 100% bắt trúng mốc Enter/Exit cho $\le 5$ người, lọc nhiễu $< 0.8\text{s}$, kích hoạt Crowd Suppression. | **ĐẠT** | [scripts/steps/test_step1_event_keyframes.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts/steps/test_step1_event_keyframes.py) |
| **Step 2 Test: OCR Dedup** | Giảm $>55\%$ chuỗi trùng lặp qua Jaccard $\ge 0.85$, phân vùng chân trang $y > 0.65$ chuẩn xác. | **ĐẠT** | [scripts/steps/test_step2_video_ocr_dedup.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts/steps/test_step2_video_ocr_dedup.py) |
| **Step 3 Test: Video QA ASR FTS5** | 100% khớp câu hỏi Video QA có/không dấu, trả về mốc giây chính xác $< 2\text{ms}$. | **ĐẠT** | [scripts/steps/test_step3_asr_timestamp_qa.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts/steps/test_step3_asr_timestamp_qa.py) |
| **Step 4 Test: Genre Classifier** | 9/9 (100%) test cases phân loại đúng thể loại và cấu hình trọng số RRF. | **ĐẠT** | [scripts/steps/test_step4_genre_classifier.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts/steps/test_step4_genre_classifier.py) |
| **Step 5 Test: Timeline Sync & Virtual Dedup** | 6/6 (100%) test cases đạt chuẩn: gộp mốc $|\Delta t| \le 0.05\text{s}$, đếm vật thể 'Nhãn x Số lượng', cửa sổ trượt 3 frame Frame Cắt Nghĩa viền tím, cứu ảnh mờ Sharpening Fallback, nhận diện bối cảnh hậu cảnh, và xuất Bộ Dữ Liệu Hợp Nhất (Unified Dataset). | **ĐẠT** | [scripts/steps/test_step5_timeline_merge_dedup.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts/steps/test_step5_timeline_merge_dedup.py) |
| **Chuẩn hóa Vector SigLIP** | 100% vector đạt $\|v\|_2 = 1.0 \pm 1e-5$, Inner Product = Cosine Sim. | **ĐẠT** | [scripts/validate_subagent_pipeline.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts/validate_subagent_pipeline.py) |
| **Sub-Agent Validation Test** | 5/5 bài test tiêu chuẩn định lượng đạt **100% PASS**. | **ĐẠT** | Execution Log trong [walkthrough.md](file:///C:/Users/Admin/.gemini/antigravity-ide/brain/510ab75c-c380-486e-91a3-72072a386a6f/walkthrough.md) |

---

### Feature 23: Hoàn Thiện Khung Trực Quan Metadata, Cứu Ảnh Mờ (Sharpening Fallback), Nhận Diện Bối Cảnh Môi Trường & Bộ Dữ Liệu Hợp Nhất Cuối Cùng (Dev Branch)
- **Mục tiêu:** Đáp ứng toàn diện các phản hồi của User về trực quan hoá, cứu ảnh mờ, giữ lại các frame đề xuất lọc bỏ với viền đỏ để kiểm duyệt, hiển thị viền xanh Cyan cho BTC, viền tím Neon cho Frame Cắt Nghĩa, hiển thị đầy đủ 8 trường metadata và xuất Bộ Dữ Liệu Hợp Nhất.
- **Hệ thống phân định màu viền (Border Design System):**
  1. **Viền Xanh Cyan (`#8be9fd`):** Keyframe Ban Tổ Chức (BTC) + Badge `[BTC - Ban Tổ Chức]`.
  2. **Viền Tím Neon / Violet (`#bd93f9`):** Frame Cắt Nghĩa (Virtual Proxy Frame) + Badge `[Frame Cắt Nghĩa +Δt]`.
  3. **Viền Đỏ Đậm (`#ff5555`):** Khung hình Đề Xuất Lọc Bỏ (Ảnh mờ / Trùng bối cảnh) + Badge `[Đề Xuất Lọc Bỏ - Lý Do]`.
  4. **Viền Vàng Cam (`#ebcb8b`):** Khung hình được cứu và tăng cường độ nét bằng Unsharp Masking (`is_sharpened_fallback = True`).
  5. **Viền Xanh Lá (`#a3be8c`):** Khung hình hợp lệ tiêu chuẩn System 1.
- **8 Trường Metadata Chuẩn Tắc Hiển Thị Trực Quan:**
  1. **Mốc thời gian:** `Mốc: 00:14.2 (14.2s) | Frame 355 | Dài 2.8s`
  2. **Vật thể & Số lượng:** `Vật thể: Cờ x 5, Người x 2, Xe máy x 1` (hoặc `Không phát hiện vật thể lớn`)
  3. **Bối cảnh chung (Environment):** `Bối cảnh: Trong phòng / Studio` / `Đường phố / Giao thông` / `Nước / Biển` / `Cây cối / Thiên nhiên` / `Unknown`
  4. **Ý nghĩa / Loại cú máy:** `Ý nghĩa: Chuyển Cảnh / Tiêu Đề` / `Cảnh Quay Thị Giác` / `Khung Hình Chuẩn BTC`
  5. **Màu chính chủ đạo:** `Màu: Đỏ Thời Sự` / `Xanh Dương`
  6. **Chữ hiển thị (OCR):** `Chữ / OCR: Bản tin thời sự 19h...`
  7. **Độ nét Laplacian:** `Độ nét: 548.2 (Sắc nét)` / `Độ nét: 32.5 (Đã làm nét)`
  8. **Mã nộp bài:** `{video_id},{frame_idx}`

### Feature 24: Kiểm Duyệt Lọc Bỏ Sau Khi Merge Timeline BTC & Tái Cấu Trúc Ý Nghĩa Toàn Cục Cú Máy (Shot Contextual Meaning)
- **Mục tiêu:**
  1. **Kiểm duyệt sau khi merge:** Loại bỏ việc xóa tùy tiện tại local; giữ 100% keyframe trích xuất và chỉ kiểm duyệt lọc bỏ sau khi đã merge lên timeline chung với BTC theo trục thời gian tăng dần.
  2. **Tái cấu trúc trường "Ý nghĩa":** Đọc ảnh và mô tả khái quát ý nghĩa của frame so với toàn bộ cú máy (Shot-level context) gồm: Hoạt động / Hành động chủ đạo (Activities) và Từ khóa chữ (Text Keywords nếu có).
  3. **Cơ chế suy đoán ngữ cảnh BTC (BTC Context Inference):** Quét tìm keyframe tương đồng cao ($\ge 0.85$) từ System 1 lân cận để kế thừa; nếu không có thì truy ngược video gốc $\pm 1.0\text{s}$ để hiểu trọn vẹn ngữ cảnh shot.
- **Định dạng hiển thị trường "Ý nghĩa" chuẩn tắc:**
  - `Ý nghĩa: Dẫn bản tin trường quay thời sự | Từ khóa: [Thời sự 19h, VTV1]`
  - `Ý nghĩa: Di chuyển giao thông đường phố | Từ khóa: [Biển báo, Ngã tư]`
  - `Ý nghĩa: Thi đấu thể thao / Tranh chấp bóng | Từ khóa: [V-League, Trực tiếp]`
  - `Ý nghĩa: Giảng bài / Ôn thi học thuật | Từ khóa: [Đạo hàm, Toán 12]`
- **Kiểm định:** 6/6 test cases trong `system1-kaggle-pipeline/scripts/steps/test_step5_timeline_merge_dedup.py` đạt **100% PASS**.

### Feature 28: Biên Soạn Master README.md Tổng Hợp Toàn Diện Dự Án Phục Vụ Commit Git
- **Mục tiêu:**
  1. **Bản đồ cấu trúc thư mục & ý nghĩa từng file:** Liệt kê 100% tệp tin và thư mục trong dự án kèm mô tả chức năng chi tiết và đường dẫn markdown có thể nhấp chuột (`file:///`).
  2. **Cẩm nang khởi động & vận hành:** Hướng dẫn 1-Click launcher (`start_interactive_test_app.bat`), chạy trên Kaggle GPU kép và phân tích chi tiết 6 bước xử lý dữ liệu.
  3. **Tổng kết kỹ thuật & hướng đã xử lý:** Đa tag Multi-Badge, ảo hóa Frame Cắt Nghĩa viền tím (`#bd93f9` + $\Delta t$), nhận diện vật thể nhỏ YOLO `conf=0.15`, cứu ảnh mờ Sharpening Fallback, ASR timestamped Video QA, phòng ngừa lỗi dữ liệu biên NaN/None.
  4. **Trung tâm tài liệu & Bàn giao định hướng:** Liên kết đến toàn bộ 7 tài liệu chuyên sâu và vạch rõ lộ trình phát triển System 2 Agentic Search & TraKE.
- **Kiểm định:** Tệp [README.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/README.md) tại gốc dự án đã sẵn sàng 100% để User thực hiện commit Git.







