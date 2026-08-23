---
trigger: always_on
---

# Quy Tắc Cá Nhân Của User (Personal User Rules)

## 1. Nguyên Tắc Trình Bày & Lên Kế Hoạch (Planning & Communication Rules)
- **Giải thích ở đầu mỗi mục lớn:** Ở đầu mỗi mục lớn, luôn giải thích rõ ràng mục tiêu và các bước đang/sẽ làm để User dễ dàng theo dõi.
- **Phân tích & Lên kế hoạch trước khi triển khai:** Trước khi thực hiện bất kỳ thay đổi mã nguồn hoặc triển khai thực nghiệm nào, phải thực hiện phân tích bài toán, giải thích cách làm và lập kế hoạch chi tiết để User duyệt trước khi bắt đầu viết code.

## 2. Quy Tắc Xử Lý Vấn Đề & Cập Nhật Thông Tin (Issue Handling & Freshness Rules)
- **Hỏi User khi gặp vấn đề hoặc thông tin không rõ ràng:** Khi gặp lỗi, câu hỏi quá tổng quát, hoặc thiếu thông tin/công nghệ mới nhất (tính đến mốc mảng nghiên cứu từ **tháng 07/2026** trở đi), PHẢI chủ động dừng lại và đặt câu hỏi hỏi User để User tra cứu.
- **Gợi ý Nguồn Tra Cứu & Yêu Cầu (Search Suggestions & Requirements):** Khi đặt câu hỏi cho User, phải gợi ý rõ:
  1. Các từ khóa tìm kiếm (Keywords).
  2. Nguồn tra cứu khuyến nghị (Hugging Face Hub, arXiv, Papers With Code, GitHub Releases, Official Documentation).
  3. Các yêu cầu thông tin cần đảm bảo (Tính mới, Benchmark mới nhất, Khả năng tương thích).

## 3. Quy Tắc Yêu Cầu Mô Hình Cấp Cao & Đánh Giá Chéo (Model Escalation & Cross-Validation Rules)
- **Đề xuất nâng cấp Mô hình AI Agent khi cần:** Khi gặp tác vụ phức tạp (thiết kế kiến trúc nâng cao, tối ưu code thuật toán khó, prompt kỹ thuật sâu), AI Agent được phép chủ động kiến nghị User chuyển đổi sang các mô hình cấp cao hơn (VD: Gemini 3.1 Pro High, Claude 3.5 Sonnet, GPT-4o) để đảm bảo chất lượng công việc tốt nhất.
- **Đề xuất Cross-Validation (Kiểm thử chéo):** Đối với các quyết định thiết kế quan trọng, xây dựng prompt VLM hay đối chiếu benchmark, AI Agent nên gợi ý User tham khảo/kiểm thử chéo qua các mô hình khác (Claude, GPT, Gemini) để thông tin đạt tính chuẩn xác và đa chiều.
- **Tích hợp Translation API cho Query Input:** Đã chốt phương án dịch câu truy vấn từ Tiếng Việt sang Tiếng Anh qua API (ví dụ: Google Translate API / DeepL / LLM Translation API) trước khi đưa vào mô hình Embedding để đảm bảo thông tin và tăng độ chính xác tìm kiếm.

## 4. Tối Ưu Tốc Độ Truy Vấn & Sub-Agent Cải Tiến Prompt (Speed & Prompt Optimization Rules)
- **Ưu tiên Tốc độ Truy vấn Trực tiếp (Live Low-Latency Search):** 
  - Toàn bộ các công đoạn nặng (VLM captioning, OCR, Object Detection, Indexing) PHẢI thực hiện ở bước **Offline Pre-processing**.
  - Khi thi trực tiếp (Live Query), mô hình và pipeline phải siêu nhẹ (Lightweight), ưu tiên chạy Local trên phần cứng giới hạn (CPU/GPU vừa phải) để tối ưu thời gian phản hồi (Latency < 200ms).
- **Sub-Agent Cải Tiến Prompt (Prompt Optimizer Sub-Agent):**
  - Xây dựng Sub-Agent / Local Rule Engine chuyên nhiệm vụ làm giàu, tối ưu và cấu trúc lại Prompt từ câu truy vấn của người dùng (đặc biệt chuẩn hóa các khái niệm thể thao, màu sắc, đối tượng).
  - **Xác nhận Prompt mới với User:** Mọi Prompt được cải tiến hoặc sinh ra bởi Sub-Agent bắt buộc phải hiển thị/xác nhận lại với User trước khi gọi tìm kiếm chính thức.

## 5. Kiến Trúc Song Song Hybrid Local + Cloud API (Dual-Stream Execution Rules)
- **Tận dụng mạng trong cuộc thi:** Khi được dùng Internet, hệ thống triển khai theo mô hình Hybrid song song để kết hợp ưu thế của cả Local và Cloud API:
  - **Stream A (Local Model - Fast Path):** Chạy SigLIP Base / FAISS tại Local. Phản hồi tức thì (< 100ms) để người dùng xem trước khung hình sơ bộ.
  - **Stream B (Cloud API Model - High Accuracy Path):** Gọi Gemini 3.1 Pro / GPT-4o / Claude API song song để tối ưu Prompt nâng cao, dịch chính xác ngữ cảnh thể thao và re-rank lại kết quả top K (< 1-2s) với điểm số tối đa.
  - **Cơ chế Fallback:** Nếu mạng chập chờn hoặc API bị timeout, hệ thống tự động sử dụng kết quả Stream A (Local) làm đáp án an toàn mà không làm gián đoạn cuộc thi.

## 6. Nhật Ký Giao Tiếp & Chuyển Nhượng Bối Cảnh (Communication & Model Handover Rules)
- **Ghi nhật ký giao tiếp vào thư mục `.agents/communication/`:**
  - AI Agent bắt buộc phải khởi tạo và duy trì các file log chuyển nhượng bối cảnh tại `.agents/communication/`.
  - Mọi mốc quan trọng (Milestones), yêu cầu từ User, các công việc đã hoàn thành, cùng cấu trúc prompt/kiến trúc đã thống nhất phải được ghi nhận rõ ràng.
- **Định dạng sẵn sàng cho Handover giữa các Model AI:**
  - File nhật ký phải được định dạng chuẩn hóa (System Prompt / Context Summary) để User có thể copy-paste nguyên văn chuyển sang các AI Agent khác (Gemini, ChatGPT, Claude) bất cứ lúc nào để tiếp tục công việc hoặc thực hiện Cross-Validation mà không làm mất bối cảnh.

## 7. Tương Tác Con Người & Kiểm Duyệt Nhanh (Human-in-the-Loop Interactive Rules)
- **Thiết kế chuẩn Interactive Cockpit (VBS / LSC Style):** Cuộc thi AIC **HOÀN TOÀN CHO PHÉP và KHUYẾN KHÍCH** sự tương tác của con người. Tối ưu giao diện Web UI để mắt người lướt duyệt nhanh (Skimming grid), rê chuột xem trước video (Hover Preview), mở dòng thời gian lân cận (Timeline Slider), và thực hiện Image-to-Image Search / Negative Filtering ngay trên UI.

## 8. Giao Tiếp và Xác Nhận Trước Khi Thực Thi
- **Bắt buộc giải thích trước:** Phải thông báo khái quát các bước dự định làm và YÊU CẦU User xác nhận đồng ý trước khi chạy bất kỳ lệnh / script thực thi nào.

## 9. Quy Chuẩn Viết Code (Cloud & Documentation)
- **Tối ưu hóa Cloud:** Hỗ trợ Dual GPU (DataParallel) và TPU (PyTorch-XLA), kèm DEBUG_MODE = True/False.
- **Tài liệu hóa chuyên nghiệp:** Trong mọi file code (.py, .ipynb) phải có hướng dẫn sử dụng.
- **Handover Notes:** Bắt buộc lưu tiến độ vào thư mục `.agents/notes/handover_log.md` để Agent đi sau dễ tiếp quản.

## 10. Nguyên Tắc Bất Khả Xâm Phạm Của Rules (Append-Only Rule)
- **Tuyệt đối không xóa:** Khi cập nhật file `user_rules.md` hoặc bất kỳ file cấu hình luật nào, Agent CHỈ ĐƯỢC PHÉP THÊM (Append) luật mới. Tuyệt đối KHÔNG ĐƯỢC xóa bỏ, thay đổi ý nghĩa, hay rút gọn các luật đã có sẵn của User.

## 11. Quy Tắc Phân Mảnh Tác Vụ & Giao Việc Cho AI Agent Khác (Task Fragmentation & Model Delegation Rules)
- **Hệ Thống Phân Giao Công Việc (Task Delegation Matrix):** Khi chia nhỏ dự án thành các module độc lập để triển khai song song hoặc giao việc cho mô hình AI khác (Gemini, Claude, GPT), Agent phải phân tách công việc rõ ràng theo cấu trúc:
  1. **Mục tiêu của Module (Module Objective):** Xác định đầu vào (inputs), đầu ra (outputs) và các ràng buộc dữ liệu.
  2. **Yêu cầu Kiến trúc & Thuật toán (Architecture & Algorithm):** Định nghĩa rõ các thư viện được sử dụng, luồng dữ liệu (data flow) và cấu trúc cơ sở dữ liệu nếu có.
  3. **Ràng buộc hiệu năng & Latency (Latency & Resource Constraints):** Quy định rõ giới hạn phần cứng (GPU/CPU/Memory) và tốc độ phản hồi.
  4. **Kế hoạch kiểm thử & Minh chứng thực nghiệm (Verification & Empirical Evidence):** Chỉ ra cách chạy file test độc lập để xác thực kết quả đầu ra.
- **Tính Độc Lập Giữa Các Hạng Mục:** Mỗi mảnh tác vụ (fragment) sau khi được phân chia phải đảm bảo có thể chạy và kiểm thử độc lập mà không cần phụ thuộc vào toàn bộ hệ thống lớn đang chạy, giúp việc tích hợp sau này diễn ra trơn tru.
- **Ràng Buộc Hợp Đồng Dữ Liệu (Data Contract Constraints):** Các module do các Sub-Agent khác nhau phát triển phải giao tiếp qua cấu trúc JSON/Dict chuẩn hóa. Nghiêm cấm việc thay đổi cấu trúc dữ liệu đầu ra mà không có sự thống nhất chung, giúp đảm bảo tính tương thích và khả năng thay thế linh hoạt (Plug-and-Play) của từng module.
- **Mô Hình Quản Trị Ba Vai Trò (Three-Role Agent Framework):** Mỗi tài liệu phân mảnh tác vụ lớn bắt buộc phải định nghĩa rõ nhiệm vụ của 3 loại Agent sau:
  1. **Agent Quản Lý Phân Mục (Orchestration Agent):** Chịu trách nhiệm kết nối, điều phối dữ liệu đầu vào/đầu ra, xử lý các trường hợp lỗi (fault-tolerance), và tích hợp module vào hệ thống lớn.
  2. **Agent Thực Hiện (Execution Agent):** Tập trung viết mã nguồn, tối ưu hóa thuật toán và thư viện sử dụng để đáp ứng các ràng buộc hiệu năng.
  3. **Agent Kiểm Duyệt (Validation Agent):** Chịu trách nhiệm chạy các kịch bản kiểm thử độc lập, đối chiếu hợp đồng dữ liệu JSON, và đánh giá hiệu năng/Latency dựa trên các tiêu chí định lượng đã định sẵn.

## 12. Quy Tắc Đồng Bộ Hóa Sổ Cái Bàn Giao & Kiểm Tra Trùng Lặp (`CONVERSATION_README.md`)
- **Cập nhật bắt buộc vào Sổ cái trung tâm:** Khi có bất kỳ cập nhật nào về tính năng mới, thay đổi xử lý hệ thống, cải tiến thuật toán, hoặc tiến độ bàn giao, AI Agent BẮT BUỘC phải cập nhật thông tin tương ứng vào tệp [CONVERSATION_README.md](file:///c:/Nhat_Code/aio/project/AIC/Multimodal-Agentic-Retrieval-Engine/CONVERSATION_README.md).
- **Rà soát chống trùng lặp (Deduplication Check):** Trước khi đề xuất hướng giải quyết hoặc thêm thông tin mới, Agent PHẢI chủ động rà soát các mục gần đây trong `CONVERSATION_README.md` để kiểm tra xem vấn đề đã được xử lý hay chưa, tránh việc triển khai lặp lại hoặc làm mâu thuẫn các quyết định kiến trúc đã thống nhất với User.

## 13. Quy Tắc Chủ Động Đặt Câu Hỏi Làm Rõ & Thảo Luận Nâng Cấp Tính Năng (Proactive Clarification & Collaborative Ideation Rule)
- **Khuyến khích chủ động hỏi làm rõ:** Khi nhận yêu cầu mới từ User, nếu thấy bài toán có nhiều hướng tiếp cận, có điểm chưa tối ưu hoặc thiếu chi tiết kỹ thuật, AI Agent ĐƯỢC PHÉP và ĐƯỢC KHUYẾN KHÍCH chủ động đặt câu hỏi đa chiều để làm rõ nhu cầu của User.
- **Thảo luận đề xuất cải tiến (Collaborative Ideation):** AI Agent chủ động đề xuất các ý tưởng tối ưu hóa tính năng, gợi mở các kiến trúc cải tiến hoặc công nghệ mới hơn, và cùng thảo luận, bàn luận định hướng với User trước hoặc trong quá trình triển khai để đạt hiệu quả cao nhất.

## 14. Quy Tắc Quản Trị Kế Hoạch & Nhật Ký Thảo Luận Kỹ Thuật Sub-Agent (Sub-Agent Plan Governance & Collaborative Discussion Tracking Rule)
- **Lưu trữ kế hoạch vào thư mục module (`plans/`):** Mọi kế hoạch triển khai, phân rã tác vụ và nâng cấp hệ thống bắt buộc phải được lưu trữ thành file Markdown chính thức trong thư mục `plans/` của từng phân hệ (ví dụ: `system1-kaggle-pipeline/plans/`).
- **Phân mục từng bước & Soạn Test Case độc lập từ dữ liệu thật:** Kế hoạch phải chia nhỏ từng bước (Step), phân định rõ 3 vai trò (Orchestration, Execution, Validation), và xây dựng các file kiểm thử chạy lẻ (`scripts/steps/test_step*.py`) trên dữ liệu mẫu thực tế để kiểm chứng độc lập trước khi tích hợp vào pipeline lớn.
- **Cập nhật tình trạng, vấn đề và thảo luận phát sinh (Live Discussion Ledger):** Trong quá trình thực hiện, mọi vấn đề kỹ thuật phát sinh, thảo luận đa chiều giữa User và Agent, các phân tích ưu/nhược điểm cùng giải pháp đã thống nhất BẮT BUỘC phải được ghi nhận chi tiết vào mục *Nhật Ký Thảo Luận & Vấn Đề Phát Sinh* trực tiếp trong file Kế hoạch để các Sub-Agent và Agent tiếp theo luôn nắm trọn vẹn bối cảnh và lý do đưa ra các quyết định kiến trúc.



