# AI Challenge TP.HCM 2026 — Phân tích Top-Down theo First Principles

> Mục tiêu tài liệu: không chỉ mô tả cuộc thi, mà suy luận từng bước từ đề bài chính thức để xác định **cần xây hệ thống gì, vì sao cần xây như vậy, kiến trúc ra sao, workflow vận hành thế nào, và nên chuẩn bị theo hướng nào**.

---

# 0. Đề bài gốc

Theo thông tin chính thức, nội dung thi là:

> **Phát triển giải pháp Trợ lý ảo thông minh hỗ trợ phân tích và truy xuất thông tin chuyên sâu trong dữ liệu lớn multimedia gồm hình ảnh, âm thanh và văn bản.**

Cuộc thi có hai hình thức:

1. **Hình thức truyền thống**: người dùng sử dụng công cụ Trợ lý ảo thông minh của nhóm để xử lý truy vấn thông tin từ kho dữ liệu multimedia.
2. **Hình thức tự động**: thử nghiệm thi tự động giữa các Trợ lý ảo thông minh của các nhóm.

Cuộc thi lấy cảm hứng từ:

- **Lifelog Search Challenge (LSC)**
- **Video Browser Showdown (VBS)**

---

# 1. Bóc tách đề bài theo first principles

Câu đề bài có các thành phần quan trọng:

```text
Trợ lý ảo thông minh
+ phân tích
+ truy xuất thông tin chuyên sâu
+ dữ liệu lớn multimedia
+ hình ảnh, âm thanh, văn bản
```

Ta không nên hiểu đây là “làm chatbot” theo nghĩa thông thường.

Một chatbot thông thường chỉ nhận câu hỏi và trả lời bằng text.  
Nhưng đề bài yêu cầu xử lý **kho dữ liệu multimedia lớn** và trả về **thông tin truy xuất được**.

Vì vậy, bản chất hệ thống cần xây là:

> **Một hệ thống truy xuất multimedia có lớp assistant/agent ở phía trên để hiểu truy vấn, điều phối các module tìm kiếm, phân tích kết quả, và trả về bằng chứng chính xác.**

Nói ngắn gọn:

```text
Không phải chatbot đơn thuần.
Mà là search engine + reasoning agent + multimedia evidence viewer.
```

---

# 2. Từ đề bài suy ra input của hệ thống

Đề bài nói “người dùng xử lý truy vấn thông tin”.

Vậy input chính của hệ thống là **truy vấn từ BTC/giám khảo/người dùng**.

Các dạng input có thể xảy ra:

## 2.1. Text query

Ví dụ:

```text
Tìm cảnh một người đang phát biểu trước màn hình xanh về trí tuệ nhân tạo.
```

Đây là dạng phổ biến nhất.

Hệ thống phải hiểu:

- người phát biểu;
- màn hình xanh;
- chủ đề trí tuệ nhân tạo;
- có thể cần hình ảnh, audio, OCR hoặc transcript.

## 2.2. Visual query

Ví dụ BTC đưa một ảnh hoặc đoạn video mẫu.

Hệ thống phải tìm phần tương tự trong kho dữ liệu.

Input có thể là:

```text
image query
video clip query
keyframe query
```

## 2.3. Question answering query

Ví dụ:

```text
Người phát biểu đang nói về chủ đề gì?
```

Hoặc:

```text
Biển hiệu trong cảnh này ghi nội dung gì?
```

Dạng này không chỉ cần tìm đúng đoạn, mà còn phải hiểu nội dung trong đoạn đó.

## 2.4. Temporal query

Ví dụ:

```text
Tìm đoạn sau khi người đàn ông bước lên sân khấu.
```

Dạng này cần hiểu quan hệ thời gian trước/sau trong video.

---

# 3. Từ input suy ra output cần trả về

Vì cuộc thi là retrieval challenge, output không thể chỉ là:

```text
Tôi đã tìm thấy cảnh đó.
```

Output phải là bằng chứng có thể chấm được.

Các output cần hỗ trợ:

## 3.1. Output cho KIS / tìm đúng khoảnh khắc

```json
{
  "video_id": "video_0342",
  "timestamp": 768.2,
  "frame_id": "video_0342_frame_18420",
  "confidence": 0.87
}
```

Tối thiểu cần có:

```text
video_id + timestamp
```

hoặc:

```text
frame_id
```

## 3.2. Output cho segment-level retrieval

Nếu đáp án là một đoạn video:

```json
{
  "video_id": "video_0342",
  "start_time": 763.0,
  "end_time": 773.0,
  "segment_id": "video_0342_seg_015"
}
```

## 3.3. Output cho VQA / Q&A

Nếu câu hỏi cần trả lời bằng text:

```json
{
  "answer": "Người phát biểu đang nói về ứng dụng AI trong đô thị thông minh.",
  "evidence_video_id": "video_0188",
  "timestamp": 201.4,
  "confidence": 0.81
}
```

## 3.4. Suy luận quan trọng

Vì output cần video/frame/timestamp/answer, hệ thống phải luôn lưu được quan hệ:

```text
video → segment → frame → timestamp → metadata/evidence
```

Nếu không thiết kế data model tốt từ đầu, về sau rất khó map kết quả search về format submit.

---

# 4. Từ dữ liệu multimedia suy ra kiến trúc dữ liệu

Đề bài nói dữ liệu gồm:

```text
hình ảnh + âm thanh + văn bản
```

Vậy ta phải chuyển mỗi modality thành dạng có thể tìm kiếm.

## 4.1. Video không thể search trực tiếp

Video là dữ liệu liên tục theo thời gian.

Muốn search video, ta cần phân rã nó thành các đơn vị nhỏ hơn:

```text
video
→ segment/shot
→ keyframe
→ embedding/caption/OCR/ASR
```

## 4.2. Cấu trúc video hợp lý

```text
video_id
│
├── segment_id
│   ├── start_time
│   ├── end_time
│   ├── keyframes
│   │   ├── frame_id
│   │   ├── timestamp
│   │   ├── image_path
│   │   └── visual_embedding
│   ├── caption
│   ├── OCR text
│   ├── ASR transcript
│   └── objects/concepts
```

## 4.3. Vì sao cần segment?

Nếu chỉ có frame riêng lẻ, hệ thống biết một ảnh đúng nhưng không biết đoạn video xung quanh.

Nếu chỉ có video, hệ thống biết video đúng nhưng không biết khoảnh khắc nào.

Segment là cầu nối giữa:

```text
frame-level evidence
và
video-level answer
```

## 4.4. Cách chia segment

Có ba cách:

### Cách 1: chia đều theo thời gian

```text
0–10s
10–20s
20–30s
```

Dễ làm nhưng có thể cắt ngang sự kiện.

### Cách 2: chia theo shot/chuyển cảnh

Phù hợp với video retrieval hơn vì mỗi segment tương ứng một cảnh.

### Cách 3: chia theo event/ngữ nghĩa

Tốt nhất nhưng khó hơn, cần model hoặc rule.

## 4.5. Kết luận thiết kế

Nên dùng hybrid:

```text
detect shot boundary
+ keyframe mỗi 1–2 giây
+ segment 5–15 giây
+ temporal expansion ±5–10 giây khi truy xuất
```

---

# 5. Từ “truy xuất thông tin chuyên sâu” suy ra không thể chỉ dùng CLIP

Nếu query là:

```text
Tìm cảnh một người phát biểu trước màn hình xanh.
```

Visual embedding có thể đủ.

Nhưng nếu query là:

```text
Tìm đoạn người phát biểu về trí tuệ nhân tạo trong giáo dục.
```

Visual embedding không đủ, vì chủ đề “trí tuệ nhân tạo trong giáo dục” nằm trong lời nói.

Cần ASR/transcript.

Nếu query là:

```text
Tìm cảnh có dòng chữ "Hội nghị chuyển đổi số".
```

Cần OCR.

Nếu query là:

```text
Người phát biểu đang nói về nội dung gì?
```

Cần ASR + LLM reasoning.

Vì vậy, từ đề bài suy ra hệ thống cần **multimodal indexing**, không phải chỉ visual search.

---

# 6. Các index bắt buộc suy ra từ từng loại dữ liệu

## 6.1. Hình ảnh/video frame

Cần:

```text
visual embedding index
object/concept index
caption index
```

Dùng để xử lý:

- cảnh;
- vật thể;
- màu sắc;
- bố cục;
- hành động;
- người/vật/sự kiện.

## 6.2. Âm thanh

Cần:

```text
ASR transcript index
audio event index nếu có thể
```

Dùng để xử lý:

- lời nói;
- nội dung phát biểu;
- tên riêng;
- chủ đề được nhắc đến.

## 6.3. Văn bản

Văn bản có thể đến từ:

```text
OCR trong video
metadata
caption
transcript
description
```

Cần:

```text
BM25 / full-text search
text embedding search
fuzzy matching
```

Dùng để xử lý:

- chữ trên màn hình;
- biển hiệu;
- tiêu đề slide;
- nội dung transcript;
- metadata mô tả video.

---

# 7. Từ yêu cầu “Trợ lý ảo” suy ra cần agent layer

Nếu chỉ có search engine, người dùng phải tự biết:

```text
query này nên search visual hay ASR?
có cần OCR không?
có cần mở rộng query không?
có cần tìm gần timestamp không?
```

Nhưng đề bài yêu cầu “trợ lý ảo thông minh”.

Vậy hệ thống cần một lớp agent để làm các việc này.

## 7.1. Agent không thay thế search engine

Agent không phải nơi lưu dữ liệu.

Agent là bộ điều phối:

```text
nhận query
→ hiểu intent
→ chọn công cụ
→ gọi retrieval modules
→ hợp nhất kết quả
→ kiểm tra bằng chứng
→ trả output
```

## 7.2. Agent cần làm gì?

Với query:

```text
Tìm đoạn người phát biểu trước màn hình xanh về trí tuệ nhân tạo.
```

Agent phải suy ra:

```json
{
  "query_type": "hybrid_retrieval",
  "visual_constraints": ["person", "speaking", "podium", "blue screen"],
  "audio_constraints": ["trí tuệ nhân tạo"],
  "ocr_constraints": ["AI", "trí tuệ nhân tạo", "hội nghị"],
  "search_plan": ["visual_search", "asr_search", "ocr_search", "caption_search"]
}
```

Sau đó agent gọi các tool:

```text
visual_search()
asr_search()
ocr_search()
caption_search()
fusion_rerank()
verify()
```

## 7.3. Vì sao gọi là agent?

Vì nó không chỉ trả lời text.

Nó có thể:

- chọn công cụ;
- sinh search plan;
- refine query;
- chạy nhiều search;
- so sánh kết quả;
- quyết định output cuối.

---

# 8. Từ hai hình thức thi suy ra hai interface cần xây

Đề bài có:

```text
hình thức truyền thống
+ hình thức tự động
```

Vậy hệ thống phải có ít nhất hai cách sử dụng.

---

## 8.1. Hình thức truyền thống → cần Human UI

Trong hình thức truyền thống, con người dùng tool để tìm kết quả.

Do đó cần UI dạng search dashboard:

```text
query box
+ result thumbnails
+ video preview
+ timeline
+ evidence panel
+ filter
+ submit/copy button
```

Không nên chỉ làm chat UI vì chat UI không đủ cho việc soi kết quả nhanh.

Một UI tốt cần trả lời được:

```text
kết quả nào đúng?
nằm ở video nào?
thời điểm nào?
bằng chứng là gì?
có frame lân cận không?
có transcript/OCR liên quan không?
```

## 8.2. Hình thức tự động → cần Agent API / batch runner

Nếu BTC thử nghiệm thi tự động giữa các trợ lý ảo, hệ thống có thể cần nhận input và trả output theo chuẩn máy đọc.

Vì vậy phải chuẩn bị:

```text
POST /agent/search
POST /agent/batch
CLI runner
Dockerized service
JSON input/output
```

Ví dụ API:

```http
POST /agent/search
```

Input:

```json
{
  "query_id": "q_001",
  "query": "Tìm cảnh người phát biểu trước màn hình xanh.",
  "query_type": "auto",
  "top_k": 5,
  "time_budget_seconds": 60
}
```

Output:

```json
{
  "query_id": "q_001",
  "results": [
    {
      "rank": 1,
      "video_id": "video_0342",
      "timestamp": 768.2,
      "frame_id": "video_0342_frame_18420",
      "confidence": 0.87
    }
  ]
}
```

## 8.3. Suy luận kiến trúc

Vì cần cả UI và automatic mode, không được viết logic search trong frontend.

Kiến trúc đúng:

```text
Human UI ───────┐
                ├── Agent/Retrieval API ── Retrieval Core ── Indexes
Auto Runner ────┘
```

Kiến trúc sai:

```text
Frontend chứa toàn bộ logic search
→ không thể dùng cho auto mode
→ khó batch evaluation
→ khó tích hợp với hệ thống BTC
```

---

# 9. Từ format LSC/VBS suy ra workflow thi

LSC/VBS thường có workflow:

```text
BTC đưa query
→ đội dùng hệ thống tìm kết quả
→ submit kết quả lên server
→ hệ thống chấm dựa trên đúng/sai và tốc độ
```

Vì vậy AI Challenge nhiều khả năng cũng xoay quanh:

```text
query
→ search
→ select result
→ submit video/frame/timestamp/answer
```

## 9.1. Workflow cho KIS

```text
Input:
mô tả một khoảnh khắc cụ thể

System:
search visual/caption/OCR/ASR
→ trả top candidates

Human/Agent:
chọn candidate tốt nhất

Submit:
video_id + timestamp / frame_id
```

## 9.2. Workflow cho AVS

```text
Input:
mô tả một loại sự kiện/chủ đề rộng

System:
tìm nhiều kết quả liên quan
→ xếp hạng

Submit:
ranked list video_id + timestamp
```

## 9.3. Workflow cho VQA

```text
Input:
câu hỏi về nội dung multimedia

System:
tìm segment liên quan
→ đọc visual/OCR/ASR
→ suy luận câu trả lời

Submit:
answer text + evidence
```

---

# 10. Từ workflow thi suy ra architecture tổng thể

Kiến trúc nên có 7 lớp:

```text
1. Data ingestion layer
2. Preprocessing layer
3. Indexing layer
4. Retrieval layer
5. Fusion/reranking layer
6. Agent/reasoning layer
7. UI/API/submission layer
```

## 10.1. Data ingestion layer

Nhiệm vụ:

```text
đọc video/dataset BTC
chuẩn hóa metadata
gán video_id
lưu path
kiểm tra lỗi dữ liệu
```

Output:

```text
raw video registry
metadata database
```

## 10.2. Preprocessing layer

Nhiệm vụ:

```text
chia segment
extract keyframe
tạo thumbnail
chạy OCR
chạy ASR
tạo caption
tạo embeddings
```

Output:

```text
frame table
segment table
visual embeddings
OCR text
ASR transcript
captions
```

## 10.3. Indexing layer

Nhiệm vụ:

```text
build FAISS/vector index
build BM25/full-text index
build metadata filters
build timestamp mapping
```

Output:

```text
visual index
text index
OCR index
ASR index
metadata index
```

## 10.4. Retrieval layer

Nhiệm vụ:

```text
nhận query
trả candidates từ từng modality
```

Các tool:

```text
visual_search(query)
caption_search(query)
ocr_search(query)
asr_search(query)
metadata_filter(query)
similar_frame_search(frame_id)
temporal_expand(timestamp)
```

## 10.5. Fusion/reranking layer

Nhiệm vụ:

```text
gộp kết quả từ nhiều nguồn
loại trùng
gán score
rerank top-K
```

Ví dụ:

```text
visual result nói video_0342 tại 768s đúng
ASR cũng nhắc "trí tuệ nhân tạo" quanh 770s
OCR có chữ "AI" quanh 765s

→ tăng confidence cho candidate này
```

## 10.6. Agent/reasoning layer

Nhiệm vụ:

```text
hiểu query
chọn search strategy
gọi tool
refine query
verify kết quả
trả output
```

## 10.7. UI/API/submission layer

Nhiệm vụ:

```text
hiển thị kết quả cho người dùng
hỗ trợ submit/copy
cung cấp API cho auto mode
export file submission
ghi log
```

---

# 11. Data model đề xuất

## 11.1. Video table

```json
{
  "video_id": "video_0342",
  "path": "/videos/video_0342.mp4",
  "duration": 900.0,
  "fps": 25,
  "source": "official_dataset"
}
```

## 11.2. Segment table

```json
{
  "segment_id": "video_0342_seg_015",
  "video_id": "video_0342",
  "start_time": 760.0,
  "end_time": 775.0,
  "representative_frame_id": "video_0342_frame_768"
}
```

## 11.3. Frame table

```json
{
  "frame_id": "video_0342_frame_768",
  "video_id": "video_0342",
  "segment_id": "video_0342_seg_015",
  "timestamp": 768.0,
  "image_path": "/frames/video_0342/768.jpg",
  "thumbnail_path": "/thumbs/video_0342/768.jpg"
}
```

## 11.4. Evidence table

```json
{
  "frame_id": "video_0342_frame_768",
  "caption": "Một người đang phát biểu trước màn hình xanh.",
  "ocr_text": "AI FOR SMART CITY",
  "objects": ["person", "microphone", "screen"],
  "asr_text_nearby": "ứng dụng trí tuệ nhân tạo trong đô thị thông minh"
}
```

---

# 12. Query processing workflow chi tiết

Với query:

```text
Tìm đoạn một người đang phát biểu trước màn hình xanh về trí tuệ nhân tạo.
```

## Step 1: Query understanding

Agent phân tích:

```json
{
  "intent": "find_video_segment",
  "visual": ["person", "speaking", "blue screen"],
  "audio": ["trí tuệ nhân tạo"],
  "ocr": ["AI", "trí tuệ nhân tạo"],
  "priority": ["visual", "asr", "caption", "ocr"]
}
```

## Step 2: Parallel retrieval

Chạy song song:

```text
visual_search("person speaking blue screen")
asr_search("trí tuệ nhân tạo")
caption_search("người phát biểu màn hình xanh")
ocr_search("AI trí tuệ nhân tạo")
```

## Step 3: Candidate generation

Mỗi tool trả về candidates:

```text
visual → video_0342 @ 768s
asr    → video_0342 @ 770s
caption→ video_0342 @ 769s
ocr    → video_0199 @ 120s
```

## Step 4: Fusion

Vì nhiều modality cùng trỏ tới video_0342 quanh 768–770s:

```text
candidate video_0342 @ 768s được tăng score
```

## Step 5: Temporal expansion

Mở rộng quanh candidate:

```text
768s ± 10s
```

Để kiểm tra đoạn đầy đủ.

## Step 6: Verification

Verifier kiểm tra:

```text
có người không?
có đang phát biểu không?
có màn hình xanh không?
ASR có nhắc AI không?
```

## Step 7: Output

```json
{
  "video_id": "video_0342",
  "timestamp": 768.2,
  "start_time": 763.0,
  "end_time": 773.0,
  "confidence": 0.87,
  "evidence": {
    "visual": "person speaking in front of blue screen",
    "asr": "trí tuệ nhân tạo",
    "ocr": "AI"
  }
}
```

---

# 13. Human UI suy ra từ workflow

Vì người thi phải tìm nhanh, UI cần phục vụ tốc độ.

## 13.1. UI không nên chỉ là chatbot

Chatbot chỉ tốt cho hội thoại, nhưng retrieval cần nhìn bằng chứng.

UI nên là:

```text
query input/chat box
+ top result grid
+ thumbnail
+ video preview
+ timeline
+ evidence
+ filters
+ submit/copy output
```

## 13.2. Layout đề xuất

```text
┌────────────────────────────────────────────┐
│ Query box                                  │
├────────────────────────────────────────────┤
│ Strategy detected: visual + ASR + OCR       │
├────────────────────────────────────────────┤
│ Result grid                                │
│ [thumb] video_0342 00:12:48 score 0.87      │
│ [thumb] video_0199 00:02:00 score 0.73      │
├────────────────────────────────────────────┤
│ Video preview + timeline ±10s              │
├────────────────────────────────────────────┤
│ Evidence: caption / OCR / ASR / objects     │
├────────────────────────────────────────────┤
│ Submit/copy: video_0342, 00:12:48           │
└────────────────────────────────────────────┘
```

## 13.3. Tính năng quan trọng

```text
hotkey
similar frame search
nearby timeline
candidate tray
query history
negative filtering
OCR/ASR quick filter
copy submission format
```

---

# 14. Auto-agent suy ra từ hình thức tự động

Vì BTC nói thử nghiệm thi tự động giữa các trợ lý ảo, cần thiết kế agent có interface máy đọc.

## 14.1. Agent API

```http
POST /agent/search
```

Input:

```json
{
  "query_id": "q_001",
  "query": "Tìm cảnh người phát biểu trước màn hình xanh.",
  "top_k": 5,
  "time_budget_seconds": 60
}
```

Output:

```json
{
  "query_id": "q_001",
  "results": [
    {
      "rank": 1,
      "video_id": "video_0342",
      "timestamp": 768.2,
      "confidence": 0.87
    }
  ]
}
```

## 14.2. Batch runner

```bash
python run_agent.py --input queries.json --output answers.json
```

## 14.3. Vì sao cần API?

Vì có thể BTC sẽ yêu cầu:

```text
đội tự chạy server
hoặc nộp Docker
hoặc chạy script batch
hoặc gọi API để test tự động
```

Nếu hệ thống có API rõ ràng, ta thích nghi được mọi kịch bản.

---

# 15. Từ yêu cầu “dữ liệu lớn” suy ra yêu cầu performance

Dữ liệu lớn nghĩa là không thể search brute-force từng frame chậm chạp.

Cần:

```text
offline preprocessing
vector index
full-text index
cache thumbnail
parallel retrieval
top-K reranking only
```

## 15.1. Nguyên tắc

Không chạy model nặng trên toàn dataset lúc query.

Đúng:

```text
query
→ search index nhanh lấy top 100–500
→ model nặng rerank top-K
```

Sai:

```text
query
→ chạy LVLM trên toàn bộ frame
```

## 15.2. Target performance

```text
search latency: < 1–2 giây
preview load: gần như tức thì
rerank top-K: vài giây
batch mode: có timeout rõ
```

---

# 16. Từ “dữ liệu đặc thù Việt Nam” suy ra cần Vietnamese-aware system

Đề bài nhấn mạnh:

```text
ngôn ngữ, âm thanh, hình ảnh đặc thù Việt Nam
```

Vậy cần xử lý:

```text
query tiếng Việt
từ đồng nghĩa Việt-Anh
ASR tiếng Việt
OCR tiếng Việt
địa danh/tên riêng Việt Nam
ngữ cảnh Việt Nam
```

Ví dụ:

```text
xe máy = motorbike/scooter
phát biểu = speaking/presentation/speech
hội nghị = conference/event/seminar
trí tuệ nhân tạo = AI/artificial intelligence
thành phố thông minh = smart city
```

Hệ thống nên có query expansion Việt-Anh.

---

# 17. Từ quyền lợi SoICT/MTAP suy ra cần research logging

Cuộc thi không chỉ trao giải, mà còn có khả năng chọn phương pháp tốt để trình bày/publish.

Vì vậy ngay từ đầu cần lưu:

```text
architecture
evaluation metrics
ablation study
latency
case studies
error analysis
agent logs
comparison baseline vs improved system
```

Nếu không log từ đầu, sau cuộc thi rất khó viết paper.

---

# 18. Kiến trúc hệ thống cuối cùng

```text
                        ┌─────────────────────┐
                        │ Human Search UI      │
                        └──────────┬──────────┘
                                   │
                        ┌──────────▼──────────┐
                        │ Agent API            │
                        │ /agent/search        │
                        │ /agent/batch         │
                        └──────────┬──────────┘
                                   │
                        ┌──────────▼──────────┐
                        │ Query Planner        │
                        │ intent + constraints │
                        └──────────┬──────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          ▼                        ▼                        ▼
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│ Visual Retrieval │      │ Text/OCR Retrieval │     │ ASR Retrieval   │
│ FAISS/Vector     │      │ BM25/Embedding     │     │ Transcript      │
└────────┬────────┘      └─────────┬────────┘      └────────┬────────┘
         │                         │                        │
         └─────────────────────────┼────────────────────────┘
                                   ▼
                        ┌─────────────────────┐
                        │ Fusion + Reranking   │
                        └──────────┬──────────┘
                                   ▼
                        ┌─────────────────────┐
                        │ Verifier             │
                        │ LVLM/LLM/evidence    │
                        └──────────┬──────────┘
                                   ▼
                        ┌─────────────────────┐
                        │ Answer Formatter     │
                        │ video/frame/time/QA  │
                        └─────────────────────┘
```

---

# 19. Tech stack suy ra từ kiến trúc

## Backend

```text
FastAPI
PostgreSQL or DuckDB
FAISS or Qdrant
Elasticsearch/OpenSearch/Tantivy
Redis cache
Celery/RQ workers
Docker Compose
```

## AI modules

```text
CLIP / SigLIP / EVA-CLIP for visual embedding
Whisper / Vietnamese ASR for audio
PaddleOCR / VietOCR for text in image
Qwen2.5-VL / InternVL / LLaVA for caption/verification
bge-m3 / multilingual-e5 for text embedding
LLM for query planning and reasoning
```

## Frontend

```text
Next.js / React
video player
thumbnail grid
timeline viewer
evidence panel
hotkey system
```

---

# 20. Roadmap xây dựng suy ra từ dependency

Không nên xây chatbot trước vì chatbot cần retrieval core phía sau.

Thứ tự đúng:

```text
1. Data schema
2. Ingestion pipeline
3. Keyframe/segment extraction
4. Embedding/OCR/ASR/caption generation
5. Indexing
6. Retrieval APIs
7. Fusion/reranking
8. Human UI
9. Agent planner
10. Auto API/batch runner
11. Mock contest/evaluation
```

## Phase 1: Baseline retrieval

Mục tiêu:

```text
text query → top keyframes → video_id + timestamp
```

## Phase 2: Multimodal retrieval

Thêm:

```text
caption search
OCR search
ASR search
metadata search
```

## Phase 3: Fusion + rerank

Thêm:

```text
multi-source score fusion
deduplication
temporal expansion
confidence
```

## Phase 4: Human UI

Thêm:

```text
result grid
video preview
evidence panel
copy/submit
hotkeys
```

## Phase 5: Auto-agent

Thêm:

```text
query planner
tool selection
batch API
automatic output
```

## Phase 6: Competition practice

Thêm:

```text
mock contest
query set
scoring
error analysis
performance tuning
```

---

# 21. MVP cần có

MVP không phải chatbot đẹp.

MVP đúng là:

```text
Nhập query tiếng Việt
→ hệ thống hiểu query
→ search visual/caption/OCR/ASR
→ trả top results có thumbnail
→ click xem video quanh timestamp
→ copy/submit video_id + timestamp
```

MVP API:

```text
POST /agent/search
input: query
output: top video_id + timestamp + confidence
```

---

# 22. Câu trả lời cuối cùng: chúng ta cần xây gì?

Từ đề bài chính thức, suy ra cần xây:

> **Một multimodal retrieval assistant cho dữ liệu video lớn, có khả năng hiểu truy vấn tiếng Việt, tìm kiếm trên hình ảnh/âm thanh/văn bản, hợp nhất và kiểm chứng kết quả, hiển thị bằng chứng cho người dùng, đồng thời có API để chạy tự động như một agent.**

Không phải chỉ chatbot.

Không phải chỉ CLIP search.

Không phải chỉ video player.

Mà là hệ thống gồm:

```text
Data pipeline
+ multimodal indexes
+ retrieval engine
+ agent planner
+ reranking/verifier
+ human search UI
+ auto-agent API
+ submission formatter
+ evaluation workflow
```

---

# 23. Nguyên tắc thiết kế quan trọng nhất

```text
Mọi kết quả search phải map được về:
video_id
timestamp
frame_id hoặc segment_id
evidence
confidence
```

Nếu hệ thống làm được điều này nhanh và ổn định, ta có nền tảng tốt để xử lý cả:

```text
KIS
AVS
VQA
traditional mode
automatic mode
```

---

# 24. Tóm tắt suy luận một dòng

```text
Vì đề bài yêu cầu trợ lý ảo truy xuất và phân tích dữ liệu lớn multimedia,
nên ta cần xây một agentic multimodal retrieval system:
video được phân rã thành segment/keyframe/transcript/OCR/caption,
mọi dữ liệu được index,
agent hiểu query và chọn tool tìm kiếm,
hệ thống fusion/rerank/verify kết quả,
UI/API trả về video_id + timestamp/frame/answer để submit.
```
