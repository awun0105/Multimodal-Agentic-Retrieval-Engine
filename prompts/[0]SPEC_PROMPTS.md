# AI Challenge HCMC 2026 Multimedia Retrieval Assistant

Mình muốn xây dựng một hệ thống hỗ trợ tham gia cuộc thi AI Challenge HCMC 2026 với chủ đề:

> Intelligent Virtual Assistant for Advanced Analysis and Information Retrieval from Large-Scale Multimedia Data

Hệ thống được thiết kế theo hướng local-first, có thể chạy hoàn toàn trên một máy cá nhân hoặc một máy chủ nội bộ, đồng thời có thể publish qua LAN để nhiều thành viên trong đội truy cập bằng trình duyệt web.

## Mục tiêu chính

Xây dựng một trợ lý truy vấn multimedia hỗ trợ con người và agent tự động tìm kiếm thông tin trong tập dữ liệu lớn gồm raw video, keyframes, hình ảnh, âm thanh, transcript và metadata.

Hệ thống phải phục vụ cả:

* Interactive Mode (Human-in-the-loop)
* Automatic Agent Mode (Agent-in-the-loop)

và cả hai mode phải sử dụng chung retrieval core, search engine, evidence engine và data storage.

Không xây dựng hai hệ thống độc lập.

---

# Kiến trúc tổng thể

Yêu cầu sử dụng:

* Modular Monolith Architecture
* Clean Architecture
* Layered Architecture
* DDD-inspired Modules
* MVC cho Presentation Layer

Yêu cầu:

* Không cần Authentication
* Không phân chia role
* Không có nhiều dashboard khác nhau
* Chỉ có một Single Web UI dùng chung cho toàn đội

Hệ thống phải dễ chạy:

* Local machine
* Local GPU workstation
* Mini server nội bộ
* LAN deployment

Ưu tiên:

* Đơn giản
* Dễ debug
* Dễ bảo trì
* Ít dependency
* RAM-efficient
* SSD-efficient

---

# Hai hệ thống chính

## System 1: Preprocessing System

Mục tiêu:

Chuẩn bị toàn bộ dữ liệu trước khi truy vấn.

Input có thể bao gồm:

* Folder chứa Raw Video
* Folder chứa Keyframes
* Metadata (link youtube của video, description video, nguồn kênh, title video,...)
* Object Detection (file json)
* Clip Embeddings từ keyframes
* Các dữ liệu khác (chưa biết chắc)
chắc
System này chịu trách nhiệm:

### Data Ingestion

Import dữ liệu được cung cấp từ ban tổ chức (có thể là google drive).

### Data Processing

Sinh hoặc chuẩn hóa:

* Video Metadata
* Keyframe Metadata
* Timeline Metadata
* Captions (từ keyframes, từ video)
* OCR Text (từ keyframes)
* ASR Transcript (từ file âm thanh của video)
* Object Concepts (từ keyframes, từ video)
* Scene Tags (từ keyframes, từ video)
* các loại embedding (Text Embedding, Video Embedding, Audio Embedding, Object Embedding, ...)

### Index Building

Build:

* Metadata Database
* Vector Index
* Text Search Index

### Output

Sinh ra:

* Metadata DB
* Search Indexes
* Retrieval Assets

để System 2 sử dụng.

---

## System 2: Retrieval Assistant System

Đây là hệ thống chính sử dụng trong cuộc thi.

### Interactive Mode

Người dùng:

* nhập query
* nhập clue
* nhập notes
* thay đổi retrieval strategy
* thay đổi search mode
* filter kết quả
* duyệt keyframe, video, các keyframe lân cận
* đánh giá evidence
* lưu candidate

Hệ thống trả về:

* ranked keyframes
* ranked videos
* evidence
* metadata
* candidate outputs

### Automatic Agent Mode

Người dùng:

* nhập query hoặc chat với agent

Agent sẽ:

* phân tích query
* chọn retrieval strategy
* gọi retrieval tools
* gọi evidence tools
* thực hiện multi-step retrieval
* reranking
* refinement
* reasoning

Sau đó trả về:

* kết quả (ranked keyframes, ranked videos, evidence, metadata, candidate outputs, evidence)
Giải thích cho từng kết quả (có thể dùng LLM để giải thích).

và toàn bộ kết quả vẫn được hiển thị trong cùng hệ thống như Interactive Mode.

Agent không được xây dựng thành một hệ thống riêng biệt mà phải sử dụng lại toàn bộ retrieval core hiện có. Nghĩa là automatic mode là một agent làm các công việc end-to-end như con người làm.

---

# Loại truy vấn cần hỗ trợ

Hệ thống phải hỗ trợ:

### Textual KIS

Tìm video hoặc keyframe từ mô tả ngôn ngữ tự nhiên.

### Q&A

Tìm video hoặc keyframe và sinh câu trả lời.

### TRAKE

Tìm chuỗi sự kiện theo thời gian trong cùng video.

### VKIS / Video KIS

Tìm kiếm từ mô tả hình ảnh hoặc video do người vận hành quan sát và diễn đạt lại bằng text.

---

# UI Requirements

Single Page Application.

Các thành phần chính:

### Query Workspace

* Current Clue
* Accumulated Clues
* Selected Clues
* Notes

### Search Controls

* Search Mode
* Retrieval Strategy
* Filters
* Ranking Controls

### Results Grid

Hiển thị:

* Keyframes
* Similar Frames
* Ranked Results

### Detail View

Hiển thị:

* Keyframe lớn
* Metadata
* Evidence

### Same Video Explorer

Hiển thị:

* Các keyframe lân cận
* Timeline
* Context của video

### Evidence Panel

Hiển thị:

* Similarity Score
* Caption
* OCR
* ASR
* Objects
* Metadata
* Agent Reasoning (nếu có)

### Candidate Basket

Lưu các candidate tiềm năng cho từng query.

### Output Helper

Copy nhanh:

* video_id
* frame_id
* answer
* TRAKE frames
* CSV row

Export chỉ là helper và phải configurable.

---

# Data Storage

Ưu tiên:

### File Storage

* Videos
* Keyframes
* Thumbnails

### Metadata Database

Ví dụ:

* DuckDB
* SQLite

### Vector Search

Ví dụ:

* FAISS

### Text Search

Ví dụ:

* SQLite FTS
* Tantivy

Không ưu tiên:

* Elasticsearch
* OpenSearch
* Distributed Systems

trong giai đoạn đầu.

---

# Performance Constraints

Giả định môi trường thực tế:

* RAM khoảng 16–32GB
* SSD hạn chế
* Dữ liệu raw nằm trên HDD

Yêu cầu:

* Keyframe-first workflow
* Lazy loading
* Virtualized result grid
* Không load toàn bộ ảnh vào RAM
* Không cache video lớn trong RAM
* Hạn chế memory footprint

---

# Deliverables

Hãy giúp mình xây dựng một SPEC hoàn chỉnh cho hệ thống này bao gồm:

1. Product Vision
2. Functional Requirements
3. Non-Functional Requirements
4. User Stories
5. System Architecture
6. Domain Model
7. Data Model
8. Storage Design
9. Retrieval Architecture
10. Preprocessing Pipeline
11. Agent Architecture
12. UI/UX Design
13. API Design
14. Module Structure
15. Deployment Model
16. Performance Strategy
17. Roadmap MVP → Production
18. Technical Risks
19. Open Questions
20. Những quyết định kiến trúc cần chốt trước khi bắt đầu development

Nếu còn điểm nào chưa rõ, hãy đặt câu hỏi trước khi thiết kế chi tiết.
