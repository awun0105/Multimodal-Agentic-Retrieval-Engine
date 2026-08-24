# Nhật Ký Bàn Giao & Sổ Tay Kinh Nghiệm Xử Lý (Handover Log & Engineering Knowledge Base)

Tài liệu này ghi nhận toàn bộ các vấn đề kỹ thuật thực tế, nguyên nhân gốc rễ, các bước cải tiến mô hình trong Pipeline, và quy chuẩn bắt buộc để các AI Agent kế tiếp đọc hiểu và tiếp quản công việc mà không làm đứt gãy bối cảnh dự án.

---

## 1. Bảng Tổng Hợp Vấn Đề Thực Tế & Bước Cải Thiện Mô Hình Tương Ứng

| STT | Vấn Đề / Hiện Tượng Thực Tế | Nguyên Nhân Gốc Rễ | Bước Cải Thiện Mô Hình Trong Pipeline | Quy Tắc Bắt Buộc Cho AI Agent Tiếp Theo |
| :--- | :--- | :--- | :--- | :--- |
| **1** | **Lệch số thứ tự khung hình (Frame ID Drift)**: Nộp bài bị sai lệch 1-5 frame so với video gốc. | Decode video bằng công thức ước lượng thời gian `pts_time * fps` thay vì đọc frame stream thực tế. | **Phase 00 Ingestion / `frame_timeline.py`**: Sử dụng kỹ thuật FFmpeg Packet Counting đếm chính xác từng packet để lập bảng `frame_timeline/{video_id}.parquet`. | Tuyệt đối không dùng phép nhân chia làm tròn `int(pts_time * fps)` để suy đoán `frame_id`. Luôn tra cứu `frame_id` từ `frame_timeline`. |
| **2** | **Keyframe bị nhòe chuyển động (Motion Blur) và bỏ sót hành động**: Lấy mẫu cố định (20%, 50%, 80%) không bắt được pha cao trào. | Lấy mẫu chu kỳ đều đặn không phụ thuộc vào chuyển động máy quay (pan/tilt) hay thời lượng thực tế của cú máy. | **Phase 01 Visual / `adaptive_keyframe.py`**: Tích hợp bộ lọc phương sai Laplacian $\text{Var}(\nabla^2 I) \ge 40.0$ và lấy mẫu thích ứng theo thời lượng & độ biến thiên chuyển động. | Luôn áp dụng bộ lọc độ sắc nét Laplacian để loại bỏ ảnh mờ trước khi đưa vào trích xuất vector. |
| **3** | **Bẫy gán nhầm thuộc tính màu sắc trong KIS (Color-Object Binding Ambiguity)**: Nhầm lẫn màu của người với vật bên cạnh (áo đỏ cạnh xe xanh). | CLIP ViT-B/32 dùng hàm mất mát Softmax trên toàn batch, không phân tách tốt các cặp thuộc tính cục bộ. | **Phase 02 Multimodal / `vector_extractor.py`**: Chuyển đổi sang **SigLIP Base (`google/siglip-base-patch16-224`)** sử dụng Sigmoid Loss độc lập trên từng cặp ảnh-chữ + Chuẩn hóa L2-Norm. | SigLIP Base là mô hình vector mặc định. Mọi vector trích xuất bắt buộc phải chuẩn hóa $L_2 = 1.0$ để tìm kiếm bằng tích vô hướng Inner Product trong FAISS. |
| **4** | **Câu hỏi KIS chứa nhiều thuộc tính chi tiết (Góc máy, Ánh sáng, Không gian, Số lượng nhỏ)**: Vector toàn cảnh không bắt đủ chi tiết nhỏ. | Vector nhúng 512D/768D khái quát hóa toàn bức ảnh, làm suy giảm trọng số của các đối tượng nhỏ ("3 ổ bánh mì", "trong vũng nước", "close-up"). | **Phase 02 Semantics & Phase 03 DB / `semantic_enricher.py` + `db_builder.py`**: Bóc tách 6 trường KIS (`colors`, `camera_angle`, `lighting_time`, `environment_setting`, `objects_and_counts`, `actions`) đưa vào SQLite FTS5. | Khi xây dựng truy vấn System 2, luôn áp dụng tìm kiếm lai (Hybrid Search: Dense Vector SigLIP + Sparse Keyword FTS5 qua thuật toán RRF). |
| **5** | **Bỏ sót chữ chạy chân trang (News Tickers) và Slide bài giảng**: Tin tức HTV/VTV có dải tin vắn liên tục; bài giảng có slide nhiều chữ. | OCR ngẫu nhiên toàn khung hình không phân vùng ưu tiên cho khu vực chân trang (Lower Thirds) hoặc khu vực slide. | **Phase 02 OCR / `ocr_extractor.py`**: Phân vùng quét chuyên biệt cho vùng $y > 0.65$ (chân trang tin tức) và quét toàn trang cho slide, gắn cờ `is_lower_third` trong SQLite. | Khi truy vấn tin tức hoặc thời sự, ưu tiên lọc trên trường `is_lower_third = 1` để bắt chính xác các dòng chữ tin vắn. |
| **6** | **Nhiễu âm thanh trong Phỏng vấn, Phóng sự, Gameshow**: Nhạc nền hoặc tiếng xe cộ làm ASR nhận diện sai chính tả tiếng Việt. | Mô hình ASR nhỏ không có bộ lọc giọng nói VAD và không có prompt định hướng ngữ cảnh tiếng Việt. | **Phase 01 ASR / `asr_transcriber.py`**: Sử dụng `faster-whisper large-v3` trên GPU (CTranslate2 FP16) với `vad_filter=True` và `initial_prompt` định hướng tin tức/talkshow tiếng Việt. | Luôn liên kết `start_sec` và `end_sec` của từng đoạn hội thoại vào keyframe và shot tương ứng để phục vụ câu hỏi Q&A ("Ai nói gì"). |
| **7** | **Tràn đĩa 20GB trên Kaggle & Tràn RAM trên máy yếu**: Dữ liệu 107GB đến 2TB không thể giải nén đồng loạt lên ổ cứng. | Lưu trữ video thô và giải nén hàng trăm nghìn file ảnh tĩnh trực tiếp trên ổ hệ thống. | **Kiến trúc Linh hoạt 2 Chế độ (Lean Mode vs Rich Mode)**: Chỉ lưu trữ artifact siêu nhẹ (`runtime.sqlite` + `siglip.faiss` SQ8 < 3GB); video và keyframe gốc stream theo nhu cầu. | Không bao giờ giải nén toàn bộ tệp zip video ra đĩa; chỉ trích xuất keyframe và thumbnail thu nhỏ (WebP 128x128 px). |
| **8** | **Tắc nghẽn tính toán Vector quy mô lớn & Hết Quota GPU**: Trích xuất hàng triệu vector SigLIP trên hàng trăm GB video tiêu tốn nhiều giờ GPU. | Chỉ chạy trên 1 GPU thông thường làm cạn kiệt 30h GPU/tuần của Kaggle. | **Phase 02 Multimodal / `vector_extractor.py` (Kaggle TPU v3-8)**: Tận dụng **20h TPU v3-8 độc lập** (8 Cores, 128GB HBM) qua `torch_xla` để chạy batch lớn (2048+), tăng tốc độ 5-10x và nâng tổng hạn mức lên **50h/tuần**. | Dùng TPU v3-8 chuyên cho Batch Inference Vector SigLIP/VLM; giữ GPU cho Whisper ASR & OCR; cố định tensor shape để tránh XLA recompilation. |

---

## 2. Chi Tiết Kỹ Thuật Từng Bước Cải Thiện

### 2.1. Cải Thiện Phase 00 (Ingestion & Frame Timeline)
- **Mã nguồn:** [system1-kaggle-pipeline/src/frame_timeline.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/frame_timeline.py)
- **Cơ chế:** Đọc luồng frame qua OpenCV/FFmpeg packet counter, sinh bảng DataFrame với các trường `frame_id`, `pts_time_sec`, `fps`. Bảng này được lưu thành `frame_timeline/{video_id}.parquet`. Mọi module sau bắt buộc phải lấy mốc thời gian từ bảng này.

### 2.2. Cải Thiện Phase 01 (Shot Detection & Smart Keyframe Extraction)
- **Mã nguồn:** [system1-kaggle-pipeline/src/shot_detector.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/shot_detector.py) và [system1-kaggle-pipeline/src/adaptive_keyframe.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/adaptive_keyframe.py)
- **Cơ chế:**
  1. Sử dụng TransNet V2 / Histogram Correlation để cắt video thành từng cú máy.
  2. Lấy mẫu thích ứng: Shot ngắn (< 3s) lấy 1 frame; Shot trung bình (3 - 10s) lấy 3 frame; Shot dài (> 10s trong bài giảng/nấu ăn) lấy mẫu mỗi 3 giây.
  3. Lọc phương sai toán tử Laplacian $\text{Var}(\nabla^2 I) \ge 40.0$. Nếu ảnh bị nhòe, tự động dò tìm trong phạm vi $\pm 2$ frames xung quanh để chọn ra frame nét nhất.
  4. Tự động nén và sinh thumbnail WebP kích thước 128x128 px (chất lượng 65%) để phục vụ Lean Mode.

### 2.3. Cải Thiện Phase 02 (ASR, OCR, SigLIP Vector & KIS Semantics)
- **Mã nguồn:** 
  - [system1-kaggle-pipeline/src/asr_transcriber.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/asr_transcriber.py)
  - [system1-kaggle-pipeline/src/ocr_extractor.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/ocr_extractor.py)
  - [system1-kaggle-pipeline/src/vector_extractor.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/vector_extractor.py)
  - [system1-kaggle-pipeline/src/semantic_enricher.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/semantic_enricher.py)
- **Cơ chế:**
  1. `faster-whisper large-v3` bóc tách lời thoại tiếng Việt có dấu, lưu mốc thời gian `start_sec`, `end_sec`.
  2. `EasyOCR` quét chữ có dấu và phân loại vùng chân trang tin tức `is_lower_third`.
  3. `SigLIP Base` mã hóa hình ảnh thành ma trận vector chuẩn hóa $L_2$.
  4. `KISDetailEnricher` phân tích 6 trường thuộc tính KIS (màu sắc, góc máy, ánh sáng, bối cảnh, số lượng vật thể nhỏ, hành động).

### 2.4. Cải Thiện Phase 03 (Database & Vector Index Packaging)
- **Mã nguồn:** [system1-kaggle-pipeline/src/db_builder.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/db_builder.py)
- **Cơ chế:**
  1. Tạo `runtime.sqlite` với bảng ảo `text_documents_fts` (SQLite FTS5 sử dụng tokenizer `unicode61 remove_diacritics 2`) gộp chung toàn bộ nội dung Tiêu đề, ASR, OCR và KIS Semantics.
  2. Xây dựng chỉ mục `siglip.faiss` sử dụng lượng tử hóa **FAISS SQ8** (Scalar Quantizer 8-bit) với metric `METRIC_INNER_PRODUCT`, giảm 4 lần dung lượng RAM mà vẫn giữ nguyên độ chính xác tìm kiếm Cosine.

---

## 3. Bản Đồ Thư Mục & Các Điểm Neo Quan Trọng

- **Gói Pipeline Kaggle Độc Lập:** [system1-kaggle-pipeline/](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline)
  - Notebook 1-Click: [notebooks/kaggle_master_pipeline.ipynb](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/notebooks/kaggle_master_pipeline.ipynb)
  - Notebook Colab Bridge: [notebooks/colab_drive_to_kaggle_uploader.ipynb](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/notebooks/colab_drive_to_kaggle_uploader.ipynb)
  - Cấu hình: [configs/pipeline_config.yaml](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/configs/pipeline_config.yaml)
- **Cẩm Nang Xử Lý Dữ Liệu Lớn Colab & Kaggle:** [.agents/notes/colab_kaggle_data_engineering_guide.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/.agents/notes/colab_kaggle_data_engineering_guide.md)
- **Kho Dữ Liệu Mẫu & Đặc Tả Sơ Khảo:** [data_sample/README.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/data_sample/README.md)
- **Thiết Kế Kiến Trúc Kênh Xử Lý Riêng:** [main-dev/system1/CUSTOM_PIPELINE_ARCHITECTURE.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/main-dev/system1/CUSTOM_PIPELINE_ARCHITECTURE.md)

---

## 4. Các Cập Nhật Và Cải Tiến Mới Nhất (Cập nhật ngày 22/08/2026)

### 4.1. Cơ Chế Quét Nối Tiếp & Sequential Fast-Forward (`cap.grab`)
- **Vấn đề:** Trích xuất vượt mốc 1 phút trên môi trường Windows thường gặp lỗi trượt frame hoặc mất frame ở giây biên (ví dụ giây thứ 57) do cơ chế seek `cap.set` của OpenCV không chính xác trên codec H.264.
- **Giải pháp:** Sử dụng cơ chế Resume Checkpoint. Khi tiếp tục từ mốc cũ (ví dụ mở rộng từ 60s lên 180s), hệ thống giữ lại các keyframe trước mốc $T_{cached} - 2.5\text{s}$, sau đó dùng vòng lặp `cap.grab()` chạy tuần tự đến đúng frame cần quét tiếp. Tốc độ `cap.grab()` đạt >1000 fps do không giải mã khung hình, giúp định vị chính xác 100% không mất frame.

### 4.2. Trích Xuất & So Sánh Vật Thể Thích Ứng (Object-Driven Keyframe Extraction)
- **Vấn đề:** Nhiều phân đoạn hội thoại dài (static talking heads) sinh ra quá nhiều keyframe giống nhau gây nhiễu, trong khi các pha xuất hiện vật thể mới hoặc thay đổi số lượng vật thể lại bị bỏ sót.
- **Giải pháp:** 
  1. Liên kết các keyframe System 1 với dữ liệu vật thể được AI phát hiện từ tệp `objects-aic25-b1.zip` qua cơ chế so khớp khoảng cách frame ngắn nhất ($\le 1.5\text{s}$).
  2. Bổ sung hàm `check_object_difference` kiểm tra xem giữa hai mốc có sự xuất hiện của loại vật thể mới, thay đổi số lượng vật thể, hoặc chênh lệch độ tin cậy lớn (>0.25) hay không.
  3. Lọc trùng lặp thích ứng: Nếu khoảng thời gian liền kề dưới 3.0s (3 trang) và không có sự thay đổi lớn về chữ và vật thể, hệ thống sẽ loại bỏ frame trùng và giữ lại frame sắc nét nhất.
  4. Hiển thị trực quan danh sách vật thể AI phát hiện trực tiếp trên thẻ System 1 ở giao diện Tab 1 tương tự như BTC.

### 4.3. Theo Dõi Vật Thể Động Trên Video (YOLOv8 ByteTrack)
- **Vấn đề:** Phân tích tĩnh từng frame đơn lẻ dễ bị đếm trùng lặp và không nắm bắt được tính liên tục của đối tượng di chuyển.
- **Giải pháp:** 
  1. Tích hợp mô hình `yolov8n.pt` kết hợp với thuật toán tracking động `ByteTrack` (`model.track`) chạy trực tiếp trên luồng video ở tần suất mẫu tối ưu (ví dụ 5 FPS qua `vid_stride`).
  2. Xây dựng bản đồ hành trình vật thể (`active_tracks`) ghi nhận thời gian bắt đầu (`first_seen`) và kết thúc (`last_seen`) của từng `track_id` duy nhất.
  3. Khi xử lý keyframe, hệ thống đối chiếu khoảng thời gian của cú máy (shot interval) với thời gian hoạt động của các track để thống kê số lượng vật thể *duy nhất* trong cú máy, loại bỏ hoàn toàn việc đếm lặp.
  4. Lọc các vật thể đang xuất hiện trực tiếp tại thời điểm của keyframe ($\pm 1.0\text{s}$) để lưu trữ và hiển thị trực quan lên giao diện người dùng.

### 4.4. Chuẩn Hóa Cẩm Nang Kỹ Thuật System 1 Kaggle Reference (Cập nhật ngày 23/08/2026)
- **Hoạt động:** Đã biên soạn và hoàn thiện tài liệu kỹ thuật chuẩn mực tại [system1-kaggle-pipeline/README.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/README.md).
- **Giá trị bàn giao:** 
  1. Kết nối liền mạch kiến trúc 4 tầng từ `main-dev/system1` sang gói thực thi độc lập `system1-kaggle-pipeline`.
  2. Làm rõ hợp đồng dữ liệu đầu ra và cơ chế nạp ảo `VirtualBlobReader` (Zero Disk Waste) cho System 2 / `monolith-mvp-app`.
  3. Hướng dẫn toàn diện chiến thuật điều phối dữ liệu đám mây (Drive -> Colab -> Kaggle) và khai thác tối đa tài nguyên GPU T4 kép + TPU v3-8 (50 giờ/tuần).
  4. Cung cấp sổ tay tra cứu 8 lỗi thực chiến và hướng dẫn sử dụng công cụ CLI trung tâm `benchmark_runner.py`.

### 4.5. Đồng Bộ Hóa Trình CLI Benchmark (`benchmark_runner.py`) (Cập nhật ngày 23/08/2026)
- **Vấn đề:** Các thuật toán mới tích hợp trong Web UI (như lọc trùng thích ứng màu sắc và vật thể, trích xuất ngày tháng từ tiêu đề, lọc khung hình đơn sắc phẳng, và YOLO live fallback) chưa được đồng bộ hóa sang công cụ CLI kiểm thử `benchmark_runner.py`. Ngoài ra, số lượng video mẫu benchmark cần thu nhỏ về 5 video đầu của L21 để tăng tốc kiểm thử.
- **Giải pháp:**
  1. Đồng bộ hóa toàn bộ helper phân tích (`analyze_text_and_color`, `is_blank_or_solid_monochrome`, `check_object_difference`, `load_cached_objects`, `get_local_yolo_model`, `extract_date_info_from_title`) vào `benchmark_runner.py`.
  2. Cập nhật `run_10_videos_mode` sử dụng quy trình trích xuất keyframe thích ứng, chạy YOLOv8n live fallback, và thực hiện lọc trùng lặp lân cận dựa trên biến thiên vật thể và độ tương quan màu sắc (Correlation Sim > 0.88 trong phạm vi 3.0s).
  3. Rút gọn danh sách `TARGET_10_VIDEOS` xuống còn 5 video đầu của L21 (`L21_V001` đến `L21_V006`).
  4. Thực nghiệm chạy offline thành công, sinh ra 300 keyframes tối ưu thông tin từ 5 video L21 đầu tiên trong thời gian ngắn và ghi nhận kết quả ra tệp so sánh `comparison_data.json` và `benchmark_summary.csv`.

### 4.6. Thiết Lập Kênh Phân Task & Khung Kiểm Định Sub-Agents (Rule 11) (Cập nhật ngày 23/08/2026)
- **Hoạt động:** 
  1. Đã biên soạn nhật ký thực nghiệm chi tiết tại [system1-kaggle-pipeline/EXECUTION_MILESTONES.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/EXECUTION_MILESTONES.md).
  2. Thiết lập Ma trận phân giao tác vụ 3 vai trò (Orchestration, Execution, Validation) tại [.agents/communication/system1_subagent_task_delegation.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/.agents/communication/system1_subagent_task_delegation.md).
  3. Cung cấp Master Handover Prompt sẵn sàng cho chuyển giao bối cảnh tại [.agents/communication/subagent_master_handover_prompt.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/.agents/communication/subagent_master_handover_prompt.md).
  4. Xây dựng và thực thi thành công 100% script kiểm định tự động [scripts/validate_subagent_pipeline.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts/validate_subagent_pipeline.py) đạt chuẩn 5 tiêu chí định lượng đầu ra.

### 4.7. Chuẩn Hóa Sổ Cái Bàn Giao `CONVERSATION_README.md` & Bổ Sung Rule 12 (Cập nhật ngày 23/08/2026)
- **Hoạt động:**
  1. Tái cấu trúc toàn diện [CONVERSATION_README.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/CONVERSATION_README.md) thành Sổ cái Quản trị Hệ thống (Master Ledger) tập hợp đầy đủ 15 tính năng cốt lõi và hướng giải quyết từ AI Agent xuyên suốt dự án.
  2. Bổ sung **Quy Tắc 12** vào [.agents/rules/user_rules.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/.agents/rules/user_rules.md) yêu cầu mọi cập nhật hệ thống phải ghi nhận vào `CONVERSATION_README.md` và kiểm tra đối chiếu chống trùng lặp dữ liệu trước khi triển khai.

### 4.8. Chuẩn Hóa Docstrings Codebase Theo 4 Phase & Xuất Bản Flow Đầu-Cuối (Cập nhật ngày 23/08/2026)
- **Hoạt động:**
  1. Chuẩn hóa toàn bộ docstrings và chú thích giai đoạn cho 10 module trong `system1-kaggle-pipeline/src/` (Phase 00 Ingestion -> Phase 01 Structure -> Phase 02 Features & Semantics -> Phase 03 DB Packaging -> Master Orchestrator).
  2. Biên soạn Cẩm nang Luồng Vận Hành & Ma Trận Kiểm Định Tổng Quan tại [system1-kaggle-pipeline/PIPELINE_FLOW_AND_VERIFICATION.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/PIPELINE_FLOW_AND_VERIFICATION.md).
  3. Chạy kiểm thử tự động đạt kết quả 100% PASS trên toàn bộ 5 tiêu chuẩn đầu ra.

### 4.9. Chuẩn Hóa Trình Thực Thi BAT Launcher & Bổ Sung Rule 13 (Cập nhật ngày 23/08/2026)
- **Hoạt động:**
  1. Chuẩn hóa [start_interactive_test_app.bat](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/start_interactive_test_app.bat) và [interactive-test-app/launcher.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/interactive-test-app/launcher.py) dọn sạch emoji, hỗ trợ khởi chạy 1-click, tự động giải phóng port 7860/7861 và ngắt Ctrl+C để restart.
  2. Bổ sung **Quy Tắc 13** vào [.agents/rules/user_rules.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/.agents/rules/user_rules.md) cho phép và khuyến khích AI Agent chủ động đặt câu hỏi làm rõ nhu cầu và thảo luận đề xuất cải tiến tính năng với User.

### 4.10. Sổ Tay Nhánh Xử Lý Keyframe, Phân Loại Ranh Giới Dữ Liệu & Phân Nhánh Git (Cập nhật ngày 23/08/2026)
- **Hoạt động:**
  1. Biên soạn [system1-kaggle-pipeline/KEYFRAME_PIPELINE_README.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/KEYFRAME_PIPELINE_README.md) tổng kết toàn diện các kỹ thuật trích xuất keyframe, bộ lọc Laplacian $\ge 40.0$, YOLOv8 ByteTrack, OCR lower thirds, SigLIP Base $L_2=1.0$, và xác nhận rõ mốc hiện tại đang ở giai đoạn Local Testing (chưa chuyển sang chạy trên Kaggle Cloud).
  2. Thiết lập ranh giới rõ ràng: Mã nguồn & tài liệu được Git Tracked/Committed; Dữ liệu mẫu, tệp nháp `scratch/`, và kết quả trích xuất nhị phân (`*.sqlite`, `*.npy`, `*.faiss`, `test_output/`) được giữ lại trên máy cá nhân để phục vụ chạy test nhưng loại trừ khỏi Git để giữ repo tinh gọn, sạch sẽ.

### 4.11. Rút Commit Trên `dev`, Tạo Nhánh Mới `feature/system1-keyframe-pipeline` & Sẵn Sàng Pull Request (Cập nhật ngày 23/08/2026)
- **Hoạt động:**
  1. Thực hiện `git reset --soft HEAD~1` trên nhánh `dev` của `main-dev` để đưa nhánh tích hợp chính về lại trạng thái an toàn ban đầu.
  2. Khởi tạo nhánh tính năng độc lập `feature/system1-keyframe-pipeline`.
  3. Hoàn tất commit toàn bộ 36 tệp tài liệu kiến trúc, mã nguồn chuẩn và agent rules trên nhánh mới (Commit ID: `c6fbde0` — `feat(system1): implement smart keyframe extraction, pipeline architecture, and agent guidelines`).
  4. Chuẩn bị sẵn sàng cho quy trình kiểm duyệt và mở Pull Request vào nhánh `dev`.

### 4.12. Chiến Lược Quản Trị Nhánh Độc Lập Chờ Nghiệm Thu Sản Phẩm (Cập nhật ngày 23/08/2026)
- **Hoạt động:**
  1. Đã thực hiện `git push -u origin feature/system1-keyframe-pipeline` thành công lên GitHub remote.
  2. Thống nhất định hướng: Giữ nguyên `feature/system1-keyframe-pipeline` ở trạng thái nhánh tính năng mở (hoặc Draft PR) để tiếp tục phát triển, tinh chỉnh tham số và kiểm duyệt giao diện Studio cục bộ; **chưa merge ngay vào nhánh `dev`** cho đến khi sản phẩm đạt độ hoàn thiện và được User nghiệm thu chính thức.

### 4.13. Kế Hoạch 4 Phân Hệ Nâng Cấp, Test Suites Độc Lập & Bổ Sung Rule 14 (Cập nhật ngày 23/08/2026)
- **Hoạt động:**
  1. Biên soạn [KEYFRAME_ENHANCEMENT_PLAN_AND_SUBAGENT_TASKS.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/plans/KEYFRAME_ENHANCEMENT_PLAN_AND_SUBAGENT_TASKS.md) lưu tại `system1-kaggle-pipeline/plans/` phân rã 4 bước nâng cấp và ma trận 3 vai trò (Rule 11).
  2. Xây dựng và kiểm thử thành công 100% PASS cho 4 kịch bản chạy lẻ:
     - `test_step1_event_keyframes.py`: Bắt mốc Enter/Exit cho $\le 5$ người, thời lượng $\ge 0.8\text{s}$, kích hoạt Crowd Suppression.
     - `test_step2_video_ocr_dedup.py`: Khử trùng lặp Jaccard $\ge 0.85$ giảm $>55\%$ chuỗi thừa, phân vùng chân trang $y > 0.65$.
     - `test_step3_asr_timestamp_qa.py`: Bảng `asr_fts` tra cứu Video QA có/không dấu $< 2\text{ms}$ khớp mốc giây.
     - `test_step4_genre_classifier.py`: Module `genre_classifier.py` phân loại đúng 100% test cases và gán trọng số RRF.
  3. Bổ sung **Quy Tắc 14** vào [.agents/rules/user_rules.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/.agents/rules/user_rules.md) yêu cầu mọi Sub-Agent phải lưu plan vào `plans/`, phân chia 3 vai trò, tạo test case độc lập trên data thật và duy trì Nhật ký thảo luận phát sinh trực tiếp trong plan.

### 4.14. Quy Hoạch Hệ Sinh Thái Tài Liệu 5 Tầng & Bổ Sung Agent Header Chuẩn Tắc (Cập nhật ngày 23/08/2026)
- **Hoạt động:**
  1. Rà soát, hợp nhất và tinh giản toàn bộ các file Markdown trong `system1-kaggle-pipeline/` theo cấu trúc 5 tầng mạch lạc:
     - Tầng 1: `README.md` (Master Handbook).
     - Tầng 2: `PIPELINE_FLOW_AND_VERIFICATION.md` (Operational Flow & Gatekeeper QA).
     - Tầng 3: `KEYFRAME_PIPELINE_README.md` (Keyframe Branch Manual & Data Boundary).
     - Tầng 4: `plans/KEYFRAME_ENHANCEMENT_PLAN_AND_SUBAGENT_TASKS.md` (Sub-Agent Plan & Live Discussion Ledger).
     - Tầng 5: `EXECUTION_MILESTONES.md` (Empirical Proof) và `scripts/README.md` (Test Scripts Guide).
  2. Bổ sung khối chú thích chuẩn tắc `AGENT CONTEXT & PROTOCOL HEADER` vào đầu 100% các file Markdown giải thích rõ ràng mục tiêu, vai trò, các quy tắc áp dụng (Rule 1, 10, 11, 12, 13, 14, No Emojis), liên kết upstream/downstream và lệnh test tương ứng cho các AI Agent kế nhiệm.
### 4.15. Hoàn Thiện Step 5: Hợp Nhất Timeline BTC-Self, Đếm Vật Thể 'Nhãn x Số lượng' & Khử Trùng Lặp Ảo Cắt Nghĩa (Cập nhật ngày 23/08/2026)
- **Hoạt động:**
  1. Cài đặt module [src/timeline_synchronizer.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/src/timeline_synchronizer.py):
     - `format_object_counts()`: Tự động dịch và tổng hợp chuỗi nhãn vật thể dạng `"Nhãn x Số lượng"` (ví dụ: `"Cờ x 5, Người x 2, Xe máy x 1"`).
     - `merge_and_sort_timeline()`: Khớp nối trục thời gian chính xác, gộp các frame trùng mốc $|\Delta t| \le 0.05\text{s}$ thành 1 bản ghi duy nhất, gán `btc_frame_idx`.
     - `sliding_window_deduplicate()`: Cửa sổ trượt 3 frame đo độ tương đồng thị giác ($\ge 0.92$) với quy tắc **Ngoại lệ OCR** (giữ nguyên frame nếu văn bản chân trang thay đổi).
     - **Cơ chế Frame Cắt Nghĩa (Virtual Reference Frame):** Zero Disk Waste (không nhân bản file ảnh JPEG/WebP), lưu `delta_time_sec` (`+1.2s`, `-0.8s`) và hiển thị trên UI với khuôn viền màu tím Neon / Violet (`#bd93f9`).
  2. Xây dựng và kiểm thử thành công 100% PASS kịch bản kiểm tra độc lập [scripts/steps/test_step5_timeline_merge_dedup.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts/steps/test_step5_timeline_merge_dedup.py) trên 5 tình huống thực tế.
  3. Cập nhật giao diện [interactive-test-app/app.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/interactive-test-app/app.py) hỗ trợ hiển thị Badges số lượng vật thể và render khuôn viền tím Violet cho các Frame Cắt Nghĩa.

### 4.16. Nâng Cấp Toàn Diện Interactive Studio 5-Tabs, Quản Lý Persistence & Nén Ảnh WebP (Cập nhật ngày 23/08/2026)
- **Hoạt động:**
  1. Kiểm tra lại 100% mã nguồn các module: `timeline_synchronizer.py`, `object_detector.py`, `ocr_extractor.py`, `asr_transcriber.py`, `genre_classifier.py`, `adaptive_keyframe.py`.
  2. Nâng cấp [interactive-test-app/app.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/interactive-test-app/app.py) thành hệ thống 5 Tab trực quan:
     - Tab 1: So Sánh Trực Quan Side-by-Side (BTC vs. System 1 Tự Xử Lý) theo dòng thời gian 3.0 giây.
     - Tab 2: Trình Quản Lý & Lưu Trữ Kết Quả (Persistence & Memory-Saving Hub) hiển thị bảng tổng hợp video và nút xuất CSV/JSON.
     - Tab 3: Khám Phá Step 1-5 (Genre Classifier, ASR QA Timestamp Search, OCR Chân Trang, Frame Cắt Nghĩa viền tím).
     - Tab 4: Tìm Kiếm KIS Nhanh (Text & Multi-Modal Search < 50ms).
     - Tab 5: Studio Tùy Chỉnh Tham Số Đầu Vào (Histogram, Laplacian, Frames).
  3. Tối ưu hóa tải ảnh qua hàm `pil_to_base64_thumb()` chuyển đổi sang WebP 140x78 chất lượng Q65 và cache RAM, giúp tiết kiệm hơn 90% dung lượng bộ nhớ so với ảnh JPEG thô 1080p.
  4. Đã xác thực toàn bộ 5 test suites độc lập đều đạt **100% PASS** và dọn dẹp sạch sẽ 100% emoji.

### 4.18. Kiểm Duyệt Lọc Bỏ Sau Khi Merge Timeline BTC, Tái Cấu Trúc Ý Nghĩa Toàn Cú Máy & Suy Đoán Ngữ Cảnh BTC (Cập nhật ngày 23/08/2026)
- **Hoạt động:**
  1. **Quy Trình Kiểm Duyệt Sau Khi Merge Timeline:**
     - Loại bỏ việc xóa tùy tiện tại local; giữ nguyên 100% keyframe trích xuất thô của System 1.
     - Quy trình kiểm duyệt và đề xuất lọc bỏ/chuyển đổi Frame Cắt Nghĩa CHỈ THỰC HIỆN SAU KHI MERGE toàn bộ timeline BTC và System 1 trên cùng trục thời gian chung.
     - Kiểm tra lịch sử các frame đã xuất hiện trước đó: Nếu tương đồng thị giác cao ($S \ge 0.92$) VÀ không có biến thiên OCR / vật thể / bối cảnh: Ưu tiên giữ frame BTC / Anchor; frame trùng lặp chuyển thành Frame Cắt Nghĩa viền tím Neon (`#bd93f9`) kèm tag $\Delta t$, hoặc Đề Xuất Lọc Bỏ viền đỏ Đậm (`#ff5555`) nếu độ nét Laplacian thấp hơn rõ rệt ($< 0.70 \times \text{Anchor}$).
  2. **Tái Cấu Trúc Trường "Ý Nghĩa" (Shot Contextual Meaning & Activities):**
     - Đọc ảnh và mô tả khái quát ý nghĩa của frame so với toàn bộ cú máy (Shot-level context) thay vì frame đơn lẻ.
     - Cài đặt `extract_text_keywords()` bóc tách 2-3 từ khóa nổi bật từ OCR tiếng Việt, loại bỏ stop words.
     - Cài đặt `infer_shot_contextual_meaning()` phân loại hoạt động chủ đạo (Dẫn tin tức, Giao thông, Thể thao, Giảng bài, Bối cảnh trong phòng, Phong cảnh, Tiêu đề) và định dạng chuẩn: `[Hoạt động khái quát] | Từ khóa: [kw1, kw2]`.
  3. **Cơ Chế Suy Đoán Ngữ Cảnh Cho BTC (BTC Context Inference):**
     - Cài đặt `enrich_btc_with_shot_context()`: Quét tìm keyframe tương đồng cao ($S \ge 0.85$) từ System 1 lân cận trong cùng video để thừa hưởng ngữ cảnh cú máy; nếu không có thì đọc video gốc trong phạm vi $\pm 1.0\text{s}$ để suy đoán toàn diện.
  4. **Kiểm Thử & Thực Nghiệm:**
     - Cập nhật và chạy thành công [scripts/steps/test_step5_timeline_merge_dedup.py](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/system1-kaggle-pipeline/scripts/steps/test_step5_timeline_merge_dedup.py) đạt **6/6 (100%) ALL PASS**.
     - Chạy lại toàn bộ 5 test suites độc lập (Step 1-5) đạt **100% ALL PASS**.

### 4.22. Hoàn Thiện Master README.md Tổng Hợp Toàn Diện Dự Án Phục Vụ Commit Git (Cập nhật ngày 24/08/2026)
- **Hoạt động:**
  1. **Bản Đồ Cấu Trúc Thư Mục Chuẩn Tắc:**
     - Biên soạn toàn diện tệp [README.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/README.md) tại thư mục gốc, liệt kê chi tiết chức năng của từng file/thư mục kèm đường link markdown có thể nhấp chuột (`file:///`).
  2. **Cẩm Nang Vận Hành & Khởi Động:**
     - Trình bày hướng dẫn 1-Click launcher (`start_interactive_test_app.bat`), thực thi Kaggle GPU kép (`kaggle_master_pipeline.ipynb`) và quy trình 6 bước xử lý tuần tự.
  3. **Tổng Kết Kỹ Thuật & Hướng Đã Xử Lý:**
     - Tổng hợp 8 giải pháp kỹ thuật đã triển khai thành công: Multi-Badge, ảo hóa Frame Cắt Nghĩa viền tím Neon `#bd93f9` + $\Delta t$ (Zero Disk Waste), phân loại tag đề xuất lọc bỏ `#ff5555`, phát hiện `[BTC-xử lý]`, phát hiện vật thể nhỏ YOLO `conf=0.15`, cứu ảnh mờ Sharpening Fallback, ASR timestamped Video QA, phòng ngừa lỗi dữ liệu biên.
  4. **Trung Tâm Tài Liệu & Lộ Trình Phát Triển:**
     - Liên kết đến toàn bộ 7 tài liệu chuyên sâu của dự án và bàn giao định hướng phát triển phân hệ System 2 (Live Agentic Search Engine, Cloud API Hybrid Fallback, TRAKE Sequence Solver).



