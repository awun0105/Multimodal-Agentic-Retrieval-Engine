Mình nói lại chi tiết hơn: **trước khi build runtime system, project phải có một “App-ready Data Contract” rõ ràng**. Nếu không, UI/backend/retrieval sẽ bị build trên giả định mơ hồ và sau này khi có data thật sẽ phải sửa rất nhiều.
Nên dùng **SQLite**, không nên dùng **thuần JSON metadata** cho runtime app.

-----

JSON vẫn có chỗ dùng, nhưng chỉ nên dùng cho **raw input, staging output, manifests, validation reports, hoặc intermediate artifacts**. Còn khi app thật chạy để search, xem keyframe, lưu candidate, lưu query session, map FAISS result về video/frame, search OCR/ASR/caption thì nên dùng **SQLite WAL + SQLite FTS5**.

Lý do đơn giản: hệ thống của mình không chỉ đọc metadata một lần. Nó phải search liên tục, join nhiều loại dữ liệu, lưu trạng thái người dùng, hỗ trợ nhiều teammate qua LAN, hỗ trợ agent mode, và xử lý các loại query như Textual KIS, Q&A, TRAKE, VKIS. Tài liệu rules cũng nói hệ thống cần interactive/manual mode, automatic/agent mode, text query search, frame result grid, video/keyframe/timeline inspection, evidence OCR/ASR/caption/object/metadata, candidate saving, query sessions và export configurable.  JSON thuần sẽ rất khó làm các việc này một cách nhanh, ổn định và dễ debug.

Cách hiểu đúng là: **JSON là format trao đổi và staging; SQLite là catalog/runtime database; FAISS là vector index; FTS5 là text index; file system là nơi chứa video/ảnh lớn.**

Ví dụ khi BTC cung cấp data, ta có thể nhận rất nhiều thứ: video `.mp4`, keyframes `.jpg`, metadata `.json/.csv`, object detection `.json`, OCR, ASR, captions, CLIP embeddings. Những file này ban đầu có thể rất lộn xộn. Preprocessing sẽ đọc chúng, chuẩn hóa ID, kiểm tra path, tạo thumbnail, build embedding, build FAISS, rồi xuất ra một bộ **app-ready artifacts**. Runtime app chỉ đọc bộ app-ready này, không scan raw folder lung tung mỗi lần search.

Nên hình dung như sau: video và ảnh lớn nằm trên HDD, ví dụ trong `${AIC_DATA_ROOT}`. SQLite và FAISS nằm ở `${AIC_RUNTIME_ROOT}`, tốt nhất là SSD nếu có. SQLite không lưu đường dẫn tuyệt đối như `D:/AIC2026/...` hay `/mnt/hdd/...`; nó chỉ lưu logical reference như `videos/L01_V028.mp4`, `keyframes/L01_V028/025300.jpg`, `thumbnails/L01_V028/025300.webp`. Backend đọc config để biết `${AIC_DATA_ROOT}` nằm ở đâu, rồi `LocalFileMediaStore` sẽ resolve logical ref đó thành file thật trên HDD. Nhờ vậy sau này đổi ổ cứng, đổi máy, hoặc thêm MinIO thì không phải migrate toàn bộ database.

Dữ liệu trung tâm nhất là **keyframe**. Mọi thứ nên map về keyframe. Một keyframe nên có `video_id`, `frame_id`, `keyframe_id`, `timestamp_sec`, `keyframe_ref`, `thumbnail_ref`. Ví dụ:

```text
video_id = "L01_V028"
frame_id = 25300
keyframe_id = "L01_V028:25300"
keyframe_ref = "keyframes/L01_V028/025300.jpg"
thumbnail_ref = "thumbnails/L01_V028/025300.webp"
```

`video_id + frame_id` quan trọng vì đây là thứ cần copy/submit. Các format KIS, Q&A, TRAKE đều xoay quanh video name và frame ID; Q&A thêm answer, TRAKE thêm chuỗi frame theo thứ tự thời gian.  `keyframe_id` thì tiện cho database và API.

Với SQLite, ta sẽ có các bảng chính như `videos`, `keyframes`, `captions`, `ocr_texts`, `asr_segments`, `objects`, `embedding_indexes`, `vector_map`, `query_sessions`, `query_clues`, `search_runs`, `search_results`, `candidates`, `agent_runs`. Các bảng này không phải để “làm màu”, mà để giải quyết mapping thực tế.

Ví dụ bảng `videos` lưu thông tin video: `video_id`, `video_ref`, title, description, duration, fps, width, height. Bảng `keyframes` lưu từng keyframe: `keyframe_id`, `video_id`, `frame_id`, timestamp, refs tới ảnh và thumbnail. Bảng `captions` lưu caption theo `keyframe_id`. Bảng `ocr_texts` lưu chữ nhận diện được trên keyframe. Bảng `asr_segments` lưu transcript theo đoạn thời gian trong video, vì ASR không gắn 1-1 với keyframe mà gắn với `video_id + start_sec + end_sec`. Bảng `objects` lưu object/concept như person, car, microphone, screen, sign, stage.

Bảng cực kỳ quan trọng là `vector_map`. FAISS không biết video nào, frame nào. FAISS chỉ trả về số dòng vector, ví dụ `vector_id = 123456`. Muốn biết vector đó là keyframe nào, bắt buộc phải có mapping:

```text
FAISS vector_id
-> SQLite vector_map
-> keyframe_id
-> video_id + frame_id
-> keyframe_ref + thumbnail_ref
-> caption/OCR/ASR/object evidence
```

Nếu dùng JSON thuần, mỗi lần FAISS trả về vector IDs, backend sẽ phải tự load file JSON mapping, parse, lookup trong memory hoặc tự build dict. Làm được ở demo nhỏ, nhưng khi data lớn, nhiều index, nhiều teammate search, cần lưu search history/candidate, cách này rất dễ rối.

Text search cũng vậy. Nếu dùng JSON, muốn tìm OCR/caption/ASR thì hoặc phải scan toàn bộ JSON, hoặc tự build BM25/index thủ công. Trong khi SQLite FTS5 giải quyết tốt hơn: ta tạo `caption_fts`, `ocr_fts`, `asr_fts`, `object_fts`, `metadata_fts`, hoặc một bảng `evidence_fts` chung. Khi user search “bảng hiệu màu đỏ”, “phỏng vấn tiếng Pháp”, “AI Challenge”, “người cầm micro”, backend có thể query FTS5 rất nhanh, trả ra `keyframe_id` hoặc `video_id`, rồi join sang bảng keyframes/evidence.

Luồng search sẽ như thế này. Nếu user nhập query visual như “người mặc áo đỏ đứng trên sân khấu”, backend encode query bằng CLIP/SigLIP text encoder, gọi FAISS, nhận về danh sách `vector_id`. Sau đó lấy `vector_map` trong SQLite để biết các vector đó tương ứng keyframe nào. Rồi lấy thumbnail/keyframe/evidence từ SQLite và media store để trả về result grid.

Nếu user search text như “chữ trên màn hình là chuyển đổi số” hoặc “người nói về pin lithium”, backend query SQLite FTS5 trên OCR/ASR/caption/metadata. Kết quả text search sẽ trả về candidate keyframe hoặc ASR segment. Nếu là ASR segment, nó cần map từ `video_id + start_sec/end_sec` sang các keyframe gần timestamp đó. Sau đó cũng trả về cùng một result object: `video_id`, `frame_id`, thumbnail, score, evidence.

Hybrid search là gộp hai luồng trên. Backend lấy candidate từ FAISS visual search, candidate từ caption FTS, OCR FTS, ASR FTS, object search, rồi normalize score và fuse lại. Kết quả cuối cùng vẫn phải quy về `keyframe_id`. Đây là lý do data model phải lấy keyframe làm trung tâm.

Còn JSON metadata thuần thì nên dùng ở các chỗ như: file BTC cung cấp ban đầu, output OCR theo shard, output ASR theo shard, caption generated theo shard, `embedding_manifest.jsonl`, `validation_report.json`, `visual_index_manifest.json`. Những thứ này là **rebuildable artifacts** hoặc **staging artifacts**. Chúng tốt cho preprocessing, audit, debug, nhưng không nên là runtime source of truth cho app.

DuckDB nằm ở tầng preprocessing/staging. Nó hữu ích khi cần gom nhiều file JSON/CSV/Parquet/JSONL, join dữ liệu, validate missing media, thống kê số video/keyframe, kiểm tra duplicate, tạo bảng sạch rồi đẩy sang SQLite. Nhưng khi app chạy, SQLite là source of truth nhẹ hơn, dễ deploy hơn, phù hợp local/LAN hơn.

Nói bằng một ví dụ end-to-end:

BTC đưa video `L01_V028.mp4`, keyframe `025300.jpg`, object JSON, OCR JSON, ASR transcript, embedding. Preprocessing sẽ chuẩn hóa thành:

```text
video_id = L01_V028
frame_id = 25300
keyframe_id = L01_V028:25300
video_ref = videos/L01_V028.mp4
keyframe_ref = keyframes/L01_V028/025300.jpg
thumbnail_ref = thumbnails/L01_V028/025300.webp
```

Trong SQLite có row ở `videos`, row ở `keyframes`, nhiều row ở `captions/ocr_texts/objects`, ASR segment ở `asr_segments`, vector mapping ở `vector_map`. Trong FAISS có vector tại `vector_id = 123456`. Trong `vector_map` có:

```text
index_name = visual_clip
vector_id = 123456
keyframe_id = L01_V028:25300
video_id = L01_V028
frame_id = 25300
```

Khi user search, app không cần biết ảnh nằm thật ở ổ nào. UI gọi:

```http
GET /api/media/thumbnail/L01_V028:25300
```

Backend lấy `thumbnail_ref` trong SQLite, dùng `LocalFileMediaStore(root=${AIC_DATA_ROOT}/processed/media)` để đọc file thật từ HDD, rồi stream về browser. Nếu sau này dùng MinIO, chỉ đổi implementation của MediaStore, UI/retrieval không cần đổi.

Vậy câu trả lời cuối cùng là: **không nên dùng thuần JSON metadata cho runtime**. Dùng JSON thuần chỉ hợp khi project còn rất nhỏ hoặc chỉ prototype một notebook. Với hệ thống thi thật, cần search nhanh, evidence rõ, candidate basket, query sessions, nhiều teammate, agent mode, output helper, thì nên dùng **SQLite WAL + SQLite FTS5 + FAISS + LocalFileMediaStore**, và **DuckDB cho preprocessing**.

Quyết định nên ghi vào docs:

```text
Use SQLite WAL as the runtime source of truth for metadata, app state, query sessions, candidates, evidence lookup, and vector mapping.

Use SQLite FTS5 for runtime text search over captions, OCR, ASR, objects, and metadata.

Use FAISS for visual vector search.

Use DuckDB for preprocessing, staging, analytics, validation, and artifact generation.

Use JSON/JSONL/Parquet only for raw input, staging, manifests, validation reports, and rebuildable intermediate artifacts.

Do not use pure JSON metadata as the runtime database.

Do not store absolute media paths in SQLite. Store logical media refs only and resolve them through MediaStorePort.
```

Thứ tự triển khai đúng là: trước hết chốt data contract, ID convention và mapping; sau đó tạo seed dataset nhỏ; rồi tạo SQLite schema; rồi build media API; sau đó mới làm UI vertical slice, FAISS search, FTS5 search, hybrid search và agent. Runtime app chỉ nên đọc **app-ready artifacts**, không đọc raw dataset lung tung.

-----

Điểm cần chốt lại cho đúng:

```text
Repo/app không chứa video/keyframe/thumbnail lớn.
Video/ảnh lớn nằm ngoài repo, dưới external data root, thường là HDD.
SQLite + FAISS + FTS5/runtime hot artifacts ưu tiên nằm ở runtime root, tốt nhất là SSD nếu đủ chỗ.
SQLite chỉ lưu logical media references, không lưu absolute machine-specific paths.
Backend dùng config + MediaStorePort để resolve logical refs sang HDD path hoặc MinIO key sau này.
```

Repo hiện tại đã định hướng đúng: ingestion biến official/raw dataset thành **SQLite runtime artifacts + FAISS + SQLite FTS5 + media assets** để app có thể search/inspect mà không scan raw folder trực tiếp. Stack canonical hiện cũng đã chốt: React/Vite, FastAPI, SQLite WAL, SQLite FTS5, DuckDB, FAISS, LocalFileMediaStore.

# 1. Tư duy tổng thể về data

Hệ thống này không nên coi “data” chỉ là video/keyframe. Nó phải coi data theo 5 lớp:

```text
Layer 1: Raw Data
- video gốc
- keyframe BTC cung cấp
- metadata gốc
- file OCR/ASR/object/caption nếu BTC cung cấp
- nằm ngoài repo, thường ở HDD: ${AIC_DATA_ROOT}/raw/

Layer 2: Preprocessing/Staging Data
- dữ liệu trung gian sau khi chạy notebook/script
- output theo shard
- bảng staging trong DuckDB
- validation reports
- nằm ngoài repo, thường ở HDD: ${AIC_DATA_ROOT}/staging/ hoặc ${AIC_DATA_ROOT}/warehouse/

Layer 3: App-ready Runtime Data
- app.sqlite
- SQLite FTS5 tables
- FAISS index
- vector/keyframe mapping
- logical media refs đã chuẩn hóa
- ưu tiên nằm ở SSD/runtime root: ${AIC_RUNTIME_ROOT}/

Layer 4: Runtime User Data
- query sessions
- clues
- search history
- candidates
- notes
- output helper state
- agent runs
- nằm trong app.sqlite

Layer 5: Rebuildable Index/Derived Artifacts
- thumbnails
- visual.faiss
- vector maps
- text indexes
- validation manifests
- có thể rebuild từ raw/staging/artifact manifests
```

Điểm quan trọng: **không phải data nào cũng lưu cùng một chỗ**.

# 2. Strategy lưu trữ tổng thể

Chốt theo nguyên tắc này:

```text
Repo source code/docs/config       -> ${REPO_ROOT}
Raw media / generated media lớn    -> ${AIC_DATA_ROOT}, thường là HDD
Preprocessing staging              -> DuckDB + JSONL/Parquet/NPY dưới ${AIC_DATA_ROOT}
Runtime structured metadata        -> SQLite WAL dưới ${AIC_RUNTIME_ROOT}, ưu tiên SSD
Runtime mutable app state          -> SQLite WAL dưới ${AIC_RUNTIME_ROOT}, ưu tiên SSD
Text search                        -> SQLite FTS5 trong app.sqlite
Vector search                      -> FAISS dưới ${AIC_RUNTIME_ROOT}/indexes
Vector/keyframe mapping            -> SQLite
Validation/report/manifests        -> JSON/Parquet + SQLite/DuckDB summary
```

Không nên nhét tất cả vào một DB. Cũng không nên nhét media lớn vào repo hoặc app folder.

## Bảng quyết định lưu trữ

| Loại dữ liệu               | Lưu ở đâu                                                      | Vì sao                                    |
| -------------------------- | -------------------------------------------------------------- | ----------------------------------------- |
| Source code/docs/config    | `${REPO_ROOT}`                                                 | repo chỉ chứa thứ nhỏ, versionable        |
| Raw video `.mp4`           | `${AIC_DATA_ROOT}/raw/videos`, thường HDD                      | file lớn, không đưa vào DB/repo           |
| Original keyframes         | `${AIC_DATA_ROOT}/raw/keyframes_original`, thường HDD          | dữ liệu lớn, immutable                    |
| Processed keyframes        | `${AIC_DATA_ROOT}/processed/media/keyframes`, thường HDD       | browser/API load qua MediaStore           |
| Thumbnail WebP/JPEG        | `${AIC_DATA_ROOT}/processed/media/thumbnails`, hoặc SSD nếu ít | dùng cho grid, có thể rất nhiều           |
| Video metadata             | SQLite runtime + DuckDB staging                                | app cần query nhanh, DuckDB cần normalize |
| Keyframe metadata          | SQLite runtime                                                 | core lookup của app                       |
| OCR text                   | SQLite + FTS5                                                  | vừa hiển thị evidence, vừa search text    |
| ASR transcript             | SQLite + FTS5                                                  | search theo lời nói/time segment          |
| Caption                    | SQLite + FTS5                                                  | search semantic/text evidence             |
| Object labels              | SQLite + FTS5                                                  | search object/category                    |
| CLIP/image embeddings      | `.npy` staging, FAISS runtime                                  | vector search                             |
| FAISS vector ID mapping    | SQLite                                                         | map result từ FAISS sang keyframe         |
| Query session              | SQLite                                                         | mutable app state                         |
| Candidate basket           | SQLite                                                         | cần persist khi nhiều teammate dùng       |
| Agent trace                | SQLite                                                         | cần debug/rerun                           |
| Validation reports         | JSON + DuckDB/SQLite summary                                   | audit dataset quality                     |
| Preprocessing intermediate | DuckDB/Parquet/JSONL/NPY                                       | rebuildable, batch-oriented               |

# 3. Physical layout nên chốt

Không dùng một folder `data/` trong repo cho dataset thật. Nên tách rõ 3 root:

```text
${REPO_ROOT}         = source code/docs/config only
${AIC_DATA_ROOT}     = external large data root, usually HDD
${AIC_RUNTIME_ROOT}  = runtime hot artifact root, preferably SSD
```

## 3.1. Repo root: source code only

```text
${REPO_ROOT}/
  README.md
  docs/
  backend/
  frontend/
  scripts/
  notebooks/
  config/
    app.example.yaml
  schemas/
    app_schema.sql
  tests/
    fixtures/
      tiny_seed_dataset/
  .gitignore
```

Repo chỉ chứa:

```text
code
docs
schemas
config templates
notebooks/scripts
tiny fixtures for tests
```

Repo không chứa:

```text
raw videos
full keyframes
large thumbnails
large .npy embeddings
large .faiss indexes
large .sqlite runtime DB
large .duckdb warehouse
```

## 3.2. External data root: usually HDD

```text
${AIC_DATA_ROOT}/
  raw/
    videos/
      L01_V001.mp4
      L01_V002.mp4
    keyframes_original/
      L01_V001/
        000001.jpg
        000125.jpg
    metadata_original/
      videos.json
      objects.json
      captions.json
      ...

  processed/
    media/
      videos/
        L01_V001.mp4
      keyframes/
        L01_V001/
          000001.jpg
          000125.jpg
      thumbnails/
        L01_V001/
          000001.webp
          000125.webp

  staging/
    shards/
      L01/
        vision_embeddings.npy
        vision_manifest.jsonl
        ocr.jsonl
        asr.jsonl
        captions.jsonl
        objects.jsonl
    reports/
      ingest_validation.json
      missing_media.json
      duplicate_frames.json

  warehouse/
    warehouse.duckdb
```

Đây là nơi chứa data lớn. Thường nên đặt ở HDD.

## 3.3. Runtime root: preferably SSD

```text
${AIC_RUNTIME_ROOT}/
  db/
    app.sqlite
    app.sqlite-wal
    app.sqlite-shm

  indexes/
    visual.faiss
    visual_index_manifest.json

  cache/
```

Ưu tiên để trên SSD:

```text
app.sqlite
app.sqlite-wal
app.sqlite-shm
FTS5 tables trong app.sqlite
visual.faiss
small runtime cache
```

Nếu SSD quá ít, có thể đặt runtime root trên HDD, nhưng performance sẽ kém hơn.

## 3.4. Config nối các root lại

Ví dụ Linux:

```yaml
storage:
  media_store:
    type: local
    root: /mnt/hdd/aic2026/processed/media

  raw_data_root: /mnt/hdd/aic2026/raw
  staging_root: /mnt/hdd/aic2026/staging
  warehouse_path: /mnt/hdd/aic2026/warehouse/warehouse.duckdb

runtime:
  sqlite_path: /mnt/ssd/aic2026_runtime/db/app.sqlite
  faiss_index_path: /mnt/ssd/aic2026_runtime/indexes/visual.faiss
  cache_root: /mnt/ssd/aic2026_runtime/cache
```

Ví dụ Windows:

```yaml
storage:
  media_store:
    type: local
    root: D:/AIC2026/processed/media

  raw_data_root: D:/AIC2026/raw
  staging_root: D:/AIC2026/staging
  warehouse_path: D:/AIC2026/warehouse/warehouse.duckdb

runtime:
  sqlite_path: C:/AIC2026_RUNTIME/db/app.sqlite
  faiss_index_path: C:/AIC2026_RUNTIME/indexes/visual.faiss
  cache_root: C:/AIC2026_RUNTIME/cache
```

# 4. Nguyên tắc ID và mapping

Đây là phần cực kỳ quan trọng. Nếu ID không chuẩn, retrieval sẽ rối.

## 4.1. ID cấp dataset

```text
dataset_id = "aic2026_prelim_v1"
dataset_version = "2026-06-25"
```

Dùng để sau này nếu có nhiều bộ data:

```text
aic2026_prelim
aic2026_final
aic2025_sample
mock_seed
```

## 4.2. ID cấp video

Nên dùng đúng format contest:

```text
video_id = "L01_V028"
```

Không lưu `.mp4` trong `video_id`.

Sai:

```text
L01_V028.mp4
D:/AIC2026/raw/videos/L01_V028.mp4
```

Đúng:

```text
video_id = "L01_V028"
video_ref = "videos/L01_V028.mp4"
```

`video_ref` là logical ref, không phải absolute path.

## 4.3. ID cấp keyframe

Nên có cả `frame_id` và `keyframe_id`.

```text
video_id = "L01_V028"
frame_id = 25300
keyframe_id = "L01_V028:25300"
```

Lý do:

* `video_id + frame_id` là format thi/copy output.
* `keyframe_id` tiện làm primary key trong DB/API.
* `frame_id` phải là integer vì output submission thường cần số frame.

## 4.4. Media references

Không lưu absolute path. Lưu logical ref.

```text
video_ref = "videos/L01_V028.mp4"
keyframe_ref = "keyframes/L01_V028/025300.jpg"
thumbnail_ref = "thumbnails/L01_V028/025300.webp"
```

Backend resolve:

```text
LocalFileMediaStore(root=${AIC_DATA_ROOT}/processed/media)
+ thumbnail_ref
= ${AIC_DATA_ROOT}/processed/media/thumbnails/L01_V028/025300.webp
```

Sau này MinIO resolve:

```text
bucket = aic2026
key = thumbnails/L01_V028/025300.webp
```

UI không biết local hay MinIO.

# 5. Các loại dữ liệu cần chuẩn hóa

## 5.1. Raw video

Nguồn:

```text
${AIC_DATA_ROOT}/raw/videos/*.mp4
```

Thông tin cần lưu:

```text
video_id
dataset_id
video_ref
duration_sec
fps
width
height
source_name
source_url
title
description
channel
created_at/source date nếu có
```

Runtime cần video để:

* mở video on-demand;
* timeline context;
* same-video navigation;
* copy result;
* verify candidate.

Nhưng không nên auto-load raw video trong UI vì HDD có thể chậm.

## 5.2. Keyframes

Nguồn có thể là:

```text
BTC-provided keyframes
hoặc generated keyframes từ video
```

Physical location:

```text
${AIC_DATA_ROOT}/raw/keyframes_original/
hoặc
${AIC_DATA_ROOT}/processed/media/keyframes/
```

Mỗi keyframe cần:

```text
keyframe_id
video_id
frame_id
timestamp_sec
keyframe_ref
thumbnail_ref
width
height
is_official_keyframe
extraction_method
```

Keyframe là entity trung tâm của toàn bộ hệ thống.

Mọi thứ nên map về keyframe:

```text
caption -> keyframe_id
OCR -> keyframe_id
object -> keyframe_id
embedding -> keyframe_id
search result -> keyframe_id
candidate -> keyframe_id
```

## 5.3. Thumbnail

Thumbnail không phải chỉ là ảnh nhỏ. Nó là dữ liệu performance-critical cho UI.

Physical location:

```text
${AIC_DATA_ROOT}/processed/media/thumbnails/{video_id}/{frame_id_padded}.webp
```

Logical ref:

```text
thumbnails/{video_id}/{frame_id_padded}.webp
```

Kích thước gợi ý:

```text
small: 320px width
medium: 640px width
full keyframe preview: original hoặc max 1280px
```

Có thể lưu:

```text
thumbnail_ref
thumbnail_width
thumbnail_height
thumbnail_size_bytes
```

UI result grid chỉ dùng thumbnail, không dùng raw keyframe lớn.

Nếu SSD đủ và thumbnail ít, có thể cache thumbnail hot subset trên SSD. Nhưng source of truth MVP vẫn nên là LocalFileMediaStore qua config.

## 5.4. Captions

Caption có thể từ:

* model image captioning;
* LVLM;
* BTC-provided captions;
* generated caption EN/VI.

Lưu theo keyframe:

```text
caption_id
keyframe_id
video_id
frame_id
lang
caption_text
model_name
confidence
created_at
```

Có thể có nhiều caption cho một keyframe:

```text
caption_en_blip
caption_vi_translated
caption_vlm_detailed
```

Strategy:

* SQLite lưu caption rows để evidence display.
* FTS5 index caption text để text search.
* Optional embedding caption text để semantic text search sau.

## 5.5. OCR text

OCR có thể có bounding boxes.

Lưu hai cấp:

```text
ocr_texts: full text per keyframe
ocr_boxes: từng box text nếu cần highlight
```

MVP có thể chỉ cần `ocr_texts`.

Cấu trúc:

```text
ocr_id
keyframe_id
video_id
frame_id
text
lang
engine
confidence
boxes_json
```

`boxes_json` có thể lưu JSON:

```json
[
  {
    "text": "AI CHALLENGE",
    "confidence": 0.91,
    "bbox": [120, 80, 320, 140]
  }
]
```

FTS5 index:

```text
ocr_fts(text)
```

Search OCR rất quan trọng vì nhiều query có clue từ chữ trên màn hình, biển hiệu, poster, slide.

## 5.6. ASR transcript

ASR không gắn trực tiếp 1-1 với keyframe. Nó gắn với video time range.

Cần lưu segment:

```text
asr_segment_id
video_id
start_sec
end_sec
text
lang
engine
confidence
```

Mapping ASR -> keyframe khi search:

```text
keyframe timestamp_sec nằm gần [start_sec, end_sec]
```

Có thể dùng rule:

```text
segment.start_sec - window <= keyframe.timestamp_sec <= segment.end_sec + window
```

Ví dụ window:

```text
3s hoặc 5s
```

Nên có bảng mapping materialized nếu muốn nhanh:

```text
keyframe_asr_segments
- keyframe_id
- asr_segment_id
- distance_sec
```

MVP có thể query runtime bằng `video_id` + timestamp range, nhưng nếu dataset lớn thì materialize mapping sẽ nhanh hơn.

## 5.7. Objects / concepts

Nguồn:

* YOLO/Detic/GroundingDINO;
* BTC-provided object JSON;
* scene classifier;
* manual tags.

Có hai loại:

```text
object detection boxes
object/concept tags
```

MVP nên lưu concept-level trước:

```text
object_id
keyframe_id
video_id
frame_id
label
confidence
source
bbox_json optional
```

FTS5 có thể index object labels:

```text
person car bus microphone stage red-shirt
```

Nhưng object search nên có thêm normalized label:

```text
raw_label = "motorbike"
normalized_label = "motorcycle"
lang_vi = "xe máy"
```

Nếu làm tốt, query tiếng Việt có thể map:

```text
xe máy -> motorcycle/motorbike
người -> person
màn hình -> screen
```

## 5.8. Scene / location / visual attributes

Dữ liệu này không bắt buộc nhưng rất hữu ích.

Ví dụ:

```text
indoor/outdoor
day/night
street/office/classroom/stage
crowded/empty
dominant_colors
weather
camera_view
```

Có thể lưu trong bảng:

```text
scene_tags
- keyframe_id
- tag
- confidence
- source
```

Hoặc JSON trong `keyframes.attributes_json`.

MVP có thể để JSON trước, sau đó tách bảng khi cần search/filter.

## 5.9. Embeddings

Có nhiều loại embedding:

```text
image_embedding: CLIP image embedding cho keyframe
text_embedding: optional caption/query embedding
audio_embedding: optional
object_embedding: optional
```

MVP cần nhất:

```text
image embedding -> FAISS visual.faiss
```

Không nên lưu vector lớn trực tiếp trong SQLite. Nên lưu:

```text
embedding npy/parquet staging dưới ${AIC_DATA_ROOT}/staging/
FAISS index runtime dưới ${AIC_RUNTIME_ROOT}/indexes/
SQLite mapping table trong app.sqlite
```

Mapping tối thiểu:

```text
embedding_id
index_name
vector_id
keyframe_id
model_name
dimension
normalize_method
```

FAISS trả về `vector_id`, sau đó SQLite map sang `keyframe_id`.

## 5.10. Metadata gốc

Video metadata có thể gồm:

```text
title
description
source
channel
upload_date
youtube_url
category
duration
language
```

Raw metadata nằm ở:

```text
${AIC_DATA_ROOT}/raw/metadata_original/
```

Normalized metadata nằm trong SQLite để display/filter.

Text fields cũng nên đưa vào FTS5:

```text
metadata_fts
```

## 5.11. Query session data

Runtime mutable data:

```text
query_sessions
query_clues
search_runs
search_results
candidates
candidate_events
notes
agent_runs
agent_steps
```

Đây không phải preprocessing data, mà là app state.

Vì team dùng LAN, Query Session là boundary chính. Session state, clue, notes, candidate basket nên lưu trong SQLite theo `session_id`.

# 6. SQLite runtime schema đề xuất

SQLite runtime nằm ở:

```text
${AIC_RUNTIME_ROOT}/db/app.sqlite
```

Bật WAL:

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;
```

## 6.1. `datasets`

```sql
CREATE TABLE datasets (
  dataset_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  version TEXT,
  root_ref TEXT,
  created_at TEXT,
  metadata_json TEXT
);
```

`root_ref` không nên là absolute machine path. Nếu cần, dùng logical name như:

```text
aic2026_prelim_v1
```

Physical root nằm trong config.

## 6.2. `videos`

```sql
CREATE TABLE videos (
  video_id TEXT PRIMARY KEY,
  dataset_id TEXT NOT NULL,
  video_ref TEXT NOT NULL,
  title TEXT,
  description TEXT,
  source_url TEXT,
  source_channel TEXT,
  duration_sec REAL,
  fps REAL,
  width INTEGER,
  height INTEGER,
  metadata_json TEXT,
  FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id)
);
```

`video_ref` ví dụ:

```text
videos/L01_V028.mp4
```

Không lưu:

```text
D:/AIC2026/raw/videos/L01_V028.mp4
```

## 6.3. `keyframes`

```sql
CREATE TABLE keyframes (
  keyframe_id TEXT PRIMARY KEY,
  video_id TEXT NOT NULL,
  frame_id INTEGER NOT NULL,
  timestamp_sec REAL,
  keyframe_ref TEXT NOT NULL,
  thumbnail_ref TEXT NOT NULL,
  width INTEGER,
  height INTEGER,
  is_official INTEGER DEFAULT 1,
  extraction_method TEXT,
  metadata_json TEXT,
  UNIQUE(video_id, frame_id),
  FOREIGN KEY (video_id) REFERENCES videos(video_id)
);
```

Index quan trọng:

```sql
CREATE INDEX idx_keyframes_video_frame ON keyframes(video_id, frame_id);
CREATE INDEX idx_keyframes_video_time ON keyframes(video_id, timestamp_sec);
```

## 6.4. `captions`

```sql
CREATE TABLE captions (
  caption_id TEXT PRIMARY KEY,
  keyframe_id TEXT NOT NULL,
  video_id TEXT NOT NULL,
  frame_id INTEGER NOT NULL,
  lang TEXT,
  caption_text TEXT NOT NULL,
  model_name TEXT,
  confidence REAL,
  created_at TEXT,
  FOREIGN KEY (keyframe_id) REFERENCES keyframes(keyframe_id)
);
```

## 6.5. `ocr_texts`

```sql
CREATE TABLE ocr_texts (
  ocr_id TEXT PRIMARY KEY,
  keyframe_id TEXT NOT NULL,
  video_id TEXT NOT NULL,
  frame_id INTEGER NOT NULL,
  text TEXT NOT NULL,
  lang TEXT,
  engine TEXT,
  confidence REAL,
  boxes_json TEXT,
  FOREIGN KEY (keyframe_id) REFERENCES keyframes(keyframe_id)
);
```

## 6.6. `asr_segments`

```sql
CREATE TABLE asr_segments (
  asr_segment_id TEXT PRIMARY KEY,
  video_id TEXT NOT NULL,
  start_sec REAL NOT NULL,
  end_sec REAL NOT NULL,
  text TEXT NOT NULL,
  lang TEXT,
  engine TEXT,
  confidence REAL,
  FOREIGN KEY (video_id) REFERENCES videos(video_id)
);
```

Optional materialized mapping:

```sql
CREATE TABLE keyframe_asr_segments (
  keyframe_id TEXT NOT NULL,
  asr_segment_id TEXT NOT NULL,
  distance_sec REAL,
  PRIMARY KEY (keyframe_id, asr_segment_id),
  FOREIGN KEY (keyframe_id) REFERENCES keyframes(keyframe_id),
  FOREIGN KEY (asr_segment_id) REFERENCES asr_segments(asr_segment_id)
);
```

## 6.7. `objects`

```sql
CREATE TABLE objects (
  object_id TEXT PRIMARY KEY,
  keyframe_id TEXT NOT NULL,
  video_id TEXT NOT NULL,
  frame_id INTEGER NOT NULL,
  label TEXT NOT NULL,
  normalized_label TEXT,
  confidence REAL,
  source TEXT,
  bbox_json TEXT,
  FOREIGN KEY (keyframe_id) REFERENCES keyframes(keyframe_id)
);
```

## 6.8. `embedding_indexes`

```sql
CREATE TABLE embedding_indexes (
  index_name TEXT PRIMARY KEY,
  index_type TEXT NOT NULL,
  model_name TEXT NOT NULL,
  dimension INTEGER NOT NULL,
  metric TEXT NOT NULL,
  index_ref TEXT NOT NULL,
  manifest_ref TEXT,
  created_at TEXT
);
```

Ví dụ:

```text
index_name = "visual_clip_vit_b32"
index_type = "faiss"
model_name = "openclip/ViT-B-32"
dimension = 512
metric = "cosine"
index_ref = "indexes/visual.faiss"
```

`index_ref` là logical runtime ref. Physical path lấy từ config:

```text
${AIC_RUNTIME_ROOT}/indexes/visual.faiss
```

## 6.9. `vector_map`

```sql
CREATE TABLE vector_map (
  index_name TEXT NOT NULL,
  vector_id INTEGER NOT NULL,
  keyframe_id TEXT NOT NULL,
  video_id TEXT NOT NULL,
  frame_id INTEGER NOT NULL,
  PRIMARY KEY (index_name, vector_id),
  FOREIGN KEY (index_name) REFERENCES embedding_indexes(index_name),
  FOREIGN KEY (keyframe_id) REFERENCES keyframes(keyframe_id)
);
```

Đây là bảng cực kỳ quan trọng.

Flow:

```text
FAISS returns vector_id = 123456
-> SELECT keyframe_id FROM vector_map WHERE index_name = ? AND vector_id = 123456
-> SELECT metadata/evidence FROM keyframes/captions/ocr/asr/objects
```

## 6.10. Query/session runtime tables

```sql
CREATE TABLE query_sessions (
  session_id TEXT PRIMARY KEY,
  title TEXT,
  query_type TEXT,
  status TEXT,
  created_at TEXT,
  updated_at TEXT,
  metadata_json TEXT
);
```

```sql
CREATE TABLE query_clues (
  clue_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  clue_order INTEGER NOT NULL,
  clue_text TEXT NOT NULL,
  source TEXT,
  created_by TEXT,
  created_at TEXT,
  FOREIGN KEY (session_id) REFERENCES query_sessions(session_id)
);
```

```sql
CREATE TABLE search_runs (
  search_run_id TEXT PRIMARY KEY,
  session_id TEXT,
  query_text TEXT NOT NULL,
  search_mode TEXT,
  strategy_json TEXT,
  created_by TEXT,
  created_at TEXT,
  latency_ms INTEGER,
  FOREIGN KEY (session_id) REFERENCES query_sessions(session_id)
);
```

```sql
CREATE TABLE search_results (
  search_run_id TEXT NOT NULL,
  rank INTEGER NOT NULL,
  keyframe_id TEXT NOT NULL,
  video_id TEXT NOT NULL,
  frame_id INTEGER NOT NULL,
  score REAL,
  visual_score REAL,
  text_score REAL,
  ocr_score REAL,
  asr_score REAL,
  object_score REAL,
  evidence_json TEXT,
  PRIMARY KEY (search_run_id, rank),
  FOREIGN KEY (search_run_id) REFERENCES search_runs(search_run_id),
  FOREIGN KEY (keyframe_id) REFERENCES keyframes(keyframe_id)
);
```

```sql
CREATE TABLE candidates (
  candidate_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  keyframe_id TEXT NOT NULL,
  video_id TEXT NOT NULL,
  frame_id INTEGER NOT NULL,
  query_type TEXT,
  answer TEXT,
  trake_sequence_json TEXT,
  note TEXT,
  created_by TEXT,
  created_at TEXT,
  updated_at TEXT,
  FOREIGN KEY (session_id) REFERENCES query_sessions(session_id),
  FOREIGN KEY (keyframe_id) REFERENCES keyframes(keyframe_id)
);
```

# 7. SQLite FTS5 design

Không nên search text bằng `LIKE` trên bảng thường. Nên tạo FTS5.

## 7.1. Caption FTS

```sql
CREATE VIRTUAL TABLE caption_fts USING fts5(
  keyframe_id UNINDEXED,
  video_id UNINDEXED,
  frame_id UNINDEXED,
  caption_text,
  tokenize='unicode61'
);
```

## 7.2. OCR FTS

```sql
CREATE VIRTUAL TABLE ocr_fts USING fts5(
  keyframe_id UNINDEXED,
  video_id UNINDEXED,
  frame_id UNINDEXED,
  text,
  tokenize='unicode61'
);
```

## 7.3. ASR FTS

```sql
CREATE VIRTUAL TABLE asr_fts USING fts5(
  asr_segment_id UNINDEXED,
  video_id UNINDEXED,
  start_sec UNINDEXED,
  end_sec UNINDEXED,
  text,
  tokenize='unicode61'
);
```

## 7.4. Objects FTS

```sql
CREATE VIRTUAL TABLE object_fts USING fts5(
  keyframe_id UNINDEXED,
  video_id UNINDEXED,
  frame_id UNINDEXED,
  labels_text,
  tokenize='unicode61'
);
```

## 7.5. Unified FTS view/table

Ngoài modality-specific FTS, nên có bảng unified để search tổng hợp:

```sql
CREATE VIRTUAL TABLE evidence_fts USING fts5(
  keyframe_id UNINDEXED,
  video_id UNINDEXED,
  frame_id UNINDEXED,
  source_type UNINDEXED,
  content,
  tokenize='unicode61'
);
```

`source_type`:

```text
caption
ocr
asr
object
metadata
```

Khi search:

```text
query -> evidence_fts -> keyframe_id candidates
```

Sau đó group by `keyframe_id`.

# 8. FAISS mapping strategy

FAISS chỉ biết vector. Nó không biết `video_id`, `frame_id`, `caption`, `OCR`.

Vì vậy bắt buộc cần mapping.

## Build-time

```text
for each keyframe:
  image -> CLIP embedding -> append vector to matrix
  vector_id = row index
  insert vector_map(index_name, vector_id, keyframe_id, video_id, frame_id)
build FAISS index from matrix
save visual.faiss under ${AIC_RUNTIME_ROOT}/indexes/
```

## Runtime

```text
query text/image
-> embedding model produces query_vector
-> FAISS.search(query_vector, top_k)
-> returns vector_ids + distances
-> SQLite vector_map resolves keyframe_id
-> SQLite keyframes/captions/ocr/asr/objects provide evidence
-> API returns ranked result cards
```

Result object nên có shape cố định:

```json
{
  "rank": 1,
  "keyframe_id": "L01_V028:25300",
  "video_id": "L01_V028",
  "frame_id": 25300,
  "timestamp_sec": 843.3,
  "thumbnail_url": "/api/media/thumbnail/L01_V028:25300",
  "image_url": "/api/media/keyframe/L01_V028:25300",
  "score": 0.87,
  "scores": {
    "visual": 0.82,
    "caption": 0.61,
    "ocr": 0.0,
    "asr": 0.22,
    "object": 0.13
  },
  "evidence": {
    "caption": ["A person wearing a white protective suit..."],
    "ocr": ["AI CHALLENGE"],
    "asr": ["..."],
    "objects": ["person", "helmet", "screen"]
  }
}
```

# 9. DuckDB staging strategy

DuckDB không phải runtime app DB. Nó là nơi gom, normalize, validate.

Physical location:

```text
${AIC_DATA_ROOT}/warehouse/warehouse.duckdb
```

hoặc:

```text
${AIC_DATA_ROOT}/staging/duckdb/warehouse.duckdb
```

## DuckDB staging tables

Ví dụ:

```sql
staging_videos
staging_keyframes
staging_captions
staging_ocr
staging_asr
staging_objects
staging_embeddings_manifest
validation_missing_media
validation_duplicate_keyframes
```

## Vì sao cần DuckDB?

Vì preprocessing có nhiều file:

```text
CSV
JSON
JSONL
Parquet
NPY manifest
folder scans
```

DuckDB xử lý batch tốt hơn SQLite:

```text
read_json_auto()
read_parquet()
read_csv_auto()
join
aggregate
validate
export
```

## Output từ DuckDB sang runtime

```text
DuckDB staging
-> export normalized tables
-> insert into ${AIC_RUNTIME_ROOT}/db/app.sqlite
-> build FTS5
-> build FAISS/vector_map
-> write validation reports
```

# 10. MediaStore mapping

Ngay từ đầu phải có `MediaStorePort`.

## DB chỉ lưu logical ref

```text
thumbnail_ref = "thumbnails/L01_V028/025300.webp"
keyframe_ref = "keyframes/L01_V028/025300.jpg"
video_ref = "videos/L01_V028.mp4"
```

## API resolve

```http
GET /api/media/thumbnail/{keyframe_id}
GET /api/media/keyframe/{keyframe_id}
GET /api/media/video/{video_id}
```

Backend flow:

```text
keyframe_id
-> SQLite keyframes.thumbnail_ref
-> MediaStore.resolve(thumbnail_ref)
-> file response or URL
```

MVP:

```text
LocalFileMediaStore(root=${AIC_DATA_ROOT}/processed/media)
```

Future:

```text
MinioMediaStore(bucket=aic2026, prefix=...)
```

Như vậy sau này thêm MinIO không sửa UI/retrieval.

# 11. Search flow mapping

## 11.1. Visual search

```text
User query: "người mặc áo đỏ đứng trên sân khấu"
-> encode query bằng CLIP text encoder
-> FAISS visual search
-> vector_id list
-> vector_map -> keyframe_id
-> keyframes -> media refs
-> evidence tables -> captions/OCR/ASR/objects
-> API result
```

## 11.2. Text search

```text
User query
-> SQLite FTS5 search caption_fts/evidence_fts/ocr_fts/asr_fts
-> keyframe_id/video_id candidates
-> keyframes metadata
-> evidence details
-> ranked result
```

## 11.3. ASR search

ASR search trả về segment, không phải keyframe trực tiếp:

```text
FTS asr_fts -> asr_segment_id
-> video_id + start_sec/end_sec
-> find nearest keyframes in same video
-> keyframe result
```

## 11.4. Hybrid search

```text
visual candidates
+ caption FTS candidates
+ OCR FTS candidates
+ ASR candidates mapped to keyframes
+ object candidates
-> normalize scores
-> weighted fusion
-> top ranked keyframes
```

Score có thể đơn giản ban đầu:

```text
final_score =
  0.50 * visual_score +
  0.25 * caption_score +
  0.10 * ocr_score +
  0.10 * asr_score +
  0.05 * object_score
```

Sau đó UI cho chỉnh weights.

# 12. Data state classification

Phải phân biệt data theo trạng thái.

## Immutable

Không sửa trong app:

```text
raw videos
official keyframes
original metadata
```

Nằm ở:

```text
${AIC_DATA_ROOT}/raw/
```

## Rebuildable

Có thể xóa build lại:

```text
thumbnails
FAISS index
FTS5 tables
DuckDB staging
captions generated by model
OCR generated by model
ASR generated by model
```

## Runtime mutable

App ghi trong lúc dùng:

```text
query_sessions
query_clues
search_runs
candidates
notes
agent_runs
```

Nằm trong:

```text
${AIC_RUNTIME_ROOT}/db/app.sqlite
```

## Configurable / rules-based

Thay đổi theo cuộc thi:

```text
query type
CSV output format
answer validation
frame tolerance
max rows
submission packaging
```

Không nên hard-code những cái này.

# 13. Minimal seed dataset cần có trước khi build app

Không cần full data. Nhưng cần sample đủ đại diện.

## Seed dataset nên có

```text
5-10 videos hoặc mock media nhỏ
100-500 keyframes
thumbnails
app.sqlite
visual.faiss
vector_map
captions sample
OCR sample
ASR sample
objects sample
query_sessions empty
candidates empty
validation report
```

## Seed dataset nên đặt ở đâu?

Có 2 loại seed:

### Tiny seed cho repo/test

```text
${REPO_ROOT}/tests/fixtures/tiny_seed_dataset/
```

Chỉ chứa file cực nhỏ, dùng cho unit/integration tests.

### Real seed cho local development

```text
${AIC_DATA_ROOT}/seed/
${AIC_RUNTIME_ROOT}/seed_runtime/
```

Không commit vào git.

## Mục tiêu của seed dataset

Test được:

```text
1. UI load result grid
2. thumbnail URL works
3. click keyframe opens detail
4. same-video explorer works
5. visual search returns keyframes
6. FTS5 search returns evidence
7. candidate basket saves to SQLite
8. copy output works
```

# 14. Preprocessing pipeline nên chia thế nào

## Stage A: Discovery

```text
scan raw videos từ ${AIC_DATA_ROOT}/raw/videos
scan keyframes từ ${AIC_DATA_ROOT}/raw/keyframes_original
scan metadata files
detect available modalities
normalize video_id/frame_id
```

Output:

```text
staging_videos
staging_keyframes
media_manifest.jsonl
```

## Stage B: Media processing

```text
generate thumbnails
validate keyframe paths
probe video metadata with ffprobe
```

Output:

```text
${AIC_DATA_ROOT}/processed/media/thumbnails/...
video_probe.jsonl
```

## Stage C: Evidence processing

```text
OCR
ASR
captions
objects
scene tags
```

Output:

```text
${AIC_DATA_ROOT}/staging/shards/*/ocr.jsonl
${AIC_DATA_ROOT}/staging/shards/*/asr.jsonl
${AIC_DATA_ROOT}/staging/shards/*/captions.jsonl
${AIC_DATA_ROOT}/staging/shards/*/objects.jsonl
```

## Stage D: Embedding processing

```text
CLIP image embeddings
optional caption embeddings
```

Output:

```text
${AIC_DATA_ROOT}/staging/shards/*/embeddings.npy
${AIC_DATA_ROOT}/staging/shards/*/embedding_manifest.jsonl
```

## Stage E: DuckDB aggregation

```text
load all staging outputs
join/normalize/validate
produce app-ready tables
```

Output:

```text
${AIC_DATA_ROOT}/warehouse/warehouse.duckdb
```

## Stage F: Runtime artifact build

```text
write ${AIC_RUNTIME_ROOT}/db/app.sqlite
build FTS5 tables inside app.sqlite
build ${AIC_RUNTIME_ROOT}/indexes/visual.faiss
write vector_map into app.sqlite
write validation report
```

# 15. Validation bắt buộc trước khi app chạy

Ingestion phải fail nếu data contract sai.

Validation cần check:

```text
video_id unique
keyframe_id unique
(video_id, frame_id) unique
video_ref resolves through MediaStore
keyframe_ref resolves through MediaStore
thumbnail_ref resolves through MediaStore
FAISS vector count == vector_map row count
every vector_map.keyframe_id exists
every caption/ocr/object keyframe_id exists
every asr segment video_id exists
no absolute path leaked into SQLite
no machine-specific path leaked into SQLite
FTS5 row count roughly matches source rows
```

Quy tắc quan trọng:

```text
SQLite must not contain:
- D:/...
- C:/...
- /mnt/hdd/...
- /home/user/...
- any absolute machine-specific media path

SQLite should contain only:
- videos/{video_id}.mp4
- keyframes/{video_id}/{frame_id_padded}.jpg
- thumbnails/{video_id}/{frame_id_padded}.webp
```

# 16. API contract phụ thuộc data contract

Sau khi có schema, API mới rõ.

## Media APIs

```http
GET /api/media/thumbnail/{keyframe_id}
GET /api/media/keyframe/{keyframe_id}
GET /api/media/video/{video_id}
```

## Lookup APIs

```http
GET /api/videos/{video_id}
GET /api/keyframes/{keyframe_id}
GET /api/videos/{video_id}/keyframes?around_frame_id=25300&window=20
GET /api/keyframes/{keyframe_id}/evidence
```

## Search APIs

```http
POST /api/search/visual
POST /api/search/text
POST /api/search/hybrid
```

## Session APIs

```http
POST /api/sessions
GET /api/sessions
GET /api/sessions/{session_id}
POST /api/sessions/{session_id}/clues
POST /api/sessions/{session_id}/candidates
GET /api/sessions/{session_id}/candidates
```

# 17. Nên cập nhật backlog thế nào

Hiện backlog có MVP-1 là Dataset + SQLite schema, MVP-2 là UI. Nhưng nên tách rõ hơn:

```text
MVP-0: Documentation canonicalization
MVP-0.5: App-ready Data Contract
MVP-0.6: Seed Dataset Builder
MVP-1: Runtime SQLite Schema + Validation
MVP-2: Backend API vertical slice
MVP-3: Keyframe-first UI vertical slice
MVP-4: FAISS visual retrieval
MVP-5: SQLite FTS5 retrieval
MVP-6: Hybrid retrieval
MVP-7: Query sessions + candidate basket
MVP-8: Agent v0
```

Lý do: nếu không tách `Data Contract` và `Seed Dataset Builder`, agent dễ nhảy thẳng vào UI/backend mà chưa có data thực sự.

# 18. Prompt chi tiết gửi harness agent

```text
Before implementing the runtime app, create a canonical App-ready Data Contract and Seed Dataset plan.

The runtime system must not be built on vague assumptions. Define exactly what app-ready artifacts exist, how they are stored, and how IDs map across media, SQLite, FAISS, FTS5, and UI/API responses.

Correct storage-root decision:
- The repository must contain only code, docs, schemas, scripts, config templates, and tiny test fixtures.
- Large videos, full keyframes, thumbnails, generated media, preprocessing shards, and warehouse files must live outside the repo under a configurable external data root, usually on HDD.
- Runtime hot artifacts such as app.sqlite, SQLite WAL/SHM, FTS5 tables, FAISS indexes, and small cache should live under a configurable runtime root, preferably SSD if available.
- SQLite must store logical media references only, never absolute machine-specific paths.
- Backend resolves logical refs through MediaStorePort using config.
- LocalFileMediaStore is MVP.
- MinioMediaStore is optional future adapter.

Use these root concepts:
- ${REPO_ROOT}: source code/docs/config only.
- ${AIC_DATA_ROOT}: external large-data root, usually HDD.
- ${AIC_RUNTIME_ROOT}: runtime hot artifact root, preferably SSD.

Canonical storage strategy:
- Raw videos/keyframes/media assets live on local filesystem under ${AIC_DATA_ROOT}.
- Runtime source of truth is SQLite WAL under ${AIC_RUNTIME_ROOT}.
- Runtime text search uses SQLite FTS5 inside app.sqlite.
- Vector search uses FAISS under ${AIC_RUNTIME_ROOT}/indexes.
- Vector-to-keyframe mapping lives in SQLite.
- Preprocessing/staging/analytics uses DuckDB under ${AIC_DATA_ROOT}/warehouse or ${AIC_DATA_ROOT}/staging.
- MinIO is optional future adapter only through MediaStorePort.

Define data categories:
1. Raw videos
2. Official/generated keyframes
3. Thumbnails
4. Video metadata
5. Keyframe metadata
6. Captions
7. OCR text and optional boxes
8. ASR transcript segments
9. Object/concept detections
10. Scene/location/attribute tags
11. Image embeddings
12. FAISS index
13. Vector mapping
14. Query sessions
15. Query clues
16. Search runs/results
17. Candidates
18. Agent runs/steps
19. Validation reports/manifests

Define canonical IDs:
- dataset_id
- video_id without .mp4, e.g. L01_V028
- frame_id as integer
- keyframe_id = "{video_id}:{frame_id}"
- vector_id = FAISS row id
- media_ref = logical relative path, never absolute path

Define logical media refs:
- videos/{video_id}.mp4
- keyframes/{video_id}/{frame_id_padded}.jpg
- thumbnails/{video_id}/{frame_id_padded}.webp

Define physical layout:

${REPO_ROOT}/
  backend/
  frontend/
  docs/
  scripts/
  notebooks/
  config/
  schemas/
  tests/fixtures/tiny_seed_dataset/

${AIC_DATA_ROOT}/
  raw/
    videos/
    keyframes_original/
    metadata_original/
  processed/
    media/
      videos/
      keyframes/
      thumbnails/
  staging/
    shards/
    reports/
  warehouse/
    warehouse.duckdb

${AIC_RUNTIME_ROOT}/
  db/
    app.sqlite
  indexes/
    visual.faiss
    visual_index_manifest.json
  cache/

Clarify that any previous `data/` tree in docs is a logical app-ready artifact layout, not repository layout. For real competition datasets, do not put raw videos/keyframes/thumbnails in the repo.

Define SQLite schema:
- datasets
- videos
- keyframes
- captions
- ocr_texts
- asr_segments
- keyframe_asr_segments optional
- objects
- scene_tags optional
- embedding_indexes
- vector_map
- query_sessions
- query_clues
- search_runs
- search_results
- candidates
- agent_runs
- agent_steps

Define FTS5 tables:
- caption_fts
- ocr_fts
- asr_fts
- object_fts
- metadata_fts
- optional unified evidence_fts

Define FAISS mapping:
FAISS returns vector_id.
SQLite vector_map maps (index_name, vector_id) -> keyframe_id, video_id, frame_id.
All search results must resolve to keyframe_id before returning to UI.

Define MediaStorePort:
The DB stores logical refs only.
UI calls backend media endpoints.
Backend resolves refs through LocalFileMediaStore in MVP.
MinioMediaStore can be added later without changing UI/retrieval core.

Define required validation:
- no duplicate video_id
- no duplicate (video_id, frame_id)
- every media_ref resolves through MediaStorePort
- every keyframe has thumbnail_ref
- every FAISS vector has vector_map row
- every vector_map keyframe_id exists
- every caption/OCR/object row points to an existing keyframe
- every ASR segment points to an existing video
- no absolute paths in SQLite
- no machine-specific paths in SQLite
- FTS5 row counts match source data expectations

Create or update docs:
- docs/architecture/data-contracts.md
- docs/architecture/storage-strategy.md
- docs/architecture/system1-ingestion.md
- docs/architecture/ingestion.md
- docs/stories/backlog.md
- docs/validation/test-matrix.md
- docs/decisions/* if needed, but do not duplicate existing decision records

Add backlog items before runtime implementation:
- MVP-0.5 App-ready Data Contract
- MVP-0.6 Seed Dataset Builder
- MVP-1 Runtime SQLite Schema + Validation
- MVP-2 Backend API vertical slice
- MVP-3 Keyframe-first UI vertical slice

Do not start full UI/backend/retrieval implementation until the data contract and seed dataset are defined.
```

# Kết luận

Bạn đúng: **cần đi từ data contract trước**, không phải UI/backend trước.

Thứ tự đúng nhất cho project này là:

```text
1. Xác định toàn bộ loại data
2. Chốt external data root và runtime root
3. Chốt ID/mapping convention
4. Chốt storage strategy
5. Chốt SQLite schema
6. Chốt FTS5 schema
7. Chốt FAISS vector mapping
8. Chốt MediaStore refs
9. Tạo seed dataset nhỏ
10. Build backend/API vertical slice
11. Build UI vertical slice
12. Mở rộng preprocessing thật
```

Nói ngắn gọn: **runtime app chỉ nên đọc “app-ready artifacts”, không đọc raw dataset lung tung; media lớn nằm ngoài repo trên HDD; runtime hot artifacts ưu tiên SSD; SQLite chỉ lưu logical refs**. Muốn làm được vậy thì phải có `App-ready Data Contract` trước.
