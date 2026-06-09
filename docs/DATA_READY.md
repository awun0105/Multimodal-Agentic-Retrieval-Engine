Dưới đây là **toàn bộ các loại data nên/ có thể sinh ra từ preprocessing system** để phục vụ project AI Challenge này. Mục tiêu là biến raw video/keyframe thành các lớp dữ liệu có thể search, filter, inspect evidence, copy result, và hỗ trợ Q&A/TRAKE/VKIS.

## 1. Raw / Source Data

Đây là dữ liệu gốc hoặc dữ liệu BTC cung cấp.

| Data                      | Ví dụ                   | Dùng để làm gì                                  |
| ------------------------- | ----------------------- | ----------------------------------------------- |
| Raw videos                | `.mp4`                  | Nguồn chính, fallback khi cần xem video         |
| Provided keyframes        | `.jpg`, `.png`          | Search/display chính                            |
| Provided metadata         | `.json`, `.csv`, `.pkl` | video id, frame id, timestamp, embedding nếu có |
| Provided embeddings       | CLIP vectors            | Dùng ngay để build vector index                 |
| Provided objects/concepts | object labels           | Filter/search theo object                       |
| Provided descriptions     | video description       | Text search                                     |
| Provided ASR/transcript   | text/audio transcript   | Search theo lời nói                             |
| Provided OCR              | text trong frame        | Search theo chữ                                 |

---

## 2. Video-Level Metadata

Một record cho mỗi video.

```json
{
  "video_id": "L01_V028",
  "video_path": "/data/videos/L01_V028.mp4",
  "duration_sec": 612.4,
  "fps": 25,
  "width": 1920,
  "height": 1080,
  "num_frames": 15310,
  "has_audio": true,
  "source": "btc_dataset"
}
```

Dùng để:

* map video id;
* browse keyframes cùng video;
* tính timestamp/frame;
* quản lý file path;
* kiểm tra thiếu file;
* group kết quả theo video.

---

## 3. Keyframe-Level Metadata

Một record cho mỗi keyframe.

```json
{
  "video_id": "L01_V028",
  "frame_id": 25300,
  "keyframe_id": "L01_V028_25300",
  "timestamp_sec": 1012.0,
  "image_path": "/data/keyframes/L01_V028/25300.jpg",
  "thumbnail_path": "/data/thumbnails/L01_V028/25300.webp",
  "width": 1280,
  "height": 720,
  "shot_id": "L01_V028_s012"
}
```

Dùng cho:

* result grid;
* mở keyframe;
* copy `video_id, frame_id`;
* tìm keyframe lân cận;
* TRAKE sequence;
* Q&A grounding.

Đây là data quan trọng nhất.

---

## 4. Thumbnail Data

Ảnh nhỏ để hiển thị nhanh trên UI.

| Data                   | Format gợi ý        |
| ---------------------- | ------------------- |
| thumbnail 160px        | `.webp` hoặc `.jpg` |
| thumbnail 320px        | `.webp`             |
| optional preview image | `.jpg`              |

Dùng cho:

* virtualized result grid;
* candidate basket;
* same-video strip;
* giảm RAM/browser memory;
* giảm load HDD.

Nên sinh thumbnail riêng, không dùng ảnh keyframe full-size trực tiếp.

---

## 5. Visual Embeddings

Vector biểu diễn hình ảnh/keyframe.

```json
{
  "keyframe_id": "L01_V028_25300",
  "model": "clip-vit-l14",
  "dim": 768,
  "vector_id": 982331
}
```

Dùng cho:

* text-to-image search;
* image/keyframe similarity;
* similar frame search;
* VKIS search;
* visual rerank.

Storage:

```text
FAISS index:
vector_id -> embedding

DB mapping:
vector_id -> video_id, frame_id, keyframe_path
```

---

## 6. Text Embeddings

Vector biểu diễn caption/OCR/ASR/description.

```json
{
  "doc_id": "caption_L01_V028_25300",
  "source_type": "caption",
  "video_id": "L01_V028",
  "frame_id": 25300,
  "model": "bge-m3",
  "vector_id": 120044
}
```

Dùng cho:

* semantic text search;
* query tiếng Việt/Anh;
* tìm theo mô tả dài;
* tìm theo ý nghĩa thay vì keyword exact.

Có thể tách nhiều index:

```text
caption_embedding.index
asr_embedding.index
ocr_embedding.index
metadata_embedding.index
```

---

## 7. Caption / Dense Description

Mô tả bằng ngôn ngữ tự nhiên cho keyframe hoặc shot.

```json
{
  "video_id": "L01_V028",
  "frame_id": 25300,
  "caption_vi": "Một người mặc đồ bảo hộ trắng đang đứng trong hang động.",
  "caption_en": "A person in white protective clothing is standing inside a cave.",
  "model": "qwen2.5-vl",
  "confidence": 0.82
}
```

Dùng cho:

* text search;
* evidence panel;
* semantic matching;
* query expansion;
* Q&A reasoning;
* TRAKE event matching.

Nên có caption tiếng Anh hoặc song ngữ vì nhiều model retrieval mạnh hơn với tiếng Anh.

---

## 8. Object / Concept Detection

Danh sách object/concept trong keyframe.

```json
{
  "video_id": "L01_V028",
  "frame_id": 25300,
  "objects": [
    {"label": "person", "score": 0.97, "bbox": [120, 80, 400, 600]},
    {"label": "helmet", "score": 0.75, "bbox": [180, 40, 260, 130]},
    {"label": "cave", "score": 0.62, "bbox": null}
  ]
}
```

Dùng cho:

* filter nhanh;
* object search;
* evidence;
* query clue matching;
* visual disambiguation.

Có thể lưu:

* object labels;
* bbox;
* confidence;
* Vietnamese aliases.

---

## 9. OCR Text

Text nhìn thấy trong keyframe.

```json
{
  "video_id": "L01_V028",
  "frame_id": 25300,
  "ocr_items": [
    {
      "text": "HỘI NGHỊ CHUYỂN ĐỔI SỐ",
      "normalized_text": "hoi nghi chuyen doi so",
      "bbox": [100, 50, 700, 120],
      "confidence": 0.91
    }
  ]
}
```

Dùng cho:

* tìm bảng hiệu;
* tìm logo/text trên slide;
* Q&A answer;
* evidence;
* exact/fuzzy search;
* nhận diện địa danh/tên tổ chức.

Nên sinh thêm:

* raw OCR text;
* normalized OCR text;
* no-accent text;
* lowercase text;
* bbox.

---

## 10. ASR / Transcript Data

Lời nói trong video.

```json
{
  "video_id": "L01_V028",
  "start_sec": 1008.0,
  "end_sec": 1020.5,
  "start_frame": 25200,
  "end_frame": 25512,
  "text": "Hôm nay chúng ta nói về chuyển đổi số trong giáo dục...",
  "language": "vi",
  "confidence": 0.84
}
```

Dùng cho:

* tìm theo lời nói;
* Q&A;
* video event description;
* phân tích nội dung;
* matching với các query có người phát biểu/phỏng vấn.

Nên có:

* transcript segment-level;
* word-level timestamps nếu có;
* normalized/no-accent transcript;
* English translation nếu cần.

---

## 11. Audio Event / Sound Tags

Không bắt buộc, nhưng hữu ích nếu đề có audio clue.

```json
{
  "video_id": "L05_V002",
  "start_sec": 35.2,
  "end_sec": 38.0,
  "audio_events": [
    {"label": "applause", "score": 0.88},
    {"label": "music", "score": 0.76}
  ]
}
```

Dùng cho:

* tiếng vỗ tay;
* nhạc;
* tiếng còi;
* tiếng động vật;
* tiếng xe;
* crowd cheering.

P2, không cần làm sớm nếu thiếu thời gian.

---

## 12. Shot / Segment Data

Nhóm keyframe thành shot hoặc segment.

```json
{
  "video_id": "L01_V028",
  "shot_id": "L01_V028_s012",
  "start_frame": 25000,
  "end_frame": 25800,
  "start_sec": 1000.0,
  "end_sec": 1032.0,
  "representative_frame_id": 25300,
  "keyframe_ids": ["L01_V028_25000", "L01_V028_25300", "L01_V028_25600"]
}
```

Dùng cho:

* group kết quả;
* tránh top 100 toàn frame gần nhau;
* TRAKE;
* Q&A context;
* same-video browsing.

---

## 13. Scene / Place / Environment Tags

Phân loại bối cảnh.

```json
{
  "video_id": "L01_V028",
  "frame_id": 25300,
  "scene_tags": [
    {"label": "cave", "score": 0.91},
    {"label": "indoor", "score": 0.72}
  ]
}
```

Dùng cho query kiểu:

* trong nhà/ngoài trời;
* sân vận động;
* hội trường;
* đường phố;
* nhà hàng;
* lớp học;
* hang động;
* bãi biển;
* sân bay.

Có thể lấy từ caption hoặc scene classifier.

---

## 14. Color / Visual Attribute Data

Dữ liệu màu sắc, thuộc tính thị giác.

```json
{
  "video_id": "L01_V028",
  "frame_id": 25300,
  "dominant_colors": ["white", "gray", "brown"],
  "attributes": ["protective suit", "helmet", "dark background"]
}
```

Dùng cho VKIS và Textual KIS:

* áo đỏ;
* nền xanh;
* xe màu trắng;
* màn hình màu xanh;
* cờ đỏ vàng.

Có thể sinh đơn giản bằng image color statistics + caption.

---

## 15. Face / Person Data

Tùy luật và mức an toàn riêng tư, có thể chỉ dùng internal cho clustering, không cần định danh người.

```json
{
  "video_id": "L01_V028",
  "frame_id": 25300,
  "persons": [
    {
      "person_track_id": "p_001",
      "bbox": [120, 80, 320, 600],
      "clothing": "white protective suit",
      "pose": "standing"
    }
  ]
}
```

Dùng cho:

* số người;
* người mặc gì;
* người xuất hiện lại;
* Q&A đếm người;
* TRAKE theo nhân vật.

Không nên tập trung định danh khuôn mặt nếu không cần.

---

## 16. Person / Object Tracking Data

Theo dõi object qua nhiều keyframes trong cùng video.

```json
{
  "video_id": "L01_V028",
  "track_id": "person_03",
  "label": "person",
  "frames": [
    {"frame_id": 25000, "bbox": [100, 80, 300, 600]},
    {"frame_id": 25300, "bbox": [110, 82, 310, 605]}
  ]
}
```

Dùng cho:

* TRAKE;
* chuỗi hành động;
* đếm object ổn định hơn;
* “người thứ nhất, người thứ hai…”;
* highlight thể thao.

P2/P3, chưa cần làm MVP.

---

## 17. Action / Event Tags

Nhận diện hành động/sự kiện.

```json
{
  "video_id": "L09_V001",
  "frame_id": 1850,
  "actions": [
    {"label": "running", "score": 0.86},
    {"label": "crossing finish line", "score": 0.73}
  ]
}
```

Dùng cho:

* người đang chạy;
* cắt bánh;
* bắt tay;
* phát biểu;
* nấu ăn;
* đá bóng;
* ghi bàn;
* trao giải.

Có thể sinh từ caption/LVLM thay vì action model chuyên dụng.

---

## 18. Entity Extraction Data

Entity từ caption/OCR/ASR/metadata.

```json
{
  "video_id": "L01_V028",
  "frame_id": 25300,
  "entities": [
    {"text": "TP.HCM", "type": "LOCATION", "source": "ocr"},
    {"text": "chuyển đổi số", "type": "TOPIC", "source": "asr"},
    {"text": "UNESCO", "type": "ORG", "source": "ocr"}
  ]
}
```

Dùng cho:

* tìm địa danh;
* tổ chức;
* người nổi tiếng;
* sự kiện;
* chủ đề nói đến.

---

## 19. Normalized Text Fields

Cho mọi text source: OCR, ASR, caption, metadata.

```json
{
  "raw": "Thành phố Hồ Chí Minh",
  "lowercase": "thành phố hồ chí minh",
  "no_accent": "thanh pho ho chi minh",
  "tokens": ["thành", "phố", "hồ", "chí", "minh"],
  "english_translation": "Ho Chi Minh City"
}
```

Dùng cho:

* tìm tiếng Việt không dấu;
* query sai dấu;
* query song ngữ;
* fuzzy search;
* BM25 tốt hơn.

Đây là data rất nên làm.

---

## 20. Query Expansion Dictionary

Từ điển đồng nghĩa Việt-Anh theo domain.

```json
{
  "xe máy": ["motorbike", "motorcycle", "scooter"],
  "phát biểu": ["speech", "speaker", "podium", "microphone", "presentation"],
  "múa lân": ["lion dance", "dragon dance", "festival"],
  "đám đông": ["crowd", "audience", "people gathering"]
}
```

Dùng lúc search.

Có thể sinh thủ công + LLM hỗ trợ.

---

## 21. Search Documents

Đây là document đã gộp để đưa vào text index.

```json
{
  "doc_id": "kf_L01_V028_25300",
  "video_id": "L01_V028",
  "frame_id": 25300,
  "text": "caption: person in white suit inside cave. ocr: ... asr: french interview...",
  "fields": {
    "caption": "...",
    "ocr": "...",
    "asr": "...",
    "objects": "person helmet cave",
    "scene": "cave indoor"
  }
}
```

Dùng cho:

* BM25;
* hybrid search;
* evidence retrieval.

Nên có cả:

* keyframe document;
* shot document;
* video document;
* ASR segment document.

---

## 22. Search Index Files

Output thực tế của preprocessing.

```text
/data/indexes/
  visual_frame.faiss
  visual_frame_mapping.parquet
  caption_text.index
  ocr_text.index
  asr_text.index
  metadata.duckdb
```

Dùng trực tiếp khi runtime.

---

## 23. Candidate Diversification Data

Dữ liệu giúp tránh kết quả trùng lặp.

```json
{
  "video_id": "L01_V028",
  "cluster_id": "cluster_881",
  "representative_frame_id": 25300,
  "member_frame_ids": [25280, 25300, 25320]
}
```

Dùng cho:

* top 100 đa dạng;
* group result theo video/shot;
* tránh result grid toàn ảnh giống nhau.

---

## 24. Similarity Graph / Nearest Neighbor Data

Precompute top similar frames cho mỗi keyframe.

```json
{
  "keyframe_id": "L01_V028_25300",
  "similar_keyframes": [
    {"keyframe_id": "L02_V011_1200", "score": 0.91},
    {"keyframe_id": "L03_V005_8800", "score": 0.87}
  ]
}
```

Dùng cho:

* “find similar” nhanh;
* VKIS;
* mở rộng candidate.

P2, nếu index search đủ nhanh thì không cần precompute.

---

## 25. Timeline Navigation Data

Dữ liệu điều hướng keyframe theo video.

```json
{
  "video_id": "L01_V028",
  "ordered_keyframes": [
    {"frame_id": 100, "timestamp": 4.0},
    {"frame_id": 250, "timestamp": 10.0},
    {"frame_id": 400, "timestamp": 16.0}
  ]
}
```

Dùng cho:

* same-video strip;
* TRAKE;
* nearby frames;
* clue verification.

Rất quan trọng.

---

## 26. TRAKE Event Candidate Data

Sinh khi chạy query hoặc có thể precompute nhẹ.

```json
{
  "query_id": "trake-001",
  "video_id": "L10_V001",
  "events": [
    {
      "event_index": 1,
      "description": "nguyên liệu đầu tiên được cho vào chảo",
      "candidate_frames": [1200, 1250, 1300]
    },
    {
      "event_index": 2,
      "description": "nguyên liệu thứ hai được cho vào chảo",
      "candidate_frames": [1850, 1900, 1950]
    }
  ]
}
```

Dùng cho:

* chọn sequence;
* copy row TRAKE;
* đảm bảo frame tăng dần.

---

## 27. Q&A Candidate Answer Data

Sinh từ Q&A helper.

```json
{
  "query_id": "qa-003",
  "candidate": {
    "video_id": "L02_V011",
    "frame_id": 1200
  },
  "answers": [
    {
      "raw_answer": "Năm người",
      "normalized_answer": "5",
      "confidence": 0.78,
      "source": "visual_counting"
    }
  ]
}
```

Dùng cho:

* gợi ý answer;
* copy Q&A row;
* check answer format.

---

## 28. Search Run Logs

Log mỗi lần user search.

```json
{
  "run_id": "search_20260609_001",
  "query": "người áo trắng hang động",
  "search_mode": "hybrid",
  "top_k": 100,
  "latency_ms": 842,
  "weights": {
    "visual": 0.4,
    "caption": 0.3,
    "ocr": 0.1,
    "asr": 0.1,
    "object": 0.1
  },
  "top_results": [
    {"video_id": "L01_V028", "frame_id": 25300, "score": 0.88}
  ]
}
```

Dùng cho:

* debug;
* cải thiện retrieval;
* replay query;
* mock contest analysis.

---

## 29. Query Session Data

Cho các clue reveal từng phần.

```json
{
  "session_id": "final_query_01",
  "query_type": "tkis",
  "clues": [
    "Một người mặc đồ bảo hộ trắng.",
    "Bối cảnh là một hang động dài khoảng 1.6km."
  ],
  "user_queries": [
    "white protective suit cave",
    "người áo trắng hang động"
  ],
  "pinned_candidates": [
    {"video_id": "L01_V028", "frame_id": 25300}
  ]
}
```

Dùng cho:

* progressive clue;
* query history;
* candidate basket theo query.

---

## 30. Config / Rule Data

Vì 2026 chưa chắc giống 2025, rules phải cấu hình.

```yaml
query_types:
  kis:
    copy_formats:
      - "{video_id},{frame_id}"
  qa:
    answer_max_length: 100
    copy_formats:
      - "{video_id},{frame_id},{answer}"
  trake:
    require_same_video: true
    require_frame_order: true
```

Dùng cho:

* copy helper;
* optional CSV export;
* validation;
* tránh hard-code.

---

## 31. Evaluation Ground Truth / Internal Benchmark

Tự tạo cho luyện tập.

```json
{
  "query_id": "mock_tkis_001",
  "query": "người mặc áo đỏ đứng cạnh xe buýt",
  "type": "tkis",
  "ground_truth": [
    {
      "video_id": "L03_V002",
      "frame_start": 1500,
      "frame_end": 1800
    }
  ]
}
```

Dùng cho:

* Recall@K;
* time-to-answer;
* so sánh fusion weight;
* test regression khi đổi model/index.

---

## 32. Health / Inventory Data

Data kiểm tra dataset có đầy đủ không.

```json
{
  "video_id": "L01_V028",
  "video_exists": true,
  "keyframe_count": 320,
  "embedding_count": 320,
  "ocr_count": 318,
  "caption_count": 320,
  "asr_segments": 25,
  "missing_files": []
}
```

Dùng cho:

* phát hiện lỗi preprocessing;
* tránh search ra frame không có file;
* audit index.

---

# Ưu tiên theo giai đoạn

## MVP bắt buộc

```text
1. video metadata
2. keyframe metadata
3. thumbnails
4. visual embeddings
5. FAISS index + mapping
6. caption/text documents
7. text index
8. timeline navigation data
9. query session data
10. candidate basket data
```

## Nên có sớm

```text
11. OCR
12. ASR/transcript
13. normalized text
14. object/concept tags
15. evidence bundle
16. search logs
17. copy/export config
```

## Nâng cấp sau

```text
18. dense caption by LVLM
19. text embeddings
20. scene tags
21. action/event tags
22. person/object tracking
23. TRAKE event candidates
24. Q&A answer candidates
25. similarity graph
26. audio event tags
```

## Không nên ưu tiên sớm

```text
- full video preview cache
- full-frame extraction dày đặc
- realtime LVLM cho mọi result
- face identification
- object tracking toàn dataset
- precompute nearest neighbor cho mọi frame nếu FAISS đã đủ nhanh
```

# Kết luận

Preprocessing system nên sinh ra 5 nhóm data chính:

```text
1. Media data:
   videos, keyframes, thumbnails, timeline

2. Retrieval data:
   visual embeddings, text embeddings, FAISS index, text index

3. Understanding data:
   captions, OCR, ASR, objects, scenes, actions, entities

4. Interaction data:
   query sessions, candidate basket, search logs, copy rows

5. Config/evaluation data:
   rules, retrieval weights, benchmark, health reports
```

Trong đó, với constraint RAM/SSD của bạn, quan trọng nhất là:

```text
keyframe metadata + thumbnails + visual index + text index + evidence text
```

Còn video preview, LVLM realtime, tracking sâu nên để sau.

Nên chia thành **4 nơi lưu chính**, không lưu tất cả vào một DB.

```text
1. HDD/File system    → video, keyframe, thumbnail, audio, file lớn
2. Metadata DB        → video_id, frame_id, timestamp, path, caption, OCR, ASR
3. Vector index       → embedding để search semantic
4. Text index         → OCR/ASR/caption để search keyword/full-text
```

## Kiến trúc lưu trữ khuyến nghị

```text
/data/
  raw/
    videos/              # HDD
    keyframes/           # HDD
    thumbnails/          # HDD hoặc SSD cache

  db/
    metadata.duckdb      # SSD nếu có
    app.sqlite           # session, basket, history

  indexes/
    visual.faiss         # SSD
    visual_mapping.parquet
    text_index/          # SQLite FTS / Tantivy / BM25

  cache/
    recent_thumbnails/   # SSD nếu có
    search_cache/

  runs/
    search_logs/
    eval_logs/

  exports/
    copied_results/
    submissions_optional/
```

---

# 1. File lớn: lưu bằng filesystem

Không đưa ảnh/video vào DB.

## Lưu ở HDD

```text
/data/raw/videos/L01/L01_V028.mp4
/data/raw/keyframes/L01_V028/00025300.jpg
/data/raw/thumbnails/L01_V028/00025300.webp
```

DB chỉ lưu đường dẫn:

```json
{
  "video_id": "L01_V028",
  "frame_id": 25300,
  "keyframe_path": "/data/raw/keyframes/L01_V028/00025300.jpg",
  "thumb_path": "/data/raw/thumbnails/L01_V028/00025300.webp"
}
```

Lý do:

* video/keyframe rất nặng;
* DB sẽ phình to nếu nhét ảnh vào;
* filesystem đọc ảnh/video tốt hơn;
* dễ backup/chuyển ổ.

---

# 2. Metadata: lưu vào DuckDB hoặc SQLite

Với máy 16–25GB RAM, mình khuyên:

## Giai đoạn đầu

Dùng **DuckDB + Parquet** hoặc **SQLite**.

| Loại                      | Khuyên dùng    |
| ------------------------- | -------------- |
| metadata phân tích lớn    | DuckDB         |
| session/app state nhỏ     | SQLite         |
| production nhiều user hơn | PostgreSQL sau |

## Các bảng chính

```text
videos
keyframes
captions
ocr_texts
asr_segments
objects
query_sessions
candidates
search_runs
```

## Ví dụ schema tối thiểu

```sql
videos(
  video_id TEXT PRIMARY KEY,
  video_path TEXT,
  duration_sec REAL,
  fps REAL,
  width INTEGER,
  height INTEGER
);

keyframes(
  keyframe_id TEXT PRIMARY KEY,
  video_id TEXT,
  frame_id INTEGER,
  timestamp_sec REAL,
  keyframe_path TEXT,
  thumbnail_path TEXT,
  shot_id TEXT
);

captions(
  keyframe_id TEXT,
  caption_vi TEXT,
  caption_en TEXT,
  model TEXT
);

ocr_texts(
  keyframe_id TEXT,
  text TEXT,
  normalized_text TEXT,
  confidence REAL
);

asr_segments(
  video_id TEXT,
  start_sec REAL,
  end_sec REAL,
  start_frame INTEGER,
  end_frame INTEGER,
  text TEXT,
  normalized_text TEXT
);

objects(
  keyframe_id TEXT,
  label TEXT,
  score REAL,
  bbox TEXT
);
```

---

# 3. Vector embeddings: không lưu trực tiếp trong DB chính

Embedding nên lưu thành:

```text
FAISS index + mapping file
```

Ví dụ:

```text
/data/indexes/visual_frame.faiss
/data/indexes/visual_frame_mapping.parquet
```

## Mapping file

```text
vector_id | video_id | frame_id | keyframe_id | timestamp_sec
0         | L01_V028 | 25300    | L01_V028_25300 | 1012.0
1         | L01_V028 | 25400    | L01_V028_25400 | 1016.0
```

Lý do:

* FAISS search nhanh;
* mapping tách riêng dễ rebuild;
* DB không bị nặng;
* có thể đổi model/index mà không ảnh hưởng metadata.

Nếu có nhiều loại embedding:

```text
visual_clip.faiss
visual_siglip.faiss
caption_bge.faiss
asr_bge.faiss
ocr_bge.faiss
```

Nhưng MVP chỉ cần:

```text
visual.faiss
visual_mapping.parquet
```

---

# 4. Text search: lưu trong text index riêng

OCR/ASR/caption cần search keyword/fuzzy/full-text.

Có 3 lựa chọn:

## Option A — đơn giản nhất

SQLite FTS5.

```text
/data/indexes/text_fts.sqlite
```

Phù hợp MVP.

## Option B — mạnh và nhẹ

Tantivy.

```text
/data/indexes/tantivy_text_index/
```

Rất hợp nếu muốn search nhanh, không cần chạy OpenSearch.

## Option C — nặng hơn

OpenSearch/Elasticsearch.

Không khuyên dùng sớm vì RAM ít.

Với RAM 16–25GB, nên chọn:

```text
DuckDB/SQLite + FAISS + SQLite FTS hoặc Tantivy
```

Không nên dùng OpenSearch sớm.

---

# 5. App state: lưu riêng, nhẹ

Các dữ liệu do người dùng tạo trong lúc thi:

```text
query history
candidate basket
copy rows
notes
current session
```

Nên lưu vào SQLite:

```text
/data/db/app.sqlite
```

Ví dụ:

```sql
query_sessions(
  session_id TEXT PRIMARY KEY,
  query_type TEXT,
  notes TEXT,
  created_at TEXT
);

search_runs(
  run_id TEXT PRIMARY KEY,
  session_id TEXT,
  query_text TEXT,
  search_mode TEXT,
  created_at TEXT
);

candidates(
  candidate_id TEXT PRIMARY KEY,
  session_id TEXT,
  video_id TEXT,
  frame_id INTEGER,
  answer TEXT,
  note TEXT,
  rank INTEGER,
  score REAL
);
```

Tách `app.sqlite` khỏi `metadata.duckdb` để:

* dễ reset session;
* không đụng metadata/index;
* dễ backup trước khi thi.

---

# 6. Cách tổ chức storage thực tế

## Bản gọn, nên dùng trước

```text
/data/
  media/
    videos/
    keyframes/
    thumbnails/

  db/
    metadata.duckdb
    app.sqlite

  indexes/
    visual.faiss
    visual_mapping.parquet
    text_fts.sqlite

  config/
    paths.yaml
    retrieval_weights.yaml
    export_rules.yaml

  logs/
    search_runs.jsonl

  exports/
```

Đây là cấu trúc đủ tốt cho MVP.

---

# 7. Data nào cần load vào RAM?

Không load toàn bộ.

## Load vào RAM

```text
FAISS index nếu vừa RAM
small config
recent search results
LRU thumbnail cache nhỏ
hot metadata cache
```

## Không load vào RAM

```text
raw videos
full keyframes
all thumbnails
all captions
all OCR
all ASR
all embeddings raw numpy
```

## Nếu FAISS index quá lớn

Dùng:

```text
FAISS mmap / IVF / PQ
hoặc chia index theo batch/dataset
hoặc dùng vector index trên SSD
```

---

# 8. Quy tắc truy cập runtime

Khi search:

```text
Query
→ Search FAISS/Text index
→ lấy vector_id/doc_id
→ lookup metadata DB
→ trả video_id/frame_id/path/evidence
→ UI lazy load thumbnail
```

Không bao giờ:

```text
Search → load toàn bộ ảnh
Search → load toàn bộ video
Search → scan toàn bộ filesystem
```

---

# 9. Gợi ý chọn stack storage

## MVP nên chọn

```text
Metadata: DuckDB
App state: SQLite
Vector: FAISS
Text search: SQLite FTS5 hoặc Tantivy
Media files: HDD filesystem
Cache/index: SSD nếu có
```

## Vì sao không PostgreSQL/OpenSearch ngay?

Vì:

* RAM ít;
* setup nặng;
* tăng dependency;
* chưa chắc cần;
* local/LAN app cần đơn giản và ổn định.

Sau này nếu dataset lớn hơn mới đổi.

---

# 10. Mapping giữa các loại data

Tất cả nên nối bằng khóa chung:

```text
video_id
frame_id
keyframe_id = video_id + "_" + frame_id
```

Ví dụ:

```text
keyframes.keyframe_id
captions.keyframe_id
ocr_texts.keyframe_id
objects.keyframe_id
visual_mapping.keyframe_id
candidates.keyframe_id
```

ASR thì gắn theo video/time range:

```text
asr_segments.video_id
asr_segments.start_frame
asr_segments.end_frame
```

Khi click keyframe, lấy ASR gần nhất bằng:

```sql
WHERE video_id = ?
AND start_frame <= selected_frame
AND end_frame >= selected_frame
```

hoặc lấy window ±30 giây.

---

# 11. Storage theo priority

## P0 bắt buộc

```text
media/videos
media/keyframes
media/thumbnails
metadata.duckdb:
  videos
  keyframes
visual.faiss
visual_mapping.parquet
text_fts.sqlite:
  captions / OCR / ASR nếu có
app.sqlite:
  sessions / candidates / history
```

## P1 nên có

```text
captions table
ocr_texts table
asr_segments table
objects table
normalized text fields
search_runs logs
```

## P2 sau

```text
scene tags
action tags
person/object tracks
similarity graph
q&a answer candidates
trake event candidates
```

---

# 12. Kết luận

Không nên nghĩ “nhiều data = một database khổng lồ”.

Nên chia như sau:

```text
Filesystem:
  file lớn: video, keyframe, thumbnail

DuckDB:
  metadata phân tích: video, frame, caption, OCR, ASR, object

SQLite:
  app state: query session, candidate basket, history

FAISS:
  vector search

SQLite FTS / Tantivy:
  text search

JSONL:
  logs, debug, search runs
```

Kiến trúc lưu trữ gọn nhất:

```text
HDD  = raw media
SSD  = DB + index + cache
RAM  = index hot path + current result only
```

Đây là cách vừa dễ bảo trì, vừa không tràn RAM, vừa phù hợp app local/LAN của bạn.
