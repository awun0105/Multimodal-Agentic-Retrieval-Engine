# Giải Thích Data Contract Và Luồng Dữ Liệu Retrieval

## Trạng thái

Đây là tài liệu giải thích bằng tiếng Việt, viết để đọc và kiểm tra lại logic chương trình. Nội dung dựa trên các canonical docs hiện tại. Mỗi câu trả lời đều có phần `Evidence` để bạn mở tài liệu gốc ra đối chiếu.

## Cách đọc nhanh

Nếu chỉ muốn nắm ý chính, hãy nhớ 3 câu này:

1. **System 1 chuẩn bị dữ liệu**: đọc raw data, chuẩn hóa, tạo index, tạo database, kiểm tra dữ liệu.
2. **System 2 chạy app thật**: backend/UI/agent chỉ đọc bộ dữ liệu đã chuẩn bị sẵn, không mò raw folders lúc user search.
3. **Mọi kết quả search phải map về `video_id` + `frame_id`**: vì đây là thứ người dùng cần xem, chọn, copy, export, hoặc submit.

---

## 1) Data contract trông như thế nào?

### Trả lời

Trong project này, **data contract** là bản cam kết về hình dạng dữ liệu mà app runtime được phép dùng.

Nói dễ hiểu hơn: trước khi viết backend search, UI, hoặc agent, ta phải trả lời rõ các câu hỏi:

- Dữ liệu video nằm ở đâu?
- Keyframe được đặt tên như thế nào?
- Một frame được định danh bằng ID gì?
- Metadata, caption, OCR, ASR, object được lưu ở bảng nào?
- FAISS trả về vector row thì làm sao biết đó là video/frame nào?
- App sẽ lưu query session và candidate ở đâu?

Data contract chính là câu trả lời chính thức cho các câu hỏi đó.

Logic lớn của contract:

1. **Raw data không phải runtime source of truth**.
   - Raw data có thể lộn xộn, thay đổi theo mùa giải, hoặc đến từ nhiều format khác nhau.
   - Vì vậy runtime app không nên search trực tiếp trong raw folders.

2. **System 1 biến raw data thành app-ready artifacts**.
   - App-ready nghĩa là dữ liệu đã đủ sạch, đủ mapping, đủ index để app dùng ngay.

3. **System 2 chỉ đọc app-ready artifacts**.
   - System 2 gồm backend, UI, retrieval adapters, agent runtime.
   - Nó không tự đoán cấu trúc raw dataset.

4. **Mỗi loại storage có nhiệm vụ riêng**.
   - System 1 `app.sqlite`: các bảng dataset/runtime read-only như video, scene, shot, keyframe, evidence, `text_documents`, `vector_map`, `feature_availability`, `release_capabilities`.
   - System 2 runtime DB/state: query session, search run, candidate, agent run/step.
   - SQLite FTS5: text search nằm trong `app.sqlite`, build từ global `text_documents`.
   - FAISS: vector search cho visual embeddings.
   - Filesystem: lưu file nặng như video, keyframe, thumbnail.
   - DuckDB: preprocessing/staging/validation offline, không phải runtime DB chính.

Các ID quan trọng nhất:

| ID | Ý nghĩa |
| --- | --- |
| `dataset_id` | Bộ dữ liệu hoặc version dữ liệu đang dùng. |
| `video_id` | ID video, ví dụ `L01_V028`. |
| `frame_id` | Số frame chính thức, ví dụ `25300`. |
| `keyframe_id` | ID nối giữa video và frame, format `"{video_id}:{frame_id}"`. |
| `vector_id` | Row ID do FAISS trả về. |
| `video_ref` | Đường dẫn logic tới raw video, không phải absolute path. |
| `keyframe_ref` | Đường dẫn logic tới ảnh keyframe đã generate. |
| `thumbnail_ref` | Đường dẫn logic tới thumbnail đã generate. |

Ví dụ một keyframe canonical:

```text
video_id = "L01_V028"
frame_id = 25300
keyframe_id = "L01_V028:25300"
video_ref = "media://raw_videos/L01_V028.mp4"
keyframe_ref = "media://keyframes/L01_V028/L01_V028_f0025300.jpg"
thumbnail_ref = "media://thumbnails/L01_V028/L01_V028_f0025300.webp"
```

Điểm cần check theo ý bạn: nếu app muốn hoạt động ổn định, mọi thứ phải quay về được `video_id`, `frame_id`, `keyframe_id`. Đây là xương sống của toàn bộ retrieval system.

### Evidence

- `docs/architecture/data-contracts.md:5`
- `docs/architecture/data-contracts.md:11`
- `docs/architecture/data-contracts.md:29`
- `docs/architecture/data-contracts.md:77`

---

## 2) Output của System 1 là gì?

### Trả lời

System 1 là phần **chuẩn bị dữ liệu trước khi app chạy thật**.

Bạn có thể hình dung System 1 giống một nhà máy xử lý dữ liệu:

```text
raw data lộn xộn
  -> normalize
  -> tạo evidence
  -> tạo index
  -> tạo SQLite runtime DB
  -> validate
  -> xuất ra bộ app-ready artifacts
```

Output của System 1 không chỉ là một file. Nó là cả một bộ artifact gồm database, index, media đã chuẩn hóa, mapping, và report.

### Nhóm output 1: Dataset/release metadata

Dùng để biết app đang chạy trên dataset/release nào.

Output nguồn sự thật gồm:

- `dataset_manifest.json`
- `validation_report.json`
- `release_capabilities`

System 1 v1.1 không yêu cầu bảng SQLite `datasets` là source of truth. Nếu implementation thêm bảng `datasets` để tiện query thì đó là mirror/implementation detail.

### Nhóm output 2: Media và catalog đã chuẩn hóa

Output gồm:

- bảng `videos`
- bảng `keyframes`
- logical refs tới video/keyframe/thumbnail

Tác dụng: app biết video nào có những keyframe nào, frame đó nằm ở thời điểm nào, thumbnail ở đâu, video gốc ở đâu.

### Nhóm output 3: Evidence đã import hoặc generate

Output canonical gồm:

- `asr_segments`: transcript từ audio theo time range.
- `shot_transcript_links`, `scene_transcript_links`: liên kết transcript với shot/scene.
- `ocr`: chữ xuất hiện trong frame/keyframe.
- `objects`: object/concept như person, car, bus, screen.
- `image_captions`, `shot_captions`: caption theo image/shot.
- `scene_summaries_initial`, `scene_summaries_enriched`: summary cấp scene.
- `shots` / `scenes`: ngữ cảnh thời gian để inspect sâu hơn từ keyframe về shot/scene/video.
- `feature_availability`: cho UI biết entity nào có ASR/OCR/object/caption/inspection evidence.

Tác dụng: đây là nguồn dữ liệu để search text, filter, giải thích vì sao một result match query.

### Nhóm output 4: Search indexes

Output gồm:

- FTS5-backed text search contract built from global `text_documents` inside `app.sqlite`.
- FAISS visual index cho vector search.
- `vector_map` để map FAISS vector row về keyframe.
- index manifest để biết index được build như thế nào.

Tác dụng: nếu không có index, search sẽ chậm hoặc không thể search đa modality.

### Nhóm output 5: Validation report

Output gồm:

- validation report dạng machine-readable.
- pass/fail status.

Tác dụng: app không nên chạy trên dataset hỏng. Ví dụ thiếu thumbnail, vector không map được về keyframe, hoặc SQLite chứa absolute path thì phải báo lỗi trước.

Ví dụ artifact vật lý:

```text
${AIC_DATA_ROOT}/raw/videos/{video_id}.mp4
${AIC_DATA_ROOT}/processed/media/keyframes/{video_id}/{video_id}_f{frame_id:07d}.jpg
${AIC_DATA_ROOT}/processed/media/thumbnails/{video_id}/{video_id}_f{frame_id:07d}.webp
${AIC_DATA_ROOT}/staging/frame_timeline/{video_id}.parquet
${AIC_DATA_ROOT}/staging/staging.duckdb
${AIC_DATA_ROOT}/staging/reports/{dataset_id}-validation.json
${AIC_RUNTIME_ROOT}/db/app.sqlite
${AIC_RUNTIME_ROOT}/indexes/visual.faiss
${AIC_RUNTIME_ROOT}/indexes/index_version.json
```

### Evidence

- `docs/architecture/system1-ingestion.md:7`
- `docs/architecture/system1-ingestion.md:23`
- `docs/architecture/system1-ingestion.md:62`
- `docs/architecture/data-contracts.md:104`

---

## 3) Input của System 2 là gì?

### Trả lời

System 2 là phần app chạy thật: backend, UI, search runtime, agent runtime.

Input của System 2 là **output đã được System 1 chuẩn bị**. System 2 không đọc raw folders trực tiếp khi user search.

Input tối thiểu của System 2 gồm:

### Nhóm input 1: Runtime SQLite database

File chính:

```text
${AIC_RUNTIME_ROOT}/db/app.sqlite
```

Bên trong System 1 release `app.sqlite` có các bảng read-only cho runtime:

- `videos`, `scenes`, `shots`, `keyframes`
- `asr_segments`, `ocr`, `objects`
- `image_captions`, `shot_captions`, scene summaries
- `embeddings_meta`, `text_documents`, `vector_map`
- `feature_availability`, `release_capabilities`

Query/session/candidate/agent tables như `query_sessions`, `search_runs`, `candidates`, `agent_runs`, `agent_steps` là **System 2 runtime state**, không phải System 1 release output contract.

### Nhóm input 2: Text search indexes

Nằm trong SQLite FTS5 bên trong `app.sqlite`.

Contract System 1 v1.1 là **FTS5-backed text search build từ global `text_documents`**. Các bảng FTS riêng theo từng source có thể là implementation detail optional, không phải output bắt buộc.

### Nhóm input 3: Vector search index

FAISS files:

```text
${AIC_RUNTIME_ROOT}/indexes/visual.faiss
${AIC_RUNTIME_ROOT}/indexes/index_version.json
```

FAISS giúp search theo visual embedding.

### Nhóm input 4: Media files

Media không được embed vào SQLite. SQLite chỉ lưu logical refs. Backend dùng `MediaStorePort` để resolve ra file thật hoặc URL.

Media gồm:

- videos
- keyframes
- thumbnails

### Nhóm input 5: Query từ user hoặc agent

Khi app chạy, user hoặc agent gửi thêm:

- query text
- query type: `tkis`, `qa`, `trake`, `vkis`, `hybrid`
- clue mode: ví dụ `current_only`, `accumulated`
- filters
- top-K / rerank settings

Tóm tắt:

```text
System 2 input = app-ready database + indexes + media refs + user/agent query
```

### Evidence

- `docs/architecture/system2-retrieval.md:7`
- `docs/architecture/system2-retrieval.md:17`
- `docs/architecture/data-contracts.md:129`
- `docs/product/api-contracts.md:95`

---

## 4) Dữ liệu được lưu ở đâu và lưu như thế nào?

### Trả lời

Project tách storage thành 3 vùng rõ ràng. Mục tiêu là tránh repo phình to, tránh hardcode path máy cá nhân, và giúp runtime chạy nhanh hơn.

### Vùng 1: `${REPO_ROOT}`

Đây là repo code.

Dùng để lưu:

- source code
- docs
- config
- schemas
- tiny fixtures nhỏ để test

Không dùng để lưu:

- video thật của competition
- keyframe thật số lượng lớn
- thumbnail thật số lượng lớn
- FAISS index lớn
- database runtime lớn

### Vùng 2: `${AIC_DATA_ROOT}`

Đây là nơi lưu dữ liệu lớn, thường nằm trên HDD hoặc ổ ngoài.

Dùng để lưu:

- raw videos
- optional organizer-provided/imported keyframes nếu có adapter riêng
- original metadata
- processed videos
- processed keyframes
- thumbnails
- staging shards
- validation reports
- DuckDB staging/preprocessing

Lý do: media rất nặng, không nên để trong git repo.

### Vùng 3: `${AIC_RUNTIME_ROOT}`

Đây là nơi lưu artifact runtime nóng, tốt nhất nằm trên SSD.

Dùng để lưu:

- `app.sqlite`
- SQLite WAL/SHM files
- FTS5 tables trong SQLite
- FAISS indexes
- runtime cache nhỏ

Lý do: app search cần đọc SQLite và FAISS nhanh.

### Cách lưu path trong SQLite

SQLite không lưu absolute path như:

```text
/home/user/dataset/videos/L01_V028.mp4
D:/AIC/videos/L01_V028.mp4
```

SQLite chỉ lưu logical refs như:

```text
media://raw_videos/L01_V028.mp4
media://keyframes/L01_V028/L01_V028_f0025300.jpg
media://thumbnails/L01_V028/L01_V028_f0025300.webp
```

Backend sẽ dùng config + `MediaStorePort` để resolve logical ref đó thành file thật.

Lợi ích:

- đổi máy không phải migrate database;
- đổi ổ cứng chỉ sửa config;
- sau này chuyển sang MinIO vẫn có thể giữ contract cũ;
- database portable hơn.

### Evidence

- `docs/architecture/data-contracts.md:29`
- `docs/architecture/data-contracts.md:39`
- `docs/architecture/data-contracts.md:91`
- `docs/architecture/storage-strategy.md:7`
- `docs/architecture/storage-strategy.md:25`

---

## 5) Tổng cộng có bao nhiêu file data/artifact, gồm những dạng file nào, mỗi file chứa gì?

### Trả lời

Câu này cần hiểu đúng theo contract hiện tại: system **không chốt một con số tuyệt đối cố định cho mọi dataset**, vì số file media thật sẽ phụ thuộc số video, số keyframe, số thumbnail, số shard, và cách build theo từng dataset.

Nhưng contract đã chốt rất rõ **những nhóm artifact nào phải có**, chúng nằm ở đâu, và vai trò của từng loại file là gì.

Nói cách khác:

- **không thể nói chính xác toàn hệ thống luôn có đúng N file**, vì N thay đổi theo dataset;
- **có thể nói chính xác system có bao nhiêu nhóm artifact chính**, file type nào, và từng loại chứa gì.

### 5.1) Nhìn theo nhóm artifact lớn

Ở mức canonical, có thể chia thành **7 nhóm artifact/data chính**:

1. Raw input files
2. Processed media files
3. Runtime SQLite database
4. Runtime FAISS index files
5. DuckDB staging/preprocessing files
6. Validation/report/manifests
7. Runtime cache files

Nếu nhìn theo “loại file cốt lõi mà app phụ thuộc để chạy”, thì tối thiểu có các artifact lõi sau:

1. `app.sqlite`
2. `visual.faiss`
3. `index_version.json`
4. video files đã chuẩn hóa
5. keyframe image files đã chuẩn hóa
6. thumbnail image files đã chuẩn hóa
7. validation report file
8. `staging.duckdb` cho preprocessing side

Nhưng cần nhớ rằng các nhóm media gồm **nhiều file**, không phải một file duy nhất.

### 5.2) Liệt kê chi tiết theo root và loại file

## A. Trong `${AIC_DATA_ROOT}/raw/`

Đây là dữ liệu đầu vào ban đầu.

### A1. Video gốc

Dạng file thường gặp:

- `.mp4`
- có thể có format video khác nếu organizer cung cấp, nhưng canonical raw-video logical ref hiện là `media://raw_videos/{video_id}.mp4`

Chứa gì:

- nội dung video gốc
- audio gốc để sinh ASR
- timeline gốc để map timestamp

### A2. Metadata gốc

Dạng file thường gặp:

- `.json`
- `.csv`
- `.parquet`

Chứa gì:

- title
- description
- source/channel
- duration
- fps metadata nếu có
- annotations hoặc các bảng mô tả khác tùy nguồn

Canonical input của System 1 v1.1 là `raw_videos/` + `metadata/`. Keyframes và thumbnails do System 1 generate. Nếu sau này organizer cung cấp keyframes sẵn, phần đó cần import adapter riêng và không đổi core contract.

### A3. Ghi chú về keyframe/thumbnails

Trong System 1 v1.1, keyframes và thumbnails là **output được generate**, không phải canonical input.

- `keyframe_ref` canonical: `media://keyframes/{video_id}/{video_id}_f{frame_id:07d}.jpg`
- `thumbnail_ref` canonical: `media://thumbnails/{video_id}/{video_id}_f{frame_id:07d}.webp`

Nếu sau này có organizer-provided keyframes, cần adapter import riêng để map chúng vào contract này, thay vì đổi core contract.

## B. Trong `${AIC_DATA_ROOT}/processed/media/`

Đây là media đã chuẩn hóa để app dùng.

### B1. Video runtime

Ví dụ path:

```text
${AIC_DATA_ROOT}/raw/videos/{video_id}.mp4
```

Chứa gì:

- video đã được đăng ký đúng `video_id`
- backend có thể phục vụ lại cho UI qua `MediaStorePort`

### B2. Keyframe runtime

Ví dụ path:

```text
${AIC_DATA_ROOT}/processed/media/keyframes/{video_id}/{video_id}_f{frame_id:07d}.jpg
```

Chứa gì:

- image keyframe chính thức dùng để hiển thị kết quả search
- là file mà UI mở ra khi inspect candidate

### B3. Thumbnail runtime

Ví dụ path:

```text
${AIC_DATA_ROOT}/processed/media/thumbnails/{video_id}/{video_id}_f{frame_id:07d}.webp
```

Chứa gì:

- thumbnail nhẹ hơn keyframe gốc
- dùng cho grid search results để UI tải nhanh

## C. Trong `${AIC_RUNTIME_ROOT}/db/`

### C1. `app.sqlite`

Đây là file data quan trọng nhất của runtime.

Dạng file:

- `.sqlite`

Chứa gì:

- catalog dữ liệu read-only do System 1 release
- evidence relations
- vector mapping
- `text_documents`
- FTS5-backed text search

Có những bảng chính nào?

| Bảng | Vai trò |
| --- | --- |
| `videos` | Một row cho mỗi video. |
| `scenes` | Scene-level inspection context. |
| `shots` | Shot-level inspection context. |
| `keyframes` | Một row cho mỗi keyframe. |
| `asr_segments` | Transcript gắn với `video_id` và time range. |
| `shot_transcript_links` | Link transcript segment với shot. |
| `scene_transcript_links` | Link transcript segment với scene. |
| `ocr` | OCR gắn với keyframe/frame. |
| `objects` | Object/concept detections gắn với `keyframe_id`. |
| `image_captions` | Caption gắn với image/keyframe. |
| `shot_captions` | Caption gắn với shot. |
| `scene_summaries_initial` | Summary scene ban đầu. |
| `scene_summaries_enriched` | Summary scene enriched nếu có. |
| `embeddings_meta` | Metadata về embeddings/model/index build. |
| `text_documents` | Global text search contract. |
| `vector_map` | Map `(index_name, vector_id)` về `keyframe_id`. |
| `feature_availability` | Cho UI/runtime biết evidence nào có sẵn hoặc degraded theo từng entity. |
| `release_capabilities` | Cờ capability của dataset/release để runtime bật/tắt feature an toàn. |

Các bảng như `query_sessions`, `query_clues`, `search_runs`, `search_results`, `candidates`, `agent_runs`, `agent_steps` thuộc **System 2 runtime behavior/state**, không phải System 1 release output contract.

FTS5 canonical của System 1 v1.1 được build từ global `text_documents`. Nếu implementation có thêm các bảng FTS riêng theo source thì đó là detail tùy chọn, không phải contract bắt buộc.

- optional `evidence_fts`

### C1.1. “Một bảng có phải là một quan hệ không?”

Có. Nếu nói theo ngôn ngữ của mô hình quan hệ (relational model), thì:

- **bảng** trong SQLite/PostgreSQL là cách cài đặt thực tế của một **quan hệ**;
- **mỗi dòng** là một bộ dữ liệu (tuple / record);
- **mỗi cột** là một thuộc tính (attribute).

Nói ngắn gọn để dễ hình dung:

- quan hệ = khái niệm logic;
- bảng = hình thức lưu trữ/biểu diễn của quan hệ trong database.

Trong tài liệu này, khi nói `videos`, `keyframes`, `ocr`, `objects`, `image_captions`... thì bạn có thể hiểu gần như là “các quan hệ chính của runtime database”.

### C1.2. Thuộc tính và ví dụ dữ liệu cho từng quan hệ chính

Lưu ý: canonical docs chưa chốt đủ DDL chi tiết cho mọi cột nhỏ, nhưng đã chốt rất rõ **vai trò bảng**, **khóa định danh**, và **các field cốt lõi**. Phần dưới đây viết theo mức “đủ để hình dung đúng logic chương trình”.

#### Dataset/release metadata

System 1 v1.1 dùng `dataset_manifest.json`, `validation_report.json`, và `release_capabilities` làm source of truth cho metadata build/release.

Nếu implementation có bảng `datasets` trong SQLite thì nên hiểu đó là mirror tiện query, không phải canonical source of truth.

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `dataset_id` | ID bộ dữ liệu | `aic2026` |
| `build_id` | ID lần build | `2026-06-13T00-00-00Z` |
| `status` | trạng thái dataset | `ready` |
| `created_at` | thời điểm tạo build | `2026-06-13T00:00:00Z` |
| `source_summary` | mô tả nguồn dữ liệu | `raw videos + metadata v1` |

Ví dụ một dòng:

```json
{
  "dataset_id": "aic2026",
  "build_id": "2026-06-13T00-00-00Z",
  "status": "ready",
  "created_at": "2026-06-13T00:00:00Z",
  "source_summary": "raw videos + metadata v1"
}
```

#### Quan hệ `videos`

Mỗi dòng là một video.

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `video_id` | ID video canonical | `L01_V028` |
| `video_ref` | logical ref tới raw video | `media://raw_videos/L01_V028.mp4` |
| `duration_sec` | độ dài video theo giây | `843.33` |
| `fps_detected` | FPS detect thực tế | `30.0` |
| `fps_source` | nguồn detect FPS | `avg_frame_rate` |
| `is_vfr` | video có VFR hay không | `false` |
| `frame_id_method` | cách xác định `frame_id` | `decoded_frame_timeline` |
| `frame_timeline_ref` | logical ref tới decoded frame timeline nếu có | `frame_timeline/L01_V028.parquet` |
| `fps_expected_default` | default planning/reference FPS | `25.0` |
| `width` | chiều rộng video | `1920` |
| `height` | chiều cao video | `1080` |
| `metadata_json` | metadata mở rộng | `{"source":"youtube"}` |

Ví dụ một dòng:

```json
{
  "video_id": "L01_V028",
  "video_ref": "media://raw_videos/L01_V028.mp4",
  "duration_sec": 843.33,
  "fps_detected": 30.0,
  "fps_source": "avg_frame_rate",
  "is_vfr": false,
  "frame_id_method": "decoded_frame_timeline",
  "frame_timeline_ref": "frame_timeline/L01_V028.parquet",
  "fps_expected_default": 25.0,
  "width": 1920,
  "height": 1080,
  "metadata_json": {"source": "youtube"}
}
```

#### Quan hệ `keyframes`

Mỗi dòng là một keyframe. Đây là quan hệ trung tâm của retrieval app.

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `keyframe_id` | ID canonical của keyframe | `L01_V028:25300` |
| `video_id` | video mà frame thuộc về | `L01_V028` |
| `frame_id` | số frame | `25300` |
| `timestamp_sec` | thời điểm xuất hiện trong video | `843.33` |
| `keyframe_ref` | logical ref tới ảnh keyframe | `media://keyframes/L01_V028/L01_V028_f0025300.jpg` |
| `thumbnail_ref` | logical ref tới thumbnail | `media://thumbnails/L01_V028/L01_V028_f0025300.webp` |

Ví dụ một dòng:

```json
{
  "keyframe_id": "L01_V028:25300",
  "video_id": "L01_V028",
  "frame_id": 25300,
  "timestamp_sec": 843.33,
  "keyframe_ref": "media://keyframes/L01_V028/L01_V028_f0025300.jpg",
  "thumbnail_ref": "media://thumbnails/L01_V028/L01_V028_f0025300.webp"
}
```

#### Quan hệ `image_captions` / `shot_captions`

System 1 v1.1 dùng `image_captions` cho caption cấp image/keyframe và `shot_captions` cho caption cấp shot.

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `caption_id` | ID dòng caption | `cap_0001` |
| `keyframe_id` | keyframe được mô tả | `L01_V028:25300` |
| `text` | nội dung caption | `A red bus on a rainy street.` |
| `source` | caption từ đâu | `generated_blip2` |
| `confidence` | độ tin cậy nếu có | `0.82` |

Ví dụ một dòng:

```json
{
  "caption_id": "cap_0001",
  "keyframe_id": "L01_V028:25300",
  "text": "A red bus on a rainy street.",
  "source": "generated_blip2",
  "confidence": 0.82
}
```

#### Quan hệ `ocr`

Mỗi dòng là một OCR snippet trên keyframe.

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `ocr_id` | ID dòng OCR | `ocr_0001` |
| `keyframe_id` | keyframe chứa text | `L01_V028:25300` |
| `text` | chữ OCR đọc được | `BUS STOP` |
| `confidence` | độ tin cậy OCR | `0.91` |
| `boxes_json` | bounding boxes nếu có | `[{"x":10,"y":20,"w":80,"h":30}]` |

Ví dụ một dòng:

```json
{
  "ocr_id": "ocr_0001",
  "keyframe_id": "L01_V028:25300",
  "text": "BUS STOP",
  "confidence": 0.91,
  "boxes_json": [{"x": 10, "y": 20, "w": 80, "h": 30}]
}
```

#### Quan hệ `asr_segments`

Mỗi dòng là một đoạn transcript theo time range của video.

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `asr_segment_id` | ID đoạn transcript | `asr_0001` |
| `video_id` | video chứa audio | `L01_V028` |
| `start_sec` | thời gian bắt đầu | `840.00` |
| `end_sec` | thời gian kết thúc | `845.00` |
| `text` | nội dung transcript | `The red bus is arriving.` |
| `source` | engine hoặc nguồn transcript | `whisper_large_v3` |

Ví dụ một dòng:

```json
{
  "asr_segment_id": "asr_0001",
  "video_id": "L01_V028",
  "start_sec": 840.0,
  "end_sec": 845.0,
  "text": "The red bus is arriving.",
  "source": "whisper_large_v3"
}
```

#### Quan hệ `shot_transcript_links` / `scene_transcript_links`

System 1 v1.1 canonical dùng liên kết transcript với shot/scene. Nếu implementation có thêm bảng align ASR cấp keyframe để debug thì nên coi đó là detail tùy chọn, không phải canonical release table.

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `shot_id` hoặc `scene_id` | shot/scene được align | `L01_V028_SH00042` |
| `asr_segment_id` | segment transcript liên quan | `asr_0001` |
| `overlap_score` | mức độ liên quan theo time overlap | `0.93` |

#### Quan hệ `objects`

Mỗi dòng là một object/concept detection trên keyframe.

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `object_id` | ID dòng detection | `obj_0001` |
| `keyframe_id` | keyframe chứa object | `L01_V028:25300` |
| `label` | nhãn object | `bus` |
| `score` | confidence | `0.95` |
| `box_json` | bounding box nếu có | `{"x":100,"y":150,"w":400,"h":220}` |
| `source` | model hoặc nguồn detection | `yolo_world` |

Ví dụ một dòng:

```json
{
  "object_id": "obj_0001",
  "keyframe_id": "L01_V028:25300",
  "label": "bus",
  "score": 0.95,
  "box_json": {"x": 100, "y": 150, "w": 400, "h": 220},
  "source": "yolo_world"
}
```

#### Quan hệ `shots` / `scenes`

Quan hệ timeline để inspect từ keyframe về shot/scene chứa nó.

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `scene_id` | scene chứa shot/keyframe | `L01_V028_SC00001` |
| `shot_id` | shot chứa keyframe | `L01_V028_SH00042` |
| `start_frame` | frame bắt đầu interval | `25200` |
| `end_frame` | frame kết thúc interval, exclusive | `25480` |
| `detection_method` | cách tạo shot/scene | `shot_boundary_detector` |

#### Quan hệ `embeddings_meta`

Mô tả metadata của embedding/model/index build.

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `index_name` | tên index | `visual` |
| `embedding_model` | model tạo embedding | `openclip_vit_l_14` |
| `dimension` | số chiều vector | `768` |
| `metric` | độ đo | `cosine` |
| `index_ref` | logical ref hoặc path index | `indexes/visual.faiss` |

#### Quan hệ `vector_map`

Đây là quan hệ cực kỳ quan trọng. Nó map FAISS row về keyframe thật.

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `index_name` | index nào tạo ra vector | `visual` |
| `vector_id` | row id trong FAISS | `123456` |
| `keyframe_id` | keyframe tương ứng | `L01_V028:25300` |
| `video_id` | video tương ứng | `L01_V028` |
| `frame_id` | frame tương ứng | `25300` |

Ví dụ một dòng:

```json
{
  "index_name": "visual",
  "vector_id": 123456,
  "keyframe_id": "L01_V028:25300",
  "video_id": "L01_V028",
  "frame_id": 25300
}
```

### Các quan hệ dưới đây thuộc **System 2 runtime behavior/state**

Chúng hữu ích để hiểu app chạy thật, nhưng không phải một phần của **System 1 release output contract**.

#### Quan hệ `query_sessions`

Mỗi dòng là một phiên làm việc tìm kiếm.

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `session_id` | ID session | `qs_001` |
| `name` | tên session | `Textual KIS round 1` |
| `query_type` | loại query | `tkis` |
| `client_label` | nickname người dùng | `teammate-a` |
| `clue_mode` | chế độ clue | `accumulated` |
| `notes` | ghi chú | `manual notes` |

#### Quan hệ `query_clues`

Mỗi dòng là một clue hoặc câu hỏi trong session.

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `clue_id` | ID clue | `clue_001` |
| `session_id` | session chứa clue | `qs_001` |
| `text` | nội dung clue | `red bus on rainy street` |
| `clue_batch` | clue thuộc batch nào | `1` |
| `is_active` | clue có đang dùng không | `true` |

#### Quan hệ `search_runs`

Mỗi dòng là một lần user hoặc agent bấm search.

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `search_run_id` | ID lần search | `sr_001` |
| `session_id` | session liên quan | `qs_001` |
| `query_type` | loại query | `tkis` |
| `query_text` | text search | `red bus on rainy street` |
| `top_k` | số kết quả lấy | `100` |
| `rerank_top_k` | số kết quả rerank | `50` |

#### Quan hệ `search_results`

Dùng để lưu snapshot kết quả đã xếp hạng.

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `search_run_id` | lần search nào | `sr_001` |
| `rank` | hạng của kết quả | `1` |
| `keyframe_id` | frame được trả về | `L01_V028:25300` |
| `score` | điểm cuối cùng | `0.87` |
| `score_components_json` | breakdown điểm | `{"visual":0.91,"caption":0.72}` |

#### Quan hệ `candidates`

Đây là những kết quả được user hoặc agent lưu lại để xem xét tiếp.

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `candidate_id` | ID candidate | `cand_001` |
| `session_id` | session chứa candidate | `qs_001` |
| `keyframe_id` | frame được lưu | `L01_V028:25300` |
| `video_id` | video tương ứng | `L01_V028` |
| `frame_id` | frame tương ứng | `25300` |
| `answer_text` | câu trả lời cho Q&A nếu có | `The answer is red bus.` |
| `trake_sequence` | sequence cho TRAKE nếu có | `[]` |
| `score_snapshot` | điểm tại thời điểm lưu | `0.87` |

#### Quan hệ `agent_runs`

Mỗi dòng là một lần agent chạy trong session.

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `agent_run_id` | ID lần chạy agent | `ar_001` |
| `session_id` | session liên quan | `qs_001` |
| `status` | trạng thái | `running` |
| `query_type` | loại query | `tkis` |
| `max_steps` | số bước tối đa | `8` |
| `max_runtime_sec` | thời gian tối đa | `60` |

#### Quan hệ `agent_steps`

Mỗi dòng là một bước agent đã thực hiện.

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `agent_run_id` | agent run cha | `ar_001` |
| `step_index` | bước thứ mấy | `1` |
| `tool_name` | tool đã gọi | `search` |
| `arguments_json` | tham số gọi tool | `{"query_text":"red bus"}` |
| `result_summary` | tóm tắt kết quả | `50 results returned` |

### C1.3. Quan hệ giữa các quan hệ chính

Bạn có thể hình dung nhanh bằng sơ đồ logic sau:

#### System 1 release data

```text
dataset_manifest.json / validation_report.json / release_capabilities
  -> videos
      -> scenes
          -> shots
              -> keyframes
                  -> ocr
                  -> objects
                  -> image_captions
                  -> vector_map
              -> shot_captions
              -> shot_transcript_links
          -> scene_transcript_links
          -> scene_summaries_initial
          -> scene_summaries_enriched
  -> asr_segments
  -> embeddings_meta
  -> text_documents
  -> feature_availability
```

#### System 2 runtime state

```text
query_sessions
  -> query_clues
  -> search_runs
      -> search_results
  -> candidates
  -> agent_runs
      -> agent_steps
```

Đây là cách nhìn rất gần với logic chương trình:

- `videos`, `scenes`, `shots`, `keyframes` là phần lõi media/timeline identity;
- `ocr`, `asr_segments`, `objects`, `image_captions`, `shot_captions`, `scene_summaries_*` là evidence;
- `text_documents` là global text search contract;
- `vector_map` nối FAISS với keyframes;
- `query_sessions` và các bảng con là System 2 runtime state.

### C2. WAL/SHM runtime files

Khi SQLite chạy ở WAL mode, thực tế sẽ có thêm file phụ như:

- `app.sqlite-wal`
- `app.sqlite-shm`

Chứa gì:

- transaction log và shared-memory cho SQLite WAL mode
- đây là file runtime behavior, không phải logical schema chính

### C3. Tất cả các bảng có nằm trong một file SQLite chính không?

**Theo contract MVP hiện tại: có.**

Cách hiểu đúng là:

- runtime relational data chính nằm trong **một file SQLite chính**: `app.sqlite`;
- các bảng catalog/evidence/vector mapping/text search read-only của System 1 release nằm trong file này;
- query/session/candidate/agent state thuộc System 2 runtime behavior và nên được tách khỏi phần mô tả System 1 output contract;
- ngoài `app.sqlite` có thêm `app.sqlite-wal` và `app.sqlite-shm`, nhưng đó là file runtime phụ của WAL mode, không phải “một database schema riêng”.

Vậy ở MVP hiện tại, system **không yêu cầu tách ra nhiều file DB runtime khác nhau**.

#### Khi nào mới cần chia ra DB khác?

Canonical docs hiện tại **chưa yêu cầu** chia thêm file DB runtime khác. Nếu sau này scale lớn hơn, có thể cân nhắc, nhưng đó là việc mở rộng tương lai, chưa phải contract hiện tại.

Lý do hiện tại dùng một SQLite chính:

1. Dễ giữ một source of truth duy nhất cho runtime.
2. Dễ join giữa catalog, evidence, vector mapping, session state.
3. Dễ backup, validate, và di chuyển dataset runtime.
4. Phù hợp MVP local/LAN workflow.

Nói ngắn gọn:

```text
MVP runtime DB = 1 file chính: app.sqlite
MVP vector index = file FAISS riêng
MVP media = file riêng trên filesystem
```

### C4. Vậy embeddings được lưu ở đâu?

Cần tách ra làm 2 ý khác nhau:

#### Ý 1: Metadata mô tả embedding/index

Metadata về embedding/index được lưu trong SQLite, ở quan hệ `embeddings_meta`.

Ví dụ nó lưu các thông tin như:

- tên index
- model tạo embedding
- dimension
- metric
- logical ref tới file index

#### Ý 2: Bản thân vector embeddings runtime

Theo contract MVP hiện tại, **vector runtime để search được lưu trong FAISS file**, không lưu trực tiếp trong SQLite dưới dạng cột vector lớn.

Ví dụ:

- visual embeddings sau khi build sẽ nằm trong `visual.faiss`;
- SQLite chỉ giữ metadata của index và `vector_map` để biết mỗi `vector_id` thuộc keyframe nào.

### C5. Embedding từ CLIP thì lưu ở đâu?

Nếu là **image embedding / visual embedding** từ CLIP hoặc OpenCLIP, thì theo contract hiện tại:

- vector runtime dùng để search nằm trong FAISS file, ví dụ `visual.faiss`;
- metadata của index nằm ở `embeddings_meta`;
- mapping từ `vector_id` về `keyframe_id` nằm ở `vector_map`.

Tức là flow là:

```text
CLIP image embedding
  -> build FAISS index
  -> lưu vector runtime trong visual.faiss
  -> lưu metadata index trong embeddings_meta
  -> lưu mapping trong vector_map
```

### C6. Embedding từ transcript hoặc description đi qua text encoder thì lưu ở đâu?

Phần này cần phân biệt rất rõ giữa **contract hiện tại** và **khả năng mở rộng tương lai**.

#### Theo contract MVP hiện tại

Text retrieval chính thức đang dùng:

- SQLite FTS5 build từ `text_documents` bên trong `app.sqlite`

Nghĩa là ở thời điểm hiện tại, **text search canonical chưa bắt buộc phải có một FAISS index riêng cho text embeddings**.

Vì vậy, nếu bạn đang hỏi “transcript embeddings” hoặc “description embeddings” trong MVP hiện tại, thì câu trả lời chuẩn là:

- text nội dung canonical được hợp nhất vào `text_documents`; per-source tables chỉ là nguồn/intermediate để build document;
- text search runtime canonical được thực hiện qua FTS5;
- canonical docs chưa chốt một file vector index riêng cho text embeddings ở MVP.

#### Nếu sau này muốn dùng text encoder embeddings

Nếu về sau hệ thống mở rộng để dùng:

- caption embeddings
- transcript embeddings
- text-description embeddings

thì cách lưu **hợp logic nhất theo contract hiện tại** sẽ là:

1. thêm một index mới trong FAISS hoặc vector backend tương đương;
2. đăng ký metadata index đó trong `embeddings_meta`;
3. thêm mapping vào `vector_map` với `index_name` khác, ví dụ `caption_text`, `asr_text`, hoặc `multimodal_text`;
4. vẫn giữ text gốc trong SQLite relational + FTS5 để explain/filter/debug.

Ví dụ tư duy lưu trữ:

```text
caption text
  -> lưu text gốc vào per-source tables và hợp nhất vào `text_documents` + FTS5
  -> nếu có text embedding runtime, build thêm FAISS index riêng
  -> đăng ký metadata index trong embeddings_meta
  -> map vector rows bằng vector_map
```

### C7. Vậy hiện tại system có bao nhiêu loại embedding runtime đã được canonical rõ?

**Được canonical rõ nhất hiện tại là visual/image embeddings**.

Còn các embedding kiểu:

- caption embedding
- transcript embedding
- description/text embedding
- audio embedding

mới đang ở mức “có thể generate/import nếu hữu ích”, nhưng **chưa được chốt thành runtime index bắt buộc của MVP** như visual FAISS + text FTS5.

Cách nói chính xác nhất theo docs hiện tại là:

- MVP bắt buộc có **visual vector search** bằng FAISS;
- MVP bắt buộc có **text search** bằng SQLite FTS5;
- text embeddings vectorized là hướng mở rộng hợp lý, nhưng chưa phải runtime contract bắt buộc hiện tại.

## D. Trong `${AIC_RUNTIME_ROOT}/indexes/`

### D1. `visual.faiss`

Dạng file:

- `.faiss`

Chứa gì:

- visual embedding index để search vector
- FAISS không chứa trực tiếp `video_id` hay `frame_id`
- nó chỉ chứa vector rows và cấu trúc index phục vụ nearest-neighbor search

### D2. `index_version.json`

Dạng file:

- `.json`

Chứa gì:

- metadata mô tả visual index
- có thể gồm tên index, model, dimension, metric, build info, version
- được dùng để biết index hiện tại là index nào và tương thích ra sao

## E. Trong `${AIC_DATA_ROOT}/staging/`

### E1. `staging.duckdb`

Dạng file:

- `.duckdb`

Chứa gì:

- staging tables
- preprocessing joins
- analytics/validation views
- dữ liệu trung gian để đẩy sang SQLite/FAISS

Lưu ý:

- DuckDB là để chuẩn bị dữ liệu, không phải runtime DB chính của app.

## F. Trong `${AIC_DATA_ROOT}/staging/` và `reports/`

### F1. Validation report files

Ví dụ:

```text
${AIC_DATA_ROOT}/staging/reports/{dataset_id}-validation.json
```

Dạng file:

- `.json`

Chứa gì:

- kết quả validation
- lỗi thiếu mapping
- lỗi duplicate IDs
- lỗi missing media refs
- mismatch giữa index và relational tables

### F2. Shards / intermediate files

Dạng file có thể gặp:

- `.json`
- `.csv`
- `.parquet`
- các file trung gian theo pipeline OCR/ASR/embedding

Chứa gì:

- output từng bước preprocessing
- dữ liệu trung gian để resume job dài
- debug artifacts hoặc manifests

Nhưng theo contract, các file này **không phải runtime source of truth**.

## G. Runtime cache

Trong `${AIC_RUNTIME_ROOT}/cache/` có thể có các file cache nhỏ.

Chứa gì:

- cache phục vụ runtime nhanh hơn
- cache này là disposable, không phải source of truth

### 5.3) Nếu nhìn theo data model thì dữ liệu được chia thành mấy nhóm?

Nhìn theo data model logic, có thể chia dữ liệu thành **6 nhóm chính**:

1. **Dataset/release metadata model**
   - `dataset_manifest.json`
   - `validation_report.json`
   - `release_capabilities`

2. **Media identity model**
   - `videos`
   - `keyframes`
   - logical media refs

3. **Evidence model**
   - `asr_segments`
   - `shot_transcript_links`
   - `scene_transcript_links`
   - `ocr`
   - `objects`
   - `image_captions`
   - `shot_captions`
   - `scene_summaries_initial`
   - `scene_summaries_enriched`
   - `feature_availability`

4. **Index/text model**
   - `embeddings_meta`
   - `vector_map`
   - FAISS files
   - `text_documents`
   - FTS5 build từ `text_documents`

5. **System 2 search/session model**
   - `query_sessions`
   - `query_clues`
   - `search_runs`
   - `search_results`

6. **System 2 decision/output model**
   - `candidates`
   - `agent_runs`
   - `agent_steps`

Đây là cách chia dễ hiểu nhất để check xem chương trình có đang mô tả đúng hay không.

### 5.4) Nếu cần một câu trả lời ngắn gọn nhất

Nếu ai hỏi “project này có những file data gì?”, bạn có thể trả lời ngắn như sau:

- raw videos/metadata ở `${AIC_DATA_ROOT}/raw/`
- processed videos/keyframes/thumbnails ở `${AIC_DATA_ROOT}/processed/media/`
- runtime SQLite DB ở `${AIC_RUNTIME_ROOT}/db/app.sqlite`
- runtime FAISS index ở `${AIC_RUNTIME_ROOT}/indexes/visual.faiss`
- FAISS manifest ở `${AIC_RUNTIME_ROOT}/indexes/index_version.json`
- DuckDB staging/preprocessing ở `${AIC_DATA_ROOT}/staging/staging.duckdb` nếu implementation bật staging/preprocessing
- validation reports ở `${AIC_DATA_ROOT}/staging/reports/`
- optional shard/intermediate files ở `${AIC_DATA_ROOT}/staging/shards/`

### Evidence

- `docs/architecture/data-contracts.md:29`
- `docs/architecture/data-contracts.md:39`
- `docs/architecture/data-contracts.md:104`
- `docs/architecture/data-contracts.md:141`
- `docs/architecture/data-contracts.md:164`
- `docs/architecture/system1-ingestion.md:62`
- `docs/architecture/storage-strategy.md:7`

---

## 6) System có những loại indexing nào? Bao nhiêu loại và là gì?

### Trả lời

System có 2 nhóm index chính để search, cộng thêm 1 lớp mapping bắt buộc.

## 6.1) FAISS vector index

FAISS dùng để search bằng vector embedding.

Trong MVP hiện tại, canonical artifact là:

```text
visual.faiss
```

Dùng cho:

- search hình ảnh/keyframe tương tự;
- search theo visual clue;
- VKIS hoặc các query mô tả cảnh nhìn thấy.

FAISS trả về `vector_id`, không trả về trực tiếp `video_id` hay `frame_id`. Vì vậy cần `vector_map` trong SQLite để dịch kết quả.

## 6.2) SQLite FTS5 text indexes

FTS5 dùng cho text search.

Contract System 1 v1.1 là:

```text
text_sources.parquet      # per-video/intermediate
text_documents.parquet    # global text search contract
app.sqlite FTS5           # built from text_documents
```

Nghĩa là `text_documents` là nguồn canonical cho text search global. FTS5 nên được build từ `text_documents`.

Các bảng FTS riêng theo source có thể tồn tại nếu implementation muốn tối ưu/debug theo source, nhưng không phải canonical required outputs của System 1 v1.1.

## 6.3) SQLite relational mapping layer

Đây không phải search index kiểu FAISS/FTS5, nhưng bắt buộc để hệ thống hoạt động.

Bao gồm:

- `vector_map`
- `videos`
- `keyframes`
- evidence tables
- System 1 read-only release tables
- System 2 session/candidate tables ở runtime state riêng

Tóm tắt số lượng:

- **1 nhóm vector index**: FAISS.
- **1 FTS5-backed text search contract** build từ `text_documents`.
- **Per-source FTS5 tables optional** nếu implementation cần.
- **1 relational mapping layer** trong SQLite.

### Evidence

- `docs/architecture/data-contracts.md:18`
- `docs/architecture/data-contracts.md:164`
- `docs/architecture/data-contracts.md:176`
- `docs/architecture/storage-strategy.md:17`

---

## 7) Những dữ liệu nào có thể dùng cho search strategies?

### Trả lời

Search strategies có thể dùng nhiều loại dữ liệu khác nhau. Mỗi loại dữ liệu trả lời một kiểu clue khác nhau.

| Dữ liệu | Dùng khi nào? | Ví dụ query phù hợp |
| --- | --- | --- |
| Visual embeddings | Khi clue là hình ảnh/cảnh/đối tượng nhìn thấy. | “một chiếc xe bus đỏ trên đường” |
| Captions | Khi cần mô tả nội dung tổng quát của frame. | “người đàn ông đang phát biểu” |
| OCR text | Khi clue có chữ trên biển hiệu, màn hình, tài liệu. | “có chữ Viettel trên bảng” |
| ASR transcript | Khi clue là lời nói trong video. | “ai đó nói về climate change” |
| Objects/concepts | Khi clue là vật thể hoặc concept cụ thể. | “car”, “person”, “microphone”, “stage” |
| Metadata | Khi clue liên quan video/source/topic/tag. | “video từ channel X”, “chủ đề thể thao” |
| Scene/location/attribute tags | Khi có tag ngữ cảnh bổ sung. | “indoor”, “street”, “night” |

Một query tốt có thể dùng nhiều nguồn cùng lúc. Ví dụ:

> “Một người đứng trên sân khấu, phía sau có chữ AI, đang nói về công nghệ.”

Query này có thể dùng:

- visual: sân khấu, người đứng;
- OCR: chữ “AI”;
- ASR: lời nói về công nghệ;
- object: person, stage, screen;
- caption: mô tả scene;
- metadata: topic/source nếu có.

### Evidence

- `docs/architecture/data-contracts.md:104`
- `docs/architecture/system2-retrieval.md:29`
- `docs/product/query-workflows.md:28`

---

## 8) Có thể dùng hoặc kết hợp những search strategies/methods nào từ dữ liệu đã generate?

### Trả lời

Hướng chính của hệ thống là **hybrid retrieval**: chạy nhiều cách search, sau đó hợp nhất kết quả.

Không nên nghĩ system chỉ có một nút “search text”. Đúng hơn là system có nhiều adapter:

```text
visual adapter
caption adapter
OCR adapter
ASR adapter
object adapter
metadata adapter
```

Mỗi adapter trả về một danh sách result riêng. Sau đó `FusionEngine` sẽ normalize score, merge theo `keyframe_id`, apply weight, diversify, và rerank nếu cần.

## 8.1) Visual retrieval

Dùng FAISS trên visual embeddings.

Phù hợp khi:

- clue chủ yếu là hình ảnh;
- cần tìm frame có cảnh tương tự;
- query thuộc VKIS;
- text evidence yếu hoặc không có.

Ví dụ:

```text
"khung cảnh đường phố mưa, có xe bus đỏ"
```

## 8.2) Text retrieval

Dùng FTS5 trên caption/OCR/ASR/object/metadata.

Phù hợp khi:

- clue có từ khóa rõ;
- cần tìm chữ xuất hiện trong frame;
- cần tìm lời nói trong video;
- query dạng Q&A hoặc Textual KIS.

Ví dụ:

```text
"biển hiệu có chữ pharmacy"
"người nói về artificial intelligence"
```

## 8.3) Object/concept retrieval

Dùng object labels như một nguồn search/filter/scoring.

Phù hợp khi query nhắc đến vật thể rõ:

```text
person, car, bus, screen, microphone, stage
```

Object có thể được dùng theo 2 cách:

1. Search text qua `text_documents`/FTS5 với `source_type = object_labels`, hoặc qua per-source FTS optional nếu implementation có bảng này.
2. Filter hoặc boost score nếu result có object đó.

## 8.4) Metadata retrieval

Dùng metadata để thu hẹp phạm vi search.

Phù hợp khi query liên quan:

- topic;
- source/channel;
- tag;
- duration/fps/dataset annotations;
- video context đã biết.

## 8.5) Hybrid fusion

Đây là cách kết hợp nhiều method.

Flow cơ bản:

```text
run adapters
  -> normalize score
  -> merge by keyframe_id
  -> apply query-type weights
  -> diversify/group by video nếu cần
  -> rerank top-K nếu bật
  -> build evidence summary
```

Ví dụ query type:

| Query type | Combination hợp lý |
| --- | --- |
| TKIS | visual + caption + OCR + ASR + object + metadata |
| Q&A | caption/OCR/ASR mạnh hơn, object và visual hỗ trợ |
| TRAKE | anchor search + same-video timeline + object/text/time continuity |
| VKIS | visual-first, thêm object/caption/metadata để giải thích |

### Evidence

- `docs/architecture/system2-retrieval.md:42`
- `docs/architecture/system2-retrieval.md:48`
- `docs/product/search-fusion.md:7`
- `docs/product/search-fusion.md:21`
- `docs/product/query-workflows.md:22`

---

## 9) Dữ liệu nào có thể dùng để filter search result?

### Trả lời

Filter không chỉ là lọc SQL. Trong hệ thống này, filter có thể xảy ra trước search, trong lúc fusion, hoặc sau khi có ranked results.

Các filter/control đã có trong canonical docs:

| Filter/control | Ý nghĩa |
| --- | --- |
| `video_id` | Chỉ search trong một video cụ thể. |
| `modalities` | Chỉ dùng một số nguồn như visual/caption/OCR/ASR/object/metadata. |
| `group_by_video` | Tránh result bị dồn vào một video duy nhất. |
| `query_type` | Chọn logic search cho TKIS/Q&A/TRAKE/VKIS. |
| `clue_mode` | Dùng clue hiện tại hoặc toàn bộ clue đã tích lũy. |
| `top_k` | Số result muốn lấy. |
| `rerank_top_k` | Số result đầu được rerank kỹ hơn. |

Các filter có thể hỗ trợ thêm từ data model:

- object/concept;
- metadata fields;
- score range;
- same-video neighborhood;
- time/timeline context;
- evidence availability, ví dụ chỉ lấy result có OCR hoặc ASR.

Ví dụ:

```json
{
  "filters": {
    "video_id": "L01_V028",
    "modalities": ["ocr", "caption", "object"],
    "group_by_video": false
  },
  "top_k": 100,
  "rerank_top_k": 50
}
```

Cách hiểu đúng: filter giúp user kiểm soát phạm vi search, còn fusion/rerank giúp system xếp hạng kết quả tốt hơn.

### Evidence

- `docs/product/api-contracts.md:119`
- `docs/architecture/system2-retrieval.md:57`
- `docs/product/query-workflows.md:9`
- `docs/product/search-fusion.md:42`

---

## 10) Data mapping hoạt động như thế nào?

### Trả lời

Mapping là phần quan trọng nhất để search result không bị “mất danh tính”.

Ví dụ: FAISS rất giỏi tìm vector gần nhau, nhưng FAISS không biết video nào hay frame nào. Nó chỉ trả về một số row.

Vì vậy cần mapping chain:

```text
FAISS vector_id
  -> SQLite vector_map(index_name, vector_id)
  -> keyframe_id
  -> video_id + frame_id
  -> keyframe_ref + thumbnail_ref
  -> image_captions / ocr / asr_segments / objects / metadata-derived text_documents
```

Giải thích từng bước:

1. User search bằng visual clue.
2. `FaissRetriever` query `visual.faiss`.
3. FAISS trả về `vector_id` và score.
4. Backend lookup `vector_map` trong SQLite.
5. `vector_map` cho biết vector đó thuộc `keyframe_id` nào.
6. Từ `keyframe_id`, backend lấy `video_id`, `frame_id`, timestamp, media refs.
7. Backend join thêm evidence: image captions, OCR, ASR, objects, metadata-derived text documents.
8. UI nhận result đã đầy đủ thông tin để hiển thị.

Text search cũng cần mapping:

```text
FTS5 hit
  -> keyframe_id hoặc video_id
  -> SQLite relational join
  -> UI-ready result
```

Media cũng cần mapping:

```text
keyframe_id
  -> keyframes table
  -> logical media refs
  -> MediaStorePort
  -> file thật hoặc URL để frontend hiển thị
```

ASR hơi đặc biệt:

- ASR thường gắn với `video_id + start_sec + end_sec`.
- Nó không phải lúc nào cũng gắn trực tiếp 1-1 với một keyframe.
- Nếu cần, system có thể align ASR segment về keyframe gần time range đó.

Điểm cần check theo logic chương trình: **mọi search result cuối cùng phải resolve được về `keyframe_id`, `video_id`, `frame_id` trước khi trả cho UI**.

### Evidence

- `docs/architecture/data-contracts.md:176`
- `docs/architecture/data-contracts.md:180`
- `docs/architecture/system2-retrieval.md:22`
- `docs/product/api-contracts.md:135`

---

## 11) Basic end-to-end flow: system map và làm việc với data như thế nào?

### Trả lời

Đây là luồng dễ hiểu nhất từ lúc có raw data tới lúc user chọn candidate.

## 11.1) Giai đoạn chuẩn bị dữ liệu: System 1

### Bước 1: Raw data đi vào

Input canonical ban đầu gồm:

- `raw_videos/`;
- `metadata/`.

Keyframes/OCR/ASR/image captions/object detections/embeddings nếu organizer cung cấp thì là optional imported evidence qua adapter, không phải required MVP input.

### Bước 2: Normalize data

System 1 chuẩn hóa:

- `video_id`;
- `frame_id`;
- `keyframe_id`;
- timestamps;
- media refs;
- metadata fields.

### Bước 3: Generate hoặc import evidence

System 1 tạo hoặc import qua adapter:

- `image_captions`, `shot_captions`;
- `ocr`;
- `asr_segments`;
- `objects`;
- `scene_summaries_initial`, `scene_summaries_enriched`;
- `text_documents` cho text search global.

### Bước 4: Build indexes

System 1 build:

- FAISS visual index;
- FTS5-backed text search contract built from global `text_documents` inside `app.sqlite`;
- `vector_map`;
- index manifest.

### Bước 5: Validate

System 1 kiểm tra:

- không duplicate `video_id`;
- không duplicate `(video_id, frame_id)`;
- media refs resolve được;
- keyframe có thumbnail;
- FAISS vector có mapping;
- evidence trỏ đúng keyframe/video;
- SQLite không chứa absolute path;
- FTS5 row count hợp lý.

Nếu validation fail, dataset chưa nên được xem là app-ready.

## 11.2) Giai đoạn app chạy: System 2

### Bước 6: User tạo query session

User mở UI và tạo hoặc chọn Query Session.

Session lưu:

- query type;
- current clue;
- accumulated clues;
- search history;
- notes;
- pinned candidates;
- optional agent runs.

### Bước 7: User search

User nhập query, ví dụ:

```text
"red bus on rainy street"
```

Request có thể gồm:

- query text;
- query type;
- clue mode;
- filters;
- top-K;
- rerank top-K.

### Bước 8: System 2 chạy adapters

Tùy query type, system chạy một hoặc nhiều adapter:

- visual adapter query FAISS;
- caption adapter query `text_documents`/FTS5 với source caption;
- OCR adapter query `text_documents`/FTS5 với source OCR;
- ASR adapter query `text_documents`/FTS5 với source ASR;
- object adapter query `text_documents`/FTS5 với `source_type = object_labels`;
- metadata adapter query `text_documents`/FTS5 hoặc metadata tables.

### Bước 9: Fusion và rerank

System:

- normalize score từng adapter;
- merge kết quả theo `keyframe_id`;
- tính final score theo weights;
- diversify/group by video nếu cần;
- rerank top-K nếu bật;
- build evidence summary.

### Bước 10: Trả result cho UI

Mỗi result phải có đủ:

- `keyframe_id`;
- `video_id`;
- `frame_id`;
- `timestamp_sec`;
- `thumbnail_url`;
- `keyframe_url`;
- `video_url`;
- `score`;
- `score_components`;
- evidence;
- warnings.

### Bước 11: User inspect candidate

User click result để xem:

- thumbnail/keyframe lớn;
- video seek tới timestamp;
- nearby keyframes;
- evidence blocks;
- score breakdown.

### Bước 12: User save/export hoặc agent đề xuất

User có thể:

- pin candidate;
- save candidate;
- edit answer cho Q&A;
- tạo frame sequence cho TRAKE;
- export `video_id,frame_id`;
- để agent chạy cùng APIs và đề xuất candidate.

Flow tóm tắt:

```text
raw organizer data
  -> System 1 normalize + index + validate
  -> app-ready SQLite + FTS5 + FAISS + media refs
  -> System 2 query adapters
  -> fusion/rerank
  -> evidence-rich keyframe results
  -> inspect/save/export/agent actions
```

Nếu muốn check chương trình có đúng ý không, hãy kiểm tra 3 điểm:

1. Runtime có đọc raw folder trực tiếp không? Nếu có, sai contract.
2. Search result có resolve được về `keyframe_id`, `video_id`, `frame_id` không? Nếu không, sai mapping.
3. Media path trong SQLite có phải logical ref không? Nếu là absolute path, sai storage rule.

### Evidence

- `docs/architecture/system1-ingestion.md:11`
- `docs/architecture/system2-retrieval.md:7`
- `docs/product/api-contracts.md:95`
- `docs/product/query-workflows.md:70`
