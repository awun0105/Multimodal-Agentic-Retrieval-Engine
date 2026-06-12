# AI Challenge TP.HCM 2026 — Phân tích Top-down & Chiến lược xây hệ thống dự thi

> Tài liệu này dùng làm bản phân tích nền tảng để hiểu cuộc thi AI Challenge TP.HCM 2026 theo hướng **first-principles thinking**: cuộc thi là gì, BTC thực sự đang yêu cầu gì, format bài toán có thể là gì, quá trình thi diễn ra ra sao, từ đó suy ra nên xây hệ thống nào, workflow nào, kiến trúc nào và chiến lược chuẩn bị ra sao.

---

## 1. Tóm tắt điều hành

AI Challenge TP.HCM 2026 không nên được hiểu đơn giản là một cuộc thi chatbot, cũng không chỉ là một cuộc thi tìm kiếm video bằng CLIP. Bản chất đúng hơn là:

> **Cuộc thi xây dựng một trợ lý ảo thông minh có khả năng phân tích và truy xuất thông tin chuyên sâu từ kho dữ liệu multimedia lớn, bao gồm hình ảnh, video, âm thanh, văn bản, OCR, transcript và metadata.**

Nói thực dụng hơn:

> Ta cần xây một hệ thống giống “Google Search + ChatGPT + video search engine” cho một kho dữ liệu multimedia, tối ưu để trả về đúng bằng chứng: video, đoạn video, frame, timestamp hoặc câu trả lời.

Hệ thống dự thi nên có hai lớp chính:

1. **Multimodal Retrieval Engine**  
   Bộ máy tìm kiếm trên video, hình ảnh, âm thanh, text, OCR, transcript, caption và metadata.

2. **Intelligent Assistant / Agent Layer**  
   Lớp trợ lý hiểu truy vấn, chọn chiến lược tìm kiếm, gọi các module phù hợp, hợp nhất kết quả, rerank, giải thích và trả output theo format thi.

Từ thông tin chính thức, cuộc thi 2026 hướng đến 2 hình thức:

- **Hình thức truyền thống:** người dùng sử dụng công cụ trợ lý ảo của đội để xử lý truy vấn.
- **Hình thức tự động:** thử nghiệm thi tự động giữa các trợ lý ảo thông minh của các nhóm.

Vì vậy, hệ thống không nên chỉ là UI cho người dùng, mà cần được thiết kế như một **agent service có input/output rõ ràng**, có thể được gọi qua UI, CLI, batch runner hoặc API.

---

## 2. Cuộc thi này là gì?

### 2.1. Tên và bối cảnh

Tên hội thi:

> **Hội thi Thử thách Trí tuệ Nhân tạo — AI Challenge Thành phố Hồ Chí Minh năm 2026**

Đơn vị chủ trì:

- Sở Khoa học và Công nghệ TP.HCM.

Đơn vị phối hợp:

- Đại học Quốc gia TP.HCM.
- Sở Giáo dục và Đào tạo.
- Thành Đoàn TP.HCM.
- Hội Tin học TP.HCM.
- Các đơn vị liên quan khác.

### 2.2. Mục tiêu cấp cao

Cuộc thi nhằm:

- Thúc đẩy học tập, nghiên cứu và ứng dụng AI.
- Gắn AI với chương trình xây dựng TP.HCM thành đô thị thông minh.
- Khuyến khích cá nhân, nhóm nghiên cứu trong và ngoài nước đề xuất giải pháp AI thực tiễn.
- Lan tỏa các giải pháp khoa học - công nghệ mới.
- Tìm kiếm các giải pháp có khả năng ứng dụng cho các bài toán thực tế tại TP.HCM, mở rộng ra cả nước, khu vực và quốc tế.

### 2.3. Suy luận first-principles

Từ mục tiêu này, ta suy ra cuộc thi không chỉ quan tâm đến “model accuracy” thuần túy. BTC sẽ đánh giá cao các hệ thống có khả năng:

- xử lý dữ liệu lớn;
- xử lý dữ liệu đặc thù Việt Nam;
- truy xuất nhanh, đúng, có thể kiểm chứng;
- có kiến trúc hệ thống rõ ràng;
- có khả năng ứng dụng thực tế;
- có hướng nghiên cứu đủ tốt để trình bày tại hội nghị/kỷ yếu.

Do đó, chiến lược đúng là xây **một hệ thống end-to-end**, không phải một model đơn lẻ.

---

## 3. Đối tượng, bảng thi và timeline

### 3.1. Đối tượng

Cuộc thi mở cho:

- Người Việt Nam.
- Người Việt Nam định cư ở nước ngoài.
- Người nước ngoài.
- Cá nhân hoặc tập thể.
- Mỗi đội tối đa 5 thành viên.

### 3.2. Bảng thi

| Bảng | Đối tượng |
|---|---|
| Bảng A | Sinh viên, thanh niên quan tâm đến CNTT và AI |
| Bảng B | Học sinh THPT yêu thích CNTT và muốn tìm hiểu AI |

Đối với Bảng B, thí sinh được phép sử dụng công cụ có sẵn do BTC cung cấp để thực hiện yêu cầu cuộc thi.

### 3.3. Timeline dự kiến 2026

| Mốc | Thời gian dự kiến | Ý nghĩa chiến lược |
|---|---:|---|
| Phát động | 15/5–20/5/2026 | Bắt đầu chính thức, mở đăng ký |
| Hạn đăng ký | 15/6/2026 | Cần chốt đội hình trước mốc này |
| Công bố nội dung/yêu cầu sơ tuyển | 25/6/2026 | Mốc rất quan trọng để mapping hệ thống với đề thật |
| Tập huấn | Tháng 6–7/2026 | Cơ hội hỏi rule, dataset, chấm điểm, format output |
| Vòng sơ tuyển | Tháng 8/2026 | Cần hệ thống ổn định, reproducible |
| Công bố kết quả sơ tuyển | 30/8/2026 | Nếu vào chung kết, chỉ còn khoảng 2 tuần để tối ưu live |
| Chung kết | 12/9–26/9/2026 | Thi live/hybrid, cần UI + operator + agent ổn định |
| Tổng kết trao giải | 10/2026 | Có thể mở hướng paper, SoICT, MTAP, kết nối triển khai |

---

## 4. Đề bài chính thức là gì?

Nội dung cuộc thi:

> Thí sinh phát triển giải pháp **Trợ lý ảo thông minh hỗ trợ phân tích và truy xuất thông tin chuyên sâu trong dữ liệu lớn multimedia**, bao gồm hình ảnh, âm thanh và văn bản.

Đề bài năm 2026 có thể hiểu theo 3 tầng:

### Tầng 1: Truy xuất thông tin

Hệ thống phải tìm được thông tin đúng trong kho dữ liệu multimedia.

Ví dụ:

- Tìm cảnh có người phát biểu trước màn hình xanh.
- Tìm đoạn video có nhắc đến “trí tuệ nhân tạo trong giáo dục”.
- Tìm cảnh có bảng hiệu hoặc chữ cụ thể trên màn hình.
- Tìm đoạn video tương ứng với một mô tả sự kiện.

### Tầng 2: Phân tích thông tin

Không chỉ tìm, hệ thống còn cần hiểu nội dung.

Ví dụ:

- Người trong video đang làm gì?
- Chủ đề được nhắc đến trong đoạn phát biểu là gì?
- Nội dung chính của đoạn video là gì?
- Câu trả lời cho câu hỏi dựa trên video là gì?

### Tầng 3: Trợ lý ảo / agent

Hệ thống phải có khả năng hỗ trợ người dùng hoặc tự động xử lý truy vấn.

Ví dụ:

- Hiểu query tiếng Việt tự nhiên.
- Tự quyết định nên tìm bằng hình ảnh, audio, OCR hay text.
- Tự sinh biến thể truy vấn.
- Tự hợp nhất kết quả từ nhiều nguồn.
- Tự rerank và đề xuất kết quả tốt nhất.

---

## 5. Cuộc thi có phải là chatbot không?

Câu trả lời ngắn:

> **Không chỉ là chatbot. Chatbot chỉ là một giao diện. Sản phẩm thật là một multimodal retrieval assistant.**

Một chatbot thông thường chỉ trả lời bằng text. Nhưng hệ thống dự thi cần trả về:

- video ID;
- timestamp;
- frame ID;
- segment ID;
- answer text;
- evidence;
- confidence;
- danh sách candidate.

Giao diện có thể giống chatbot ở phần input, nhưng output phải giống một search dashboard:

```text
[Query box]
Tìm cảnh người phát biểu trước màn hình xanh về trí tuệ nhân tạo

[Top results]
1. video_0342 | 00:12:48 | thumbnail | confidence 0.87
2. video_0188 | 00:03:21 | thumbnail | confidence 0.74
3. video_0912 | 00:18:05 | thumbnail | confidence 0.69

[Video preview]
[Nearby frames]
[Evidence: visual / OCR / ASR / caption]
[Submit/copy result]
```

---

## 6. Format bài toán có thể xuất hiện

Cuộc thi được mô tả là có thể thức tương tự:

- Lifelog Search Challenge — LSC.
- Video Browser Showdown — VBS.

Từ đó, có thể dự đoán các dạng task chính.

---

## 7. KIS — Known-Item Search

### 7.1. KIS là gì?

KIS là bài toán tìm **một item/khoảnh khắc cụ thể đã tồn tại trong dataset**.

Nó giống như BTC nói:

> “Hãy tìm đúng cảnh này trong toàn bộ kho video.”

### 7.2. Input

Thường là mô tả chi tiết bằng text, hoặc đôi khi bằng hình ảnh/video mẫu.

Ví dụ:

```text
Tìm cảnh một người đàn ông mặc áo trắng đứng cạnh xe đỏ trước một tòa nhà.
```

### 7.3. Output

Thường là:

```text
video_id + timestamp
```

hoặc:

```text
frame_id
```

hoặc:

```text
segment_id
```

### 7.4. Đặc điểm

- Có một đáp án đúng hoặc rất ít đáp án đúng.
- Cần precision cao.
- Cần tìm nhanh.
- Nếu submit sai có thể bị trừ điểm tùy luật.

### 7.5. Hệ thống cần gì?

- Visual embedding search.
- Caption search.
- Object/concept search.
- OCR nếu cảnh có chữ.
- ASR nếu mô tả liên quan lời nói.
- Timeline navigation.
- Reranking.

---

## 8. AVS — Ad-hoc Video Search

### 8.1. AVS là gì?

AVS là bài toán tìm **nhiều video/đoạn video liên quan đến một khái niệm hoặc sự kiện tổng quát**.

Khác KIS, AVS không nhất thiết chỉ có một đáp án.

### 8.2. Input

Một query rộng hơn.

Ví dụ:

```text
Tìm các cảnh có người đi xe máy trong thành phố.
```

### 8.3. Output

Danh sách kết quả được xếp hạng:

```text
1. video_0012, 00:01:20
2. video_0088, 00:04:15
3. video_0311, 00:09:02
```

### 8.4. Đặc điểm

- Có nhiều đáp án đúng.
- Cần recall cao.
- Cần ranking tốt.
- Cần tránh duplicate quá nhiều.

### 8.5. Hệ thống cần gì?

- Semantic visual search.
- Concept search.
- Caption embedding.
- Diversity ranking.
- Deduplication theo video/scene.

---

## 9. VQA — Visual Question Answering

### 9.1. VQA là gì?

VQA là bài toán trả lời câu hỏi dựa trên dữ liệu hình ảnh/video/multimedia.

### 9.2. Input

Một câu hỏi.

Ví dụ:

```text
Người phát biểu trong đoạn video đang nói về chủ đề gì?
```

hoặc:

```text
Xe buýt trong cảnh này có màu gì?
```

### 9.3. Output

Text answer, thường kèm evidence.

```json
{
  "answer": "Người phát biểu đang nói về ứng dụng AI trong đô thị thông minh.",
  "video_id": "video_0188",
  "timestamp": "00:03:21"
}
```

### 9.4. Đặc điểm

- Không chỉ retrieve mà còn phải reason.
- Có thể cần kết hợp visual, ASR, OCR, caption.
- Cần tránh hallucination.
- Cần evidence grounding.

### 9.5. Hệ thống cần gì?

- Retrieval trước, reasoning sau.
- LVLM/LLM để phân tích candidate.
- ASR/transcript để hiểu lời nói.
- OCR để đọc chữ trong video.
- Evidence citation nội bộ.

---

## 10. Các khái niệm dữ liệu cốt lõi

### 10.1. Video ID

Mã định danh của toàn bộ video.

Ví dụ:

```text
video_0342
```

### 10.2. Segment ID

Mã định danh của một đoạn liên tục trong video.

Ví dụ:

```text
video_0342_seg_015
start_time: 00:12:40
end_time: 00:12:55
```

### 10.3. Frame ID

Mã định danh của một frame/keyframe cụ thể.

Ví dụ:

```text
video_0342_frame_18420
```

### 10.4. Timestamp

Thời điểm trong video.

Ví dụ:

```text
00:12:48
```

hoặc:

```text
768.2 seconds
```

### 10.5. Quan hệ giữa chúng

```text
videoID
└── segmentID / timeframe
    └── frameID / keyframe
        └── timestamp
```

Một kết quả tốt thường cần ít nhất:

```text
videoID + timestamp
```

Nếu BTC yêu cầu chi tiết hơn, có thể cần thêm:

```text
frameID / segmentID / start_time / end_time
```

---

## 11. Segment nên hiểu như thế nào?

Segment là một đoạn liên tục trong video. Segment **không bắt buộc phải chia đều**.

Có 3 cách chia phổ biến:

### 11.1. Chia đều theo thời gian

Ví dụ mỗi segment 10 giây.

Ưu điểm:

- Dễ làm.
- Dễ index.
- Dễ map timestamp.

Nhược điểm:

- Có thể cắt ngang một event.

### 11.2. Chia theo shot/scene

Dùng shot boundary detection để phát hiện chuyển cảnh.

Ưu điểm:

- Bám sát nội dung video.
- Tốt cho retrieval.

Nhược điểm:

- Cần xử lý thêm.

### 11.3. Chia theo event/logical unit

Ví dụ:

- một đoạn phỏng vấn;
- một phần bản tin;
- một cảnh hành động;
- một câu trả lời;
- một chủ đề.

Ưu điểm:

- Semantic tốt.

Nhược điểm:

- Khó tự động hóa.

### 11.4. Khuyến nghị

Dùng hybrid segmentation:

```text
1. Extract keyframe mỗi 1–2 giây.
2. Detect shot boundary.
3. Gom frame thành shot/segment.
4. Nếu segment quá dài, chia nhỏ thành 10–15 giây.
5. Nếu segment quá ngắn, gộp với segment gần đó.
6. Khi tìm được keyframe, mở rộng ±5–10 giây để kiểm tra.
```

---

## 12. First-principles: từ đề bài suy ra hệ thống cần xây

### 12.1. Đề bài yêu cầu truy xuất multimedia

Suy ra cần index nhiều loại dữ liệu:

| Loại dữ liệu | Cần index gì? |
|---|---|
| Hình ảnh/video frame | visual embedding |
| Caption/mô tả frame | text embedding + BM25 |
| Âm thanh/lời nói | ASR transcript index |
| Chữ trên màn hình | OCR index |
| Metadata | database + filters |
| Object/concept | tag index |

### 12.2. Đề bài yêu cầu phân tích chuyên sâu

Suy ra cần thêm:

- LLM/LVLM reasoning.
- Reranking top candidates.
- Evidence verification.
- Answer generation grounded on retrieved evidence.

### 12.3. Đề bài yêu cầu trợ lý ảo

Suy ra cần:

- Query understanding.
- Query decomposition.
- Tool selection.
- Search planning.
- Multi-step refinement.
- Final answer formatting.

### 12.4. Đề bài có hình thức truyền thống

Suy ra cần:

- Human-operated UI.
- Thumbnail grid.
- Video preview.
- Timeline navigation.
- Hotkeys.
- Candidate tray.
- Submit/copy result.

### 12.5. Đề bài có hình thức tự động

Suy ra cần:

- Agent API.
- Batch runner.
- Standard input/output.
- Confidence scoring.
- Auto-reranking.
- Dockerized service.

---

## 13. Workflow dữ liệu: từ video đến search result

### 13.1. Offline preprocessing

```text
Raw videos
→ extract metadata
→ extract keyframes
→ detect shots/segments
→ generate thumbnails
→ run visual embedding
→ run OCR
→ run ASR
→ generate captions
→ store everything in indexes/databases
```

### 13.2. Online retrieval

```text
User/BTC query
→ query understanding
→ choose retrieval strategy
→ search visual index
→ search caption/text index
→ search OCR index
→ search ASR index
→ merge candidates
→ rerank
→ verify evidence
→ return video/frame/timestamp/answer
```

### 13.3. Submission workflow

```text
Query from committee
→ system returns top candidates
→ human or agent selects best candidate
→ output formatted as video_id/timestamp/frame_id/answer
→ submit to committee platform
```

---

## 14. Visual retrieval core — pipeline cơ bản

Đây là pipeline bạn đã mô tả đúng:

```text
Video
→ segment/shot detection
→ keyframe extraction
→ keyframe embedding
→ text query embedding
→ similarity search
→ top keyframes
→ map keyframe to timestamp
→ map timestamp to segment
→ map segment to videoID
→ return result
```

Ví dụ:

```text
Query:
Tìm cảnh người phát biểu trước màn hình xanh.

Text embedding của query
→ so sánh với visual embeddings của keyframes
→ tìm được keyframe_18420
→ keyframe_18420 thuộc segment_015
→ segment_015 thuộc video_0342
→ timestamp = 00:12:48

Output:
video_0342, 00:12:48
```

Đây là lõi của visual retrieval. Nhưng hệ thống 2026 cần mở rộng sang multimodal retrieval.

---

## 15. Multimodal retrieval core — pipeline đầy đủ

### 15.1. Vì sao không đủ nếu chỉ dùng keyframe embedding?

Vì có nhiều query không biểu hiện rõ bằng hình ảnh.

Ví dụ:

```text
Tìm đoạn người nói về trí tuệ nhân tạo trong giáo dục.
```

Query này cần ASR/transcript.

Ví dụ khác:

```text
Tìm cảnh có dòng chữ “Hội nghị chuyển đổi số”.
```

Query này cần OCR.

Ví dụ khác:

```text
Người phát biểu đang nói về chủ đề gì?
```

Query này cần VQA/reasoning.

### 15.2. Các nguồn tín hiệu cần kết hợp

```text
visual keyframe embedding
+ segment caption embedding
+ OCR text
+ ASR transcript
+ object tags
+ metadata
+ temporal context
```

### 15.3. Fusion score ví dụ

```text
final_score =
  visual_score * w_visual
+ caption_score * w_caption
+ asr_score * w_asr
+ ocr_score * w_ocr
+ object_score * w_object
+ metadata_score * w_metadata
```

Trọng số nên thay đổi theo loại query.

| Query type | Visual | Caption | ASR | OCR | Object |
|---|---:|---:|---:|---:|---:|
| Cảnh/hình ảnh | Cao | Trung bình | Thấp | Thấp | Cao |
| Lời nói/chủ đề | Thấp | Trung bình | Cao | Thấp | Thấp |
| Chữ trên màn hình | Thấp | Thấp | Thấp | Cao | Thấp |
| Sự kiện tổng hợp | Cao | Cao | Trung bình | Trung bình | Trung bình |
| VQA | Trung bình | Cao | Cao | Trung bình | Trung bình |

---

## 16. Kiến trúc hệ thống đề xuất

### 16.1. High-level architecture

```text
                    ┌──────────────────────┐
                    │ Human Search UI       │
                    └──────────┬───────────┘
                               │
                               v
┌──────────────────────┐   ┌──────────────────────┐
│ Batch/Auto Runner     │-->| Agent API             │
└──────────────────────┘   └──────────┬───────────┘
                                      │
                                      v
                          ┌──────────────────────┐
                          │ Query Planner         │
                          └──────────┬───────────┘
                                      │
                                      v
                          ┌──────────────────────┐
                          │ Retrieval Orchestrator│
                          └────┬─────┬─────┬─────┘
                               │     │     │
              ┌────────────────┘     │     └────────────────┐
              v                      v                      v
      ┌──────────────┐       ┌──────────────┐       ┌──────────────┐
      │ Visual Index  │       │ Text/OCR IDX  │       │ ASR Index    │
      └──────┬───────┘       └──────┬───────┘       └──────┬───────┘
             │                      │                      │
             └──────────────┬───────┴──────────────┬───────┘
                            v                      v
                    ┌──────────────────────┐
                    │ Fusion + Reranking    │
                    └──────────┬───────────┘
                               v
                    ┌──────────────────────┐
                    │ Verifier / LVLM Check │
                    └──────────┬───────────┘
                               v
                    ┌──────────────────────┐
                    │ Answer Formatter      │
                    └──────────────────────┘
```

### 16.2. Thành phần chính

| Component | Vai trò |
|---|---|
| Human Search UI | Giao diện thi live cho người vận hành |
| Agent API | Interface chuẩn cho UI, batch, auto mode |
| Query Planner | Phân tích query, chọn chiến lược tìm kiếm |
| Retrieval Orchestrator | Gọi nhiều search module song song |
| Visual Index | Tìm bằng visual embedding |
| Text/OCR Index | Tìm bằng caption, OCR, text metadata |
| ASR Index | Tìm bằng transcript/lời nói |
| Fusion + Reranking | Hợp nhất và xếp hạng kết quả |
| Verifier | Kiểm tra evidence bằng LLM/LVLM/rules |
| Answer Formatter | Trả kết quả đúng format |

---

## 17. Agent API cho hình thức tự động

Vì BTC nói sẽ thử nghiệm hình thức tự động giữa các trợ lý ảo, nên nên thiết kế agent như một service có contract rõ.

### 17.1. Single query API

```http
POST /agent/search
```

Request:

```json
{
  "query_id": "q_001",
  "query": "Tìm cảnh một người phát biểu trước màn hình màu xanh.",
  "query_type": "auto",
  "top_k": 10,
  "time_budget_seconds": 60,
  "return_evidence": true
}
```

Response:

```json
{
  "query_id": "q_001",
  "status": "success",
  "detected_query_type": "visual_event",
  "results": [
    {
      "rank": 1,
      "video_id": "video_0342",
      "timestamp": 768.2,
      "start_time": 763.0,
      "end_time": 773.0,
      "frame_id": "video_0342_frame_18420",
      "segment_id": "video_0342_seg_015",
      "confidence": 0.87,
      "answer": null,
      "evidence": {
        "caption": "Một người đang phát biểu trước màn hình màu xanh.",
        "objects": ["person", "podium", "screen"],
        "ocr": ["AI", "conference"],
        "asr": ["trí tuệ nhân tạo"]
      }
    }
  ],
  "debug": {
    "latency_ms": 1840,
    "strategy": ["visual", "caption", "asr"]
  }
}
```

### 17.2. Batch API

```http
POST /agent/batch
```

Request:

```json
{
  "queries": [
    {
      "query_id": "q_001",
      "query": "Find a man speaking at a podium.",
      "query_type": "textual_kis"
    },
    {
      "query_id": "q_002",
      "query": "What topic is being discussed in the segment about smart cities?",
      "query_type": "vqa"
    }
  ],
  "top_k": 5
}
```

Response:

```json
{
  "results": [
    {
      "query_id": "q_001",
      "video_id": "video_0342",
      "timestamp": 768.2,
      "confidence": 0.87
    },
    {
      "query_id": "q_002",
      "answer": "Người phát biểu đang nói về ứng dụng AI trong quản lý đô thị thông minh.",
      "video_id": "video_0188",
      "timestamp": 201.4,
      "confidence": 0.81
    }
  ]
}
```

### 17.3. CLI fallback

Ngoài API, nên có CLI để phòng trường hợp BTC dùng file-based evaluation.

```bash
python run_agent.py --input queries.json --output answers.json
```

---

## 18. Human-operated UI cho hình thức truyền thống

### 18.1. UI không nên chỉ là chatbot

UI tốt nên là search dashboard có assistant input.

```text
┌──────────────────────────────────────────────┐
│ Query / Chat Input                            │
│ Tìm cảnh người phát biểu trước màn hình xanh  │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│ Top Candidates                                │
│ [thumb] video_0342 00:12:48 score 0.87        │
│ [thumb] video_0188 00:03:21 score 0.74        │
│ [thumb] video_0912 00:18:05 score 0.69        │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│ Video Preview + Nearby Timeline               │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│ Evidence Panel: caption / OCR / ASR / objects  │
└──────────────────────────────────────────────┘
```

### 18.2. Các tính năng cần có

- Query input tiếng Việt/Anh.
- Grid thumbnail.
- Video preview.
- Nearby frames trước/sau timestamp.
- Candidate tray.
- Similar-frame search.
- Filter theo OCR/ASR/object.
- Copy/submit videoID + timestamp.
- Query history.
- Hotkeys.
- Confidence/evidence display.

### 18.3. Nguyên tắc UI khi thi live

> UI không cần đẹp trước, cần nhanh, rõ, ít thao tác và giảm sai sót.

Các hotkey nên có:

| Hotkey | Chức năng |
|---|---|
| Enter | Search |
| 1–9 | Mở candidate |
| S | Submit/copy result |
| F | Find similar |
| [ / ] | Tua trước/sau |
| A | ASR filter |
| O | OCR filter |
| C | Caption filter |

---

## 19. Query understanding và tool selection

### 19.1. Vì sao cần query planner?

Vì không phải query nào cũng nên search giống nhau.

Ví dụ:

```text
Tìm cảnh người phát biểu trước màn hình xanh.
```

Nên ưu tiên visual + caption.

```text
Tìm đoạn người nói về chuyển đổi số trong giáo dục.
```

Nên ưu tiên ASR + transcript + caption.

```text
Tìm cảnh có dòng chữ “Hội nghị trí tuệ nhân tạo”.
```

Nên ưu tiên OCR.

### 19.2. Output của query planner

```json
{
  "query_type": "hybrid",
  "main_intent": "find_video_segment",
  "visual_constraints": {
    "objects": ["person", "microphone", "screen"],
    "actions": ["speaking", "presenting"],
    "scene": ["conference", "stage"]
  },
  "audio_constraints": {
    "keywords": ["chuyển đổi số", "giáo dục"]
  },
  "text_constraints": {
    "ocr_keywords": ["hội nghị", "AI", "TP.HCM"]
  },
  "search_strategy": ["asr", "caption", "visual", "ocr"]
}
```

---

## 20. Reranking và verification

### 20.1. Vì sao cần rerank?

Embedding search thường trả về nhiều candidate gần đúng nhưng chưa chắc đúng nhất.

Reranking giúp:

- kết hợp nhiều tín hiệu;
- ưu tiên candidate có evidence mạnh;
- giảm duplicate;
- tăng precision top-1/top-5.

### 20.2. Reranking có thể dùng

- Weighted score fusion.
- Cross-encoder text-image/text-caption reranker.
- LVLM verify top-K.
- Rule-based boost.
- Temporal consistency.
- ASR/OCR evidence matching.

### 20.3. Verification

Verifier trả lời câu hỏi:

> Candidate này có thật sự khớp query không?

Ví dụ:

```text
Query: người phát biểu trước màn hình xanh
Candidate: video_0342 at 00:12:48

Verifier check:
- Có người không?
- Có đang phát biểu không?
- Có màn hình xanh không?
- Có evidence OCR/ASR liên quan không?
```

---

## 21. Output và submission format

Format chính thức cần chờ BTC công bố, nhưng hệ thống nên support nhiều output type.

### 21.1. KIS output

```json
{
  "query_id": "q_001",
  "video_id": "video_0342",
  "timestamp": 768.2,
  "frame_id": "video_0342_frame_18420",
  "segment_id": "video_0342_seg_015",
  "confidence": 0.87
}
```

### 21.2. AVS output

```json
{
  "query_id": "q_002",
  "results": [
    {"video_id": "video_0012", "timestamp": 80.1, "score": 0.91},
    {"video_id": "video_0088", "timestamp": 255.4, "score": 0.84},
    {"video_id": "video_0311", "timestamp": 542.0, "score": 0.79}
  ]
}
```

### 21.3. VQA output

```json
{
  "query_id": "q_003",
  "answer": "Xe buýt có màu xanh.",
  "evidence_video_id": "video_0123",
  "timestamp": 84.0,
  "confidence": 0.88
}
```

---

## 22. Đề xuất tech stack

### 22.1. Backend

- Python.
- FastAPI.
- FAISS hoặc Qdrant/Milvus.
- DuckDB hoặc PostgreSQL.
- Elasticsearch/OpenSearch/Tantivy.
- Redis.
- Celery/RQ cho offline jobs.
- Docker Compose.

### 22.2. AI/ML

- CLIP / SigLIP / EVA-CLIP cho visual embedding.
- bge-m3 / multilingual-e5 cho text embedding.
- Whisper large-v3/turbo cho ASR.
- PaddleOCR / VietOCR cho OCR.
- Qwen2.5-VL / InternVL / LLaVA-family cho caption/LVLM verification.
- bge-reranker/cross-encoder cho reranking.

### 22.3. Frontend

- Next.js / React.
- HTML5 video player.
- Thumbnail grid.
- Timeline viewer.
- Keyboard-first interaction.

### 22.4. Infra

- Docker Compose.
- Local NVMe SSD nếu có.
- GPU machine cho preprocessing/captioning.
- Backup index.
- Script rebuild toàn bộ pipeline.

---

## 23. Repository structure đề xuất

```text
ai-challenge-2026/
├── apps/
│   ├── web-ui/
│   ├── agent-api/
│   └── batch-runner/
├── services/
│   ├── ingestion/
│   ├── keyframe-extraction/
│   ├── shot-detection/
│   ├── visual-embedding/
│   ├── ocr/
│   ├── asr/
│   ├── captioning/
│   ├── retrieval/
│   ├── reranking/
│   └── verification/
├── data/
│   ├── raw/
│   ├── frames/
│   ├── thumbnails/
│   ├── indexes/
│   └── metadata/
├── notebooks/
├── scripts/
├── configs/
├── docker-compose.yml
└── README.md
```

---

## 24. Kế hoạch chuẩn bị theo timeline

### Phase 1 — Trước 15/6/2026

Mục tiêu:

> Có baseline chạy được trước hạn đăng ký.

Việc cần làm:

- Chốt team.
- Chốt stack.
- Dựng repo.
- Tạo mini dataset.
- Extract keyframes.
- Build visual index.
- Build OCR/ASR/caption baseline.
- Làm UI search đơn giản.
- Tạo 100 query luyện tập.
- Đo Recall@10/50.

Deliverable:

```text
Query tiếng Việt → top video/frame/timestamp → preview được.
```

### Phase 2 — 25/6 đến hết tháng 7

Mục tiêu:

> Mapping hệ thống với yêu cầu chính thức và dataset thật.

Việc cần làm:

- Đọc yêu cầu sơ tuyển.
- Đi tập huấn.
- Hỏi rule/dataset/chấm điểm/API/phần cứng.
- Ingest dataset nếu được cấp.
- Tune index.
- Tune fusion weights.
- Mock contest mỗi tuần.

### Phase 3 — Tháng 8

Mục tiêu:

> Qua sơ tuyển chắc chắn.

Việc cần làm:

- Freeze core trước deadline.
- Tạo batch submission script.
- Validate output format.
- Log từng query và candidate.
- Có fallback nếu agent lỗi.
- Không thêm feature rủi ro sát ngày.

### Phase 4 — 30/8 đến chung kết

Mục tiêu:

> Tối ưu thi live và tự động.

Việc cần làm:

- Mock contest 3–5 buổi/tuần.
- Ghi màn hình operator.
- Review lỗi.
- Tối ưu UI/hotkey.
- Tối ưu latency.
- Chốt vai trò từng người.
- Freeze version thi đấu.

---

## 25. Đội hình lý tưởng

| Vai trò | Trách nhiệm |
|---|---|
| Technical Lead / Architect | Thiết kế hệ thống, ưu tiên kỹ thuật, review end-to-end |
| AI Retrieval Engineer | Embedding, vector index, rerank, evaluation |
| Backend/Data Engineer | Ingestion, API, database, performance |
| Frontend/UX Engineer | Search UI, video preview, hotkeys, workflow thi live |
| Agent/QA/Operator | Query planner, auto-agent, mock contest, evaluation set |

Nếu team nhỏ, ưu tiên tuyển người theo thứ tự:

1. Backend/data pipeline chắc.
2. Frontend/UX nhanh.
3. AI retrieval/reranking.
4. Agent/LLM.

---

## 26. Evaluation nội bộ

Không thể cải thiện nếu không có benchmark riêng.

### 26.1. Dataset luyện tập

Tạo mini dataset:

- video tin tức tiếng Việt;
- video hội thảo;
- video đường phố;
- video có chữ trên màn hình;
- video có lời nói rõ;
- video có nhiều sự kiện trong cùng một clip.

### 26.2. Query set

Tạo ít nhất 200 query:

| Loại query | Số lượng |
|---|---:|
| Visual KIS | 50 |
| AVS/general event | 40 |
| OCR-based | 30 |
| ASR-based | 30 |
| VQA | 30 |
| Temporal reasoning | 20 |

### 26.3. Metrics

| Metric | Ý nghĩa |
|---|---|
| Recall@10 | Đáp án đúng có nằm trong top 10 không |
| Recall@50 | Đáp án đúng có nằm trong top 50 không |
| MRR | Kết quả đúng đứng thứ mấy |
| Latency | Thời gian trả kết quả |
| Time-to-answer | Thời gian người vận hành tìm và submit |
| Submit accuracy | Tỷ lệ submit đúng |
| Auto success rate | Tỷ lệ agent tự chọn đúng |

### 26.4. Mục tiêu cạnh tranh

| Metric | Mức tối thiểu | Mức cạnh tranh |
|---|---:|---:|
| Recall@50 visual/text | >70% | >85% |
| Query latency | <2s | <1s |
| Query dễ time-to-answer | <45s | <20s |
| Query trung bình | <90s | <45s |
| UI crash | 0 | 0 |
| Auto-agent query dễ | >50% | >70% |

---

## 27. Các câu hỏi phải hỏi BTC trong tập huấn

1. Dataset gồm những loại dữ liệu nào?
2. BTC có cung cấp keyframe, embedding, OCR, transcript hoặc metadata sẵn không?
3. Có được dùng dữ liệu ngoài không?
4. Có được dùng pretrained model/API thương mại không?
5. Khi chung kết có internet không?
6. Có giới hạn GPU/server/cloud không?
7. Hệ thống phải chạy local hay được chạy cloud?
8. Format nộp là videoID, frameID, timestamp, segmentID hay answer text?
9. Có trừ điểm khi submit sai không?
10. Mỗi query có giới hạn thời gian bao lâu?
11. Query có tiếng Việt, tiếng Anh hay mixed?
12. Có visual query bằng ảnh/video không?
13. Auto mode được chạy như thế nào?
14. BTC gọi API, chạy Docker, dùng batch file hay yêu cầu submit trên web?
15. Có yêu cầu evidence/explanation không?

---

## 28. Các rủi ro chính

| Rủi ro | Tác động | Cách giảm |
|---|---|---|
| Dataset lớn hơn dự kiến | Index chậm, search chậm | Thiết kế pipeline scale từ đầu |
| Format output thay đổi | Nộp sai | Tách Answer Formatter riêng |
| Không có internet khi thi | API ngoài không dùng được | Có local fallback |
| Query nhiều tiếng Việt đời thường | Search kém | Query expansion tiếng Việt |
| OCR/ASR noise | Sai evidence | Fuzzy search + confidence |
| UI khó dùng | Mất thời gian live | Mock contest + hotkeys |
| Agent hallucinate | Submit sai | Retrieval-grounded + verifier |
| Code đổi sát ngày | Crash | Freeze trước deadline |

---

## 29. Chiến lược research để tận dụng SoICT/MTAP

Vì đội đạt kết quả tốt có thể được mời trình bày tại Special Session về Lifelog and Multimedia Event Retrieval ở SoICT 2026 và có cơ hội gửi Special Issue MTAP, nên ngay từ đầu cần log theo hướng nghiên cứu.

Cần lưu:

- kiến trúc hệ thống;
- baseline;
- proposed method;
- ablation study;
- Recall@K;
- latency;
- human vs auto mode;
- query type analysis;
- error analysis;
- case studies;
- screenshots UI;
- agent decision logs.

Research story đề xuất:

> **A Vietnamese-aware multimodal assistant for large-scale multimedia event retrieval, combining visual-language search, ASR/OCR-grounded evidence, bounded agentic query planning, and human-in-the-loop interaction.**

---

## 30. Chiến lược tổng kết

Từ first principles, ta suy ra chiến lược đúng:

```text
Không xây chatbot đơn thuần.
Không chỉ làm CLIP search.
Không bắt đầu bằng fine-tune model.

Hãy xây:
1. Multimedia retrieval engine.
2. Human-operated search dashboard.
3. Agent API cho auto mode.
4. Query planner + tool selection.
5. Fusion + reranking + verification.
6. Submission formatter.
7. Evaluation + mock contest workflow.
```

Công thức hệ thống cạnh tranh:

```text
Fast hybrid retrieval
+ good Vietnamese query understanding
+ OCR/ASR/caption/visual indexes
+ strong UI for live search
+ bounded auto-agent
+ reranking and evidence verification
+ repeated mock contest practice
= competitive AI Challenge 2026 system
```

---

## 31. Checklist hành động ngay

### Tuần đầu tiên

- [ ] Tạo repo.
- [ ] Chốt schema dữ liệu.
- [ ] Tạo mini dataset 20–50 video.
- [ ] Extract keyframes.
- [ ] Generate thumbnails.
- [ ] Build CLIP/SigLIP visual index.
- [ ] Làm API search đơn giản.
- [ ] Làm UI grid + preview.
- [ ] Tạo 50 query thử.

### Hai tuần đầu

- [ ] Thêm OCR.
- [ ] Thêm ASR.
- [ ] Thêm caption.
- [ ] Thêm hybrid search.
- [ ] Thêm rerank đơn giản.
- [ ] Thêm output videoID/timestamp/frameID.
- [ ] Tạo evaluation script.
- [ ] Chạy mock contest đầu tiên.

### Trước vòng sơ tuyển

- [ ] Tương thích dataset thật.
- [ ] Tương thích format output BTC.
- [ ] Có batch runner.
- [ ] Có logging.
- [ ] Có backup indexes.
- [ ] Freeze stable version.

### Trước chung kết

- [ ] UI có hotkeys.
- [ ] Có candidate tray.
- [ ] Có similar-frame search.
- [ ] Có timeline navigation.
- [ ] Có auto-agent mode.
- [ ] Có script khởi động 1 lệnh.
- [ ] Mock contest nhiều lần.
- [ ] Chốt role team.

---

## 32. Định nghĩa sản phẩm cuối cùng

Sản phẩm dự thi nên được định nghĩa như sau:

> **Một hệ thống trợ lý truy xuất multimedia, có khả năng nhận truy vấn tự nhiên, phân tích intent, tìm kiếm trên video/hình ảnh/audio/text/OCR/transcript/metadata, hợp nhất và xếp hạng kết quả, kiểm chứng bằng evidence, rồi trả về đáp án dạng videoID, timestamp, frameID, segmentID hoặc text answer theo format cuộc thi.**

Tên kỹ thuật ngắn gọn:

> **Vietnamese-aware Multimodal Retrieval Agent for AI Challenge 2026**

