# System 1 Specification v1.1

## HCMC AI Challenge 2026 — Multimedia Dataset Factory

---

## Định nghĩa ngắn gọn

**System 1** là toàn bộ pipeline xử lý dữ liệu từ dataset thô của Ban Tổ chức đến khi tạo ra bộ dữ liệu đã chuẩn hóa, có cấu trúc, có feature, có mapping, có index và sẵn sàng để **System 2** sử dụng.

```text
System 1 = Data Preparation / Preprocessing / Index Factory

Raw videos + metadata JSON
→ metadata normalization
→ batch assignment
→ ASR
→ shot detection
→ scene construction
→ keyframe selection
→ thumbnail generation
→ OCR / object detection / image captioning / visual embedding
→ artifact packaging
→ merge structural + feature artifacts
→ global text document construction
→ app.sqlite + FTS5 build
→ FAISS + vector_map build
→ validation
→ competition_dataset_vXXX release
```

**System 2** là runtime retrieval web app, nằm ngoài phạm vi của SPEC này.

SPEC v1.1 giữ nguyên hướng kiến trúc của v1.0, nhưng bổ sung thêm các contract vận hành để System 1 có thể được code, rerun, validate, debug và bàn giao ổn định cho team 3–5 người trong bối cảnh competition-grade production pipeline.

## Design principles to preserve

System 1 nên đi theo triết lý:

1. **Rich producer, tolerant consumer**
   - System 1 tạo càng nhiều dữ liệu hữu ích càng tốt vì đây là pipeline offline tốn chi phí chạy.
   - System 2 chỉ phụ thuộc cứng vào core runtime contract ổn định.
   - Các enrichment như shot, scene, caption, OCR, object phải là first-class artifacts, nhưng System 2 phải fallback được nếu một phần degraded.

2. **Core runtime contract tách khỏi staging contract**
   - DuckDB, parquet trung gian, notebook checkpoint, debug manifest là internal/staging contract của System 1.
  - `app.sqlite`, FTS5 tables, FAISS, `vector_map`, `video_ref`/logical media refs, validation report là app-ready contract cho System 2.

3. **No hardcoded environment assumptions**
   - Không hardcode absolute path cá nhân.
   - Không hardcode FPS thật của video.
   - Không hardcode assumption rằng mọi enrichment luôn tồn tại và luôn hoàn hảo.

4. **Runtime inspection is first-class**
   - Retrieval top-k chỉ là bước đầu.
   - System 1 phải tạo đủ metadata để System 2 inspect sâu theo `keyframe -> shot -> scene -> video`, xem context lân cận, và hỗ trợ chọn lại frame chính xác hơn.

5. **Generated once, reused many times**
   - Output phải đủ giàu để hỗ trợ feature hiện tại và feature tương lai.
   - Mọi artifact phải versioned, rebuildable, independently validated, và dễ hiểu cho người maintain sau này.

---

# 1. Mục tiêu

## Mục tiêu chính

System 1 phải tạo ra một bộ dữ liệu chuẩn:

```text
competition_dataset_vXXX/
```

Bộ dữ liệu này phải cho phép System 2:

1. Search theo video metadata.
2. Search theo transcript / ASR.
3. Search theo scene text / scene summary.
4. Search theo shot caption.
5. Search theo OCR.
6. Search theo object.
7. Search theo visual embedding của keyframe.
8. Truy ngược từ bất kỳ result nào về:

   * video;
   * scene;
   * shot;
   * keyframe;
   * frame_id theo actual probed fps/timeline;
   * transcript;
   * OCR;
   * caption;
   * logical media ref của video gốc.
9. Extract dense frames runtime nếu cần, dựa trên `video_ref` của video gốc và shot/scene boundary.

## Runtime contract levels

Không phải mọi output của System 1 đều có cùng mức độ bắt buộc.

### Core runtime contract

System 2 được phép phụ thuộc cứng vào:

- `videos`
- `keyframes`
- `thumbnails`
- `app.sqlite`
- FTS5-backed text search contract
- `visual.faiss`
- `vector_map`
- `video_ref` and logical media refs
- validation report

### First-class enrichment contract

System 1 nên sinh ra đầy đủ nhất có thể:

- `asr_segments`
- `ocr`
- `objects`
- `image_captions`
- `shots`
- `scenes`
- `shot_captions`
- `scene_summaries`
- `text_documents`
- quality/debug manifests

Nguyên tắc:

- Enrichment nào có thì System 2 tận dụng tối đa.
- Enrichment nào degraded hoặc unavailable thì UI/runtime fallback thay vì hỏng toàn bộ.
- `shots` và `scenes` là first-class inspection artifacts: rất quan trọng cho inspect UX, nhưng không được làm core retrieval unusable nếu một phần segmentation degraded ở một subset video.

## Non-goals

System 1 **không làm**:

```text
- Không làm Web UI.
- Không làm interactive search runtime.
- Không làm query session runtime.
- Không làm candidate basket.
- Không làm submit API.
- Không làm submit history.
- Không làm dense frame extraction trong lúc thi.
```

System 1 chỉ chuẩn bị dữ liệu để System 2 dùng.

---

# 2. Input từ Ban Tổ chức

Theo giả định hiện tại, dataset BTC cung cấp gồm:

```text
dataset/
├── raw_videos/
│   ├── L21_V001.mp4
│   ├── L21_V002.mp4
│   └── ...
│
└── metadata/
    ├── L21_V001.json
    ├── L21_V002.json
    └── ...
```

Dataset dự kiến:

```text
300GB–500GB raw videos
metadata JSON theo từng video
FPS: expected/default 25, nhưng actual fps phải được probe và persist theo từng video
```

Metadata JSON có thể chứa:

```text
author
channel_id
channel_url
description
keywords
length
publish_date
thumbnail_url
title
watch_url
```

---

# 3. Output cuối cùng cho System 2

System 1 release một bộ artifact app-ready và staging-ready.

Về mặt logic có thể đóng gói thành một release folder duy nhất. Về mặt contract phải tách rõ:

- **runtime outputs**: System 2 đọc trực tiếp.
- **staging/debug outputs**: System 1 dùng để build, validate, audit, retry.

Layout tham chiếu:

```text
competition_dataset_v001/
├── db/
│   ├── app.sqlite
│   └── staging.duckdb
│
├── indexes/
│   ├── visual.faiss
│   ├── vector_map.parquet
│   └── index_version.json
│
├── media/
│   ├── keyframes/
│   ├── thumbnails/
│   └── dense_frame_cache/          # optional empty folder for System 2 runtime
│
├── tables/
│   ├── videos.parquet
│   ├── asr_segments.parquet
│   ├── scenes.parquet
│   ├── shots.parquet
│   ├── frame_timeline.parquet          # staging/debug; may be sampled or omitted from compact release if too large
│   ├── keyframes.parquet
│   ├── shot_transcript_links.parquet
│   ├── scene_transcript_links.parquet
│   ├── embeddings_meta.parquet
│   ├── ocr.parquet
│   ├── objects.parquet
│   ├── image_captions.parquet
│   ├── shot_captions.parquet
│   ├── scene_summaries_initial.parquet
│   ├── scene_summaries_enriched.parquet
│   ├── text_sources.parquet
│   ├── feature_availability.parquet
│   └── text_documents.parquet
│
├── manifests/
│   ├── dataset_manifest.json
│   ├── artifact_manifest.parquet
│   ├── video_processing_status.parquet
│   ├── quality_report.parquet
│   ├── validation_report.json
│   └── validation_errors.jsonl
│
└── raw_mapping/
    └── media_store_manifest.parquet
```

Notes:

- `app.sqlite` là runtime source of truth cho System 2.
- DuckDB/parquet là staging/debug layer, không phải runtime source of truth chính.
- FTS5 mặc định phải nằm trong `app.sqlite` để System 2 chỉ cần một runtime DB. Không tạo `text_fts.sqlite` riêng trong MVP trừ khi có decision record mới nêu rõ lý do vận hành.
- Không lưu absolute raw video path trong runtime DB. Runtime lưu `video_ref`, `keyframe_ref`, `thumbnail_ref` như các logical media refs chính; path thật resolve qua config hoặc `MediaStore` adapter.

---

# 4. Core data hierarchy

System 1 phải tạo được hierarchy metadata:

```text
Video
├── Scene
│   ├── Shot
│   │   ├── Frame
│   │   └── Keyframe
│   └── Shot
│       └── Keyframe
└── Scene
    └── Shot
        └── Keyframe
```

## Video

Video là file `.mp4` gốc.

Video chứa:

```text
metadata JSON
ASR transcript
scenes
shots
keyframes
features
```

## Scene

Scene là đoạn nội dung/chủ đề tương đối hoàn chỉnh.

Scene là **temporal metadata over original video**, không phải file `.mp4` cắt riêng theo mặc định.

Ví dụ:

```text
Scene 1: bản tin giao thông
Scene 2: phỏng vấn người dân
Scene 3: tin bóng đá
```

Scene có thể gồm nhiều shot.

Scene nên chứa tối thiểu:

```text
scene_id
video_id
start_sec
end_sec
start_frame
end_frame
summary (optional/degraded allowed)
quality/status metadata
```

Scene boundary phải dựa trên shot boundary:

```text
scene.start_frame = first_shot.start_frame
scene.end_frame = last_shot.end_frame
```

Quyết định kiến trúc:

```text
Shots are more canonical than scenes.
Scenes are derived from shots + ASR + metadata + optional semantic grouping.
Scenes có thể rebuild độc lập mà không cần rerun ASR, shot detection, keyframe extraction, OCR hoặc embeddings.
```

Scene rebuild dependency:

```text
change scene heuristic
→ rebuild scenes
→ remap shots.scene_id
→ remap keyframes.scene_id
→ recompute scene/shot/keyframe counts
→ rebuild scene summaries/text_documents/FTS
→ no need to rerun image extraction/OCR/embedding
```

System 2 phải có khả năng fallback về shot + keyframe + ASR segment nếu scene quality chưa tốt.

## Shot

Shot là đoạn hình ảnh liên tục, thường không có camera cut lớn.

Shot là **temporal metadata over original video**, không phải file `.mp4` cắt riêng theo mặc định.

Ví dụ:

```text
Shot 1: MC đọc bản tin
Shot 2: cảnh đường phố
Shot 3: phỏng vấn người dân
Shot 4: quay lại MC
```

Shot là đơn vị visual. Scene là đơn vị semantic.

Shot nên chứa tối thiểu:

```text
shot_id
video_id
scene_id (nullable during degraded enrichment states)
start_sec
end_sec
start_frame
end_frame
representative_keyframe_id (optional)
quality/status metadata
```

## Frame

Frame là frame gốc trong video theo actual probed fps/timeline của video.

```text
frame_id = decoded original frame index
```

## Keyframe

Keyframe là frame đại diện cho shot hoặc một phần trong shot.

Keyframe dùng cho:

```text
search
preview
visual embedding
OCR
object detection
image captioning
```

---

# 5. Frame ID convention

FPS planning default là **25 FPS**, nhưng actual fps phải được probe và persist theo từng video.

Frame ID policy:

```text
Primary:
  frame_id = decoded original frame index when frame is extracted.

Fallback:
  frame_id = floor(timestamp_sec * fps_detected) only for CFR videos or when decoded frame index is unavailable.

Persist:
  fps_detected
  fps_source
  is_vfr
  frame_id_method
  timestamp_sec
  pts_time
```

Boundary convention:

```text
[start_frame, end_frame)
```

Tức là:

```text
start_frame: inclusive
end_frame: exclusive
```

Ví dụ:

```text
shot.start_frame = 1000
shot.end_frame = 1250

Shot chứa frame 1000 đến 1249.
```

Phải phân biệt:

```text
frame_id      = frame index gốc dùng cho submit/search mapping
keyframe_index = thứ tự keyframe nội bộ trong video
```

Không được dùng `keyframe_index` để submit.

Canonical identity rules:

```text
video_id    = filename stem của raw video sau khi pair và validate uniqueness
frame_id    = frame index theo actual probed fps/timeline
keyframe_id = {video_id}:{frame_id}
```

Lý do:

- ngắn gọn;
- stable;
- dễ debug bằng mắt;
- không phụ thuộc model, batch, shard, hay release version.

---

# 6. Media convention

## Keyframe

```yaml
keyframe:
  format: jpg
  quality: 90
  long_side: 960
```

## Thumbnail

```yaml
thumbnail:
  format: webp
  quality: 75
  width: 256
```

## Naming convention

```text
{video_id}_f{frame_id:07d}.jpg
{video_id}_f{frame_id:07d}.webp
```

Đây là **tên file artifact**, không phải canonical runtime ID.

Runtime contract nên ưu tiên:

```text
keyframe_id = {video_id}:{frame_id}
keyframe_ref = media://keyframes/{video_id}/{video_id}_f{frame_id:07d}.jpg
thumbnail_ref = media://thumbnails/{video_id}/{video_id}_f{frame_id:07d}.webp
video_ref = media://raw_videos/{video_id}.mp4
```

Physical media layout:

```text
media/keyframes/{video_id}/{video_id}_f{frame_id:07d}.jpg
media/thumbnails/{video_id}/{video_id}_f{frame_id:07d}.webp
raw video is not copied into the release package by default; `video_ref` resolves through media_store_manifest
```

Canonical ref guidance:

```text
video_ref = canonical raw video logical ref
keyframe_ref = canonical keyframe logical ref
thumbnail_ref = canonical thumbnail logical ref
media_ref = generic adapter field name only when a table needs one abstract media column
```

Nguyên tắc:

- Runtime DB ưu tiên các logical refs canonical như `video_ref`, `keyframe_ref`, `thumbnail_ref`.
- Physical path thật được resolve qua config hoặc `MediaStore` adapter.
- Staging/debug manifests có thể giữ physical path nếu cần audit, nhưng runtime DB không được phụ thuộc vào absolute path.

Ví dụ:

```text
L21_V001_f0000000.jpg
L21_V001_f0000050.jpg
L21_V001_f0000250.jpg

L21_V001_f0000000.webp
L21_V001_f0000050.webp
L21_V001_f0000250.webp
```

---

# 7. Storage strategy

## Shared Hugging Face storage

Primary shared storage uses exactly two Hugging Face Dataset repos:

```text
AIC26_raw
AIC26_release
```

Do not use Team Drive as the primary shared storage contract and do not create
a third Hugging Face repo for System 1 outputs.

`AIC26_raw` is the canonical raw dataset repo. It contains only standardized
raw videos, metadata, and raw-level inventory/import manifests:

```text
AIC26_raw/
└── canonical_raw_v003/
    ├── raw_videos/
    │   ├── L21_V001.mp4
    │   ├── L21_V002.mp4
    │   └── ...
    ├── metadata/
    │   ├── L21_V001.json
    │   ├── L21_V002.json
    │   └── ...
    └── manifests/
        ├── canonical_file_manifest.jsonl
        ├── canonical_import_report.json
        ├── canonical_video_inventory.parquet
        ├── missing_metadata.json
        └── unmatched_metadata.json
```

`AIC26_raw` must not contain structure artifacts, feature artifacts, merged
tables, `app.sqlite`, FAISS indexes, or final release packages.

`missing_metadata.json` and `unmatched_metadata.json` SHOULD live in
`AIC26_raw` as raw-level audit manifests because they describe the integrity of
`raw_videos/` and `metadata/` for a `raw_import_id`. Their authoritative source
of truth is:

```text
AIC26_raw/canonical_raw_vXXX/manifests/
```

`AIC26_release` MAY also contain copies of these audits under
`phase00_ingestion/reports/` as release-run snapshots. Those copies are for
reproducibility and debugging of that release run, not the source of truth.

`AIC26_release` is the processed workspace plus final release repo. It contains
phase00 ingestion output, phase01 structure artifacts, phase02 feature
artifacts, phase03 merged staging, final app-ready releases, logs, and
checkpoints. `AIC26_release` is not only the final release folder.

Rule of thumb:

```text
AIC26_raw     = standardized source data that changes rarely.
AIC26_release = artifacts and reports for a specific pipeline run/release.
```

## Local machine / server

Dùng để merge, validate, build final package.

```text
HDD:
- raw videos
- keyframes
- thumbnails
- extracted artifacts

SSD:
- app.sqlite
- FTS5 tables/indexes
- visual.faiss
- vector_map.parquet
- staging.duckdb
```

## RAM constraint

System 1 không được giả định RAM lớn.

Thiết kế ưu tiên:

```text
Parquet
DuckDB
SQLite
FAISS
batch processing
per-video artifacts
```

Không dùng các service nặng như Milvus/OpenSearch/Kafka trong System 1 MVP.

---

# 8. Canonical ID contract

Tất cả ID quan trọng trong System 1 phải deterministic.

Không dùng random UUID cho các entity chính nếu không thật sự cần.

Mục tiêu:

```text
- rerun không làm vỡ mapping;
- merge nhiều batch không sinh duplicate mơ hồ;
- System 2 không phụ thuộc vào thứ tự ngầm của file hoặc index.
```

## Canonical IDs

```text
video_id:
  lấy từ filename, bỏ extension
  ví dụ: L21_V001

scene_id:
  {video_id}_SC{scene_index:05d}
  ví dụ: L21_V001_SC00001

shot_id:
  {video_id}_SH{shot_index:05d}
  ví dụ: L21_V001_SH00023

keyframe_id:
  {video_id}:{frame_id}
  ví dụ: L21_V001:1250

embedding_id:
  {keyframe_id}_{embedding_model_slug}

doc_id:
  hash(source_type + entity_id + normalized_text)
```

## Vector mapping

`vector_id` có thể là số thứ tự trong lúc build FAISS, nhưng bắt buộc phải có mapping rõ ràng:

```text
vector_id
→ embedding_id
→ keyframe_id
→ shot_id
→ scene_id
→ video_id
```

System 2 không được phụ thuộc vào thứ tự ngầm trong `.npy` hoặc FAISS row order.

## ID stability rules

```text
- đổi model không được làm đổi video_id / shot_id / scene_id / keyframe_id;
- đổi scene heuristic có thể làm đổi scene_id, nhưng không được làm đổi shot_id;
- đổi embedding model có thể sinh embedding_id mới, nhưng keyframe_id phải giữ nguyên;
- doc_id phải stable nếu source_type, entity_id và normalized_text không đổi.
```

---

# 9. Dataset layering model

System 1 phải được hiểu như 3 tầng dữ liệu rõ ràng:

```text
Layer 1: canonical_per_video
- per-video structure artifact
- per-video feature artifact
- source of truth theo từng video

Layer 2: dataset_merged
- merged parquet tables
- staging.duckdb
- validation reports
- global text_documents.parquet

Layer 3: runtime_release
- app.sqlite
- FTS5 tables/indexes
- visual.faiss
- vector_map.parquet
- keyframes/thumbnails
- dataset_manifest.json
```

Mục tiêu của mô hình này:

```text
- tách per-video truth khỏi merged truth;
- tách merged truth khỏi serving package cho System 2;
- cho phép rerun từng tầng mà không làm rối toàn pipeline.
```

---

# 10. Artifact strategy

## Vì sao dùng ZIP?

Vì nếu upload hàng trăm nghìn keyframe/thumbnail rời rạc lên shared storage
như Hugging Face Dataset repos:

```text
- chậm;
- dễ rate limit;
- khó retry;
- khó biết video nào đã xử lý xong;
- dễ thiếu file;
- khó validate.
```

Do đó, mỗi video nên xuất thành các artifact ZIP.

## Structure artifact

```text
L21_V001_structure.zip
```

Chứa dữ liệu cấu trúc:

```text
L21_V001/
├── metadata_normalized.json
├── asr_segments.parquet
├── shots.parquet
├── scenes.parquet
├── keyframes.parquet
├── shot_transcript_links.parquet
├── scene_transcript_links.parquet
├── scene_summaries_initial.parquet
├── keyframes/
│   ├── L21_V001_f0000000.jpg
│   └── ...
├── thumbnails/
│   ├── L21_V001_f0000000.webp
│   └── ...
├── manifest.json
└── errors.jsonl
```

## Feature artifact

```text
L21_V001_features.zip
```

Chứa dữ liệu feature:

```text
L21_V001/
├── visual_embeddings.npy
├── embeddings_meta.parquet
├── ocr.parquet
├── objects.parquet
├── image_captions.parquet
├── shot_captions.parquet
├── scene_summaries_enriched.parquet
├── text_sources.parquet
├── feature_manifest.json
└── errors.jsonl
```

Lưu ý:

```text
text_sources.parquet = text fragments cấp video.
text_documents.parquet = global text table, build sau merge toàn dataset.
feature_availability.parquet = global availability table, build sau merge toàn dataset.
```

Không nên để `text_documents.parquet` trong từng per-video feature artifact nếu nó là global index table.
Không nên để `feature_availability.parquet` trong từng per-video feature artifact; per-video status nằm trong `feature_manifest.json`.

---

# 11. Reproducibility contract

Mỗi artifact và mỗi release phải biết chính xác nó được sinh bằng gì.

Tối thiểu, `manifest.json`, `feature_manifest.json` và `dataset_manifest.json` phải chứa:

```json
{
  "pipeline_run_id": "run_2026_07_01_001",
  "system1_version": "1.1.0",
  "schema_version": "1.0.0",
  "pipeline_git_commit": "abc1234",
  "config_hash": "sha256:...",
  "config_version": "2026-07-01",
  "created_at": "2026-07-01T10:30:00+07:00",
  "created_by": "worker_03",
  "environment": {
    "platform": "kaggle",
    "python": "3.10",
    "cuda": "12.1",
    "gpu": "T4"
  },
  "models": {
    "asr": "whisper-large-v3",
    "shot_detector": "pyscenedetect-content",
    "embedding": "clip-vit-base-patch32",
    "ocr": "paddleocr",
    "caption": "blip2"
  },
  "thresholds": {
    "shot_threshold": 27.0,
    "scene_similarity_threshold": 0.72,
    "ocr_min_confidence": 0.5
  }
}
```

Không có phần này thì team không thể giải thích vì sao hai lần chạy cho ra kết quả khác nhau.

---

# 12. Artifact manifest & checksum contract

Mỗi ZIP artifact phải có manifest liệt kê đầy đủ file bên trong, kèm size và checksum.

Ví dụ:

```json
{
  "artifact_id": "L21_V001_structure",
  "video_id": "L21_V001",
  "artifact_type": "structure",
  "status": "complete",
  "files": [
    {
      "path": "L21_V001/shots.parquet",
      "size_bytes": 18231,
      "sha256": "..."
    },
    {
      "path": "L21_V001/keyframes/L21_V001_f0001250.jpg",
      "size_bytes": 108230,
      "sha256": "..."
    }
  ]
}
```

Merge phase phải kiểm tra tối thiểu:

```text
file exists
size matches
checksum matches
schema matches
```

---

# 13. Failure policy

System 1 phải định nghĩa rõ required artifact, optional artifact và cách xử lý khi fail.

## Failure classification

| Artifact / Step     | Required?                  | Nếu fail thì sao?                       |
| ------------------- | -------------------------: | --------------------------------------- |
| metadata normalized |                   Required | video fail                              |
| video_ref / logical media ref mapping | Required | video fail |
| shots.parquet       |                   Required | video fail                              |
| keyframes.parquet   |                   Required | video fail                              |
| keyframe `.jpg`     |                   Required | video fail                              |
| thumbnail `.webp`   |            Required for UI | warning hoặc fail tùy release tier      |
| ASR                 |                  Important | warning nếu fail, vẫn release được      |
| scenes              |                  Important | fallback scene = group theo shot/window |
| visual embeddings   | Required for visual search | fail nếu release tier cần visual        |
| OCR                 |            Optional/Silver | warning                                 |
| object detection    |              Optional/Gold | warning                                 |
| captions            |              Optional/Gold | warning                                 |
| text_documents      |   Required for text search | fail nếu release có FTS                 |
| FAISS               |   Required for visual tier | fail                                    |
| SQLite runtime      |                   Required | fail                                    |
| FTS                 | Required nếu text enabled  | fail                                    |

Clarifications:

- If shot detection fails but raw video metadata is valid, create one `fallback_full_video` shot and mark the video `completed_with_warnings` / degraded. Missing or corrupt `shots.parquet` after fallback is a video fail.
- If ASR fails, emit an empty schema-valid `asr_segments.parquet` plus explicit failed status so downstream merge/index code does not crash.

## Video processing status state machine

`video_processing_status.parquet` phải hỗ trợ các trạng thái:

```text
pending
running
completed
completed_with_warnings
failed_retryable
failed_final
skipped
```

Mỗi row nên có thêm:

```text
failed_phase
error_code
error_message
retry_count
last_attempt_at
```

---

# 14. Quality gates

Validation không chỉ là schema validation. System 1 phải có quality metrics và pass/warn/fail thresholds.

## ASR

```text
asr_segment_count
asr_non_empty_rate
asr_chars_per_second
language_detected
asr_empty_duration_ratio
```

Ví dụ:

```text
warn nếu asr_non_empty_rate < 0.3
```

## Shot detection

```text
shot_count
median_shot_duration
short_shot_rate
long_shot_rate
```

## Keyframes

```text
keyframe_count
keyframes_per_minute
missing_thumbnail_rate
duplicate_keyframe_rate
```

## Embeddings

```text
embedding_count
missing_embedding_rate
nan_vector_count
zero_norm_vector_count
norm_mean
norm_std
```

Ví dụ:

```text
fail nếu nan_vector_count > 0
fail nếu missing_embedding_rate > 0.01
```

## OCR / captions / summaries

```text
ocr_non_empty_rate
ocr_avg_confidence

empty_caption_rate
duplicate_caption_rate
avg_caption_length

empty_summary_rate
avg_summary_length
scene_confidence_mean
```

Các metric này nên được lưu vào:

```text
quality_report.parquet
validation_report.json
```

---

# 15. Text normalization contract

Mọi nguồn text phải giữ cả raw text và normalized text.

`normalized_text` nên áp dụng thống nhất cho metadata, ASR, OCR, captions, summaries.

```text
raw_text:
  text gốc

normalized_text:
  unicode normalized
  trim whitespace
  collapse multiple spaces
  normalize punctuation nhẹ
  remove broken URLs nếu cần
  lowercase optional theo config
```

Với tiếng Việt:

```text
- không bỏ dấu tiếng Việt mặc định;
- có thể tạo thêm normalized_no_diacritics để phục vụ search nếu cần.
```

Schema text nên ưu tiên có:

```text
raw_text
normalized_text
normalized_no_diacritics
language
```

---

# 16. `text_documents.parquet` contract

`text_sources.parquet` là per-video intermediate text table.

`text_documents.parquet` là global text table, chỉ build sau merge toàn dataset.

Schema đề xuất:

```text
doc_id
level
entity_id
video_id
scene_id
shot_id
keyframe_id
source_type
raw_text
normalized_text
normalized_no_diacritics
language
weight
source_priority
token_count
dedup_key
created_at
pipeline_run_id
```

`source_type` gợi ý:

```text
video_title
video_description
video_keywords
asr
scene_summary_initial
scene_summary_enriched
scene_keywords
shot_caption
image_caption
ocr
object_labels
```

Text V1 nên bắt đầu với source ít rủi ro:

```text
video_title
video_description
video_keywords
asr
ocr
image_caption
object_labels
```

Các source dựa trên shot/scene summary có thể bật khi `inspection_context` đủ tốt. Không nên để text search V1 phụ thuộc cứng vào scene/shot enrichment.

FTS strategy:

```text
tokenizer: unicode61
remove_diacritics: configurable
index_columns: normalized_text, normalized_no_diacritics, source_type, entity fields
search_modes: diacritics-preserving exact, no-diacritics fallback, BM25 + source weight rerank
```

Ranking prior ban đầu có thể là:

```text
video_title: 1.2
video_keywords: 1.1
scene_summary_enriched: 1.1
ocr: 1.0
asr: 0.9
shot_caption: 0.9
image_caption: 0.8
object_labels: 0.7
video_description: 0.6
```

`dedup_key` gợi ý:

```text
hash(level + entity_id + source_type + normalized_text)
```

---

# 17. Incremental rebuild dependency graph

System 1 chưa cần incremental engine hoàn chỉnh, nhưng phải chốt dependency để rerun đúng scope.

```text
metadata_normalized
  depends on raw metadata JSON

asr_segments
  depends on raw video/audio + ASR config

shots
  depends on raw video + shot detector config

scenes
  depends on shots + asr_segments + metadata + scene builder config

keyframes
  depends on shots + raw video + keyframe config

keyframes.scene_id
  depends on scenes + shot_id mapping

embeddings
  depends on keyframes + embedding model config

ocr
  depends on keyframes + OCR config

objects
  depends on keyframes + object model config

image_captions
  depends on keyframes + caption model config

shot_captions
  depends on image_captions + keyframes + shots

scene_summaries_enriched
  depends on asr + ocr + object_labels + captions

text_sources
  depends on metadata + asr + summaries + captions + ocr + object_labels

text_documents
  depends on all merged text_sources

FTS
  depends on text_documents

FAISS
  depends on visual_embeddings + embeddings_meta
```

Ví dụ ứng dụng:

```text
đổi scene heuristic
→ rebuild scenes + downstream summaries/text
→ không cần rerun OCR/embeddings

đổi OCR model
→ rebuild OCR + text_sources + FTS
→ không cần rerun keyframes/shots
```

---

# 18. Release tiers

Để team không bị kẹt vì muốn Gold ngay từ đầu, System 1 nên hỗ trợ release tier.

## Bronze

```text
metadata
keyframes
thumbnails
visual embeddings
visual.faiss
app.sqlite
text_documents from metadata title/description/keywords
FTS5-backed text search contract
core video_ref/logical media ref mapping
```

## Silver

```text
Bronze
+ ASR
+ scenes or degraded inspection fallback
+ OCR
+ ASR/OCR-backed text_documents
```

## Gold

```text
Silver
+ image captions
+ shot captions
+ enriched scene summaries
+ object detection
+ quality reports đầy đủ
```

---

# 19. Lineage / provenance columns

System 1 không cần data catalog enterprise, nhưng các bảng sinh bởi model phải đủ provenance để debug.

Các bảng sau nên có provenance columns:

```text
asr_segments
shots
scenes
keyframes
ocr
objects
image_captions
shot_captions
scene_summaries
embeddings_meta
text_sources
```

Columns tối thiểu:

```text
source_artifact
batch_id
worker_id
pipeline_run_id
model_name
model_version
config_hash
created_at
```

## `frame_timeline.parquet` schema

This staging/debug table is used when frame-accurate timestamp mapping matters, especially for VFR files or videos with unreliable metadata FPS.

```text
video_id
frame_id
pts_time
dts_time
duration_time
is_key_packet
width
height
decode_order
timebase
frame_id_method
```

Timestamp interval mapping rule:

```text
start_frame = first frame_id where pts_time >= start_sec
end_frame = first frame_id where pts_time >= end_sec
interval = [start_frame, end_frame)
```

Keyframe extraction should prefer decoded `frame_id`. Timestamp seeking is allowed only when exact decoded-frame extraction is unavailable or when validation marks the output as estimated/degraded.

Artifact policy:

```text
frame_timeline.parquet is a staging/debug artifact for accurate timestamp-to-frame mapping.
It may be generated per video, merged globally, sampled, or omitted from compact release if too large.
If omitted from compact release, key tables must still persist enough mapping fields such as frame_id, timestamp_sec, pts_time, frame_id_method, fps_detected, and is_vfr.
```

Mục tiêu:

```text
- biết row nào sinh từ artifact nào;
- biết model/config nào tạo ra output;
- truy ngược lỗi theo worker hoặc batch;
- so sánh được hai lần rerun.
```

---

# 20. Notebook as thin orchestration layer

Notebook được dùng để giúp team chạy trên Kaggle / Colab, nhưng business logic không được nằm chính trong notebook.

Rule bắt buộc:

```text
Business logic must live in src/system1/.
Notebooks are thin orchestration templates only.
```

Repo layout khuyến nghị:

```text
hcm-ai-system1/
├── src/
│   └── system1/
│       ├── ingest/
│       ├── asr/
│       ├── shots/
│       ├── scenes/
│       ├── keyframes/
│       ├── features/
│       ├── text/
│       ├── artifacts/
│       ├── merge/
│       ├── indexes/
│       ├── validation/
│       └── release/
│
├── notebooks/
│   ├── 00_master_ingestion_and_assignment.ipynb
│   ├── 01_worker_structure_pipeline.ipynb
│   ├── 02_worker_feature_enrichment.ipynb
│   └── 03_merge_validate_index_release.ipynb
│
└── scripts/
    ├── system1_ingest.py
    ├── system1_process_batch.py
    ├── system1_feature_batch.py
    ├── system1_merge.py
    ├── system1_validate.py
    └── system1_build_release.py
```

CLI tối thiểu:

```bash
system1 ingest
system1 process-batch --batch-id batch_000
system1 feature-batch --batch-id batch_000
system1 merge
system1 validate
system1 build-index
system1 release
```

---

# 21. Schema evolution policy

Dataset release là contract giữa System 1 và System 2, nên phải version schema rõ ràng.

`dataset_manifest.json` phải có:

```json
{
  "schema_version": "1.0.0",
  "minimum_system2_version": "1.0.0"
}
```

Policy:

```text
Add column = minor version, backward compatible.
Rename/remove column = major version, breaking change.
Change ID format = major version, breaking change.
Change frame_id convention = major version, breaking change.
```

System 2 chỉ được load dataset khi `schema_version` tương thích với `minimum_system2_version`.

## Competition Rules Adapter

Vì luật cuộc thi có thể thay đổi theo năm hoặc được công bố muộn, các phần sau phải configurable thay vì hardcode trong code nghiệp vụ:

```text
submission_format_config.yaml
frame_id_policy.yaml
query_type_config.yaml
scoring_tolerance_config.yaml
export_template_config.yaml
```

Nguyên tắc:

- System 1 persist dữ liệu giàu và stable.
- Adapter layer quyết định cách export/submit theo luật hiện hành.
- Không nhúng logic competition-specific dễ thay đổi vào core artifact schemas nếu chưa có quy định chính thức.

---

# 22. Phase overview

```text
Phase 0: Setup conventions, schemas, configs
Phase 1: Master ingestion & dataset manifest
Phase 2: Batch assignment
Phase 3: Worker structure pipeline
Phase 4: Worker feature enrichment
Phase 5: Artifact packaging
Phase 6: Merge structural + feature artifacts
Phase 7: Build global text_documents
Phase 8: Build runtime DB + FTS5 + FAISS + vector_map
Phase 9: Validate + release package for System 2
Phase 10: Smoke test

Cross-cutting contracts:
- canonical IDs
- reproducibility
- checksums
- failure policy
- quality gates
- schema evolution
```

---

# 23. Notebook templates

## Recommended compact version: 4 notebooks

```text
00_master_ingestion_and_assignment.ipynb

01_worker_structure_pipeline.ipynb
- audio extraction
- ASR
- shot detection
- transcript-shot alignment
- scene construction
- keyframe selection
- thumbnail generation
- structure artifact packaging

02_worker_feature_enrichment.ipynb
- visual embeddings
- OCR
- object detection
- image captions
- shot captions
- enriched scene summaries
- text_sources
- feature artifact packaging

03_merge_validate_index_release.ipynb
- artifact scan
- artifact validation
- table merge
- global text_documents build
- DuckDB build
- SQLite build
- SQLite FTS5 build
- FAISS build
- release package
- smoke test
```

## Expanded version: 7 notebooks

Nếu team muốn tách nhỏ để dễ debug:

```text
00_master_ingestion_and_assignment.ipynb
01_worker_audio_asr.ipynb
02_worker_shot_detection.ipynb
03_worker_scene_construction.ipynb
04_worker_keyframe_thumbnail.ipynb
05_worker_feature_enrichment.ipynb
06_merge_validate_index_release.ipynb
```

Khuyến nghị cho team hiện tại: dùng **4 notebook**, bên trong chia section rõ ràng.

---

# 24. Phase 0 — Setup conventions, schemas, configs

## Mục tiêu

Chốt chuẩn trước khi team chạy preprocessing phân tán.

## Folder repo

```text
hcm-ai-system1/
├── configs/
│   ├── dataset.yaml
│   ├── frame.yaml
│   ├── media.yaml
│   ├── preprocessing.yaml
│   ├── models.yaml
│   ├── artifact.yaml
│   └── release.yaml
│
├── schemas/
│   ├── videos.schema.yaml
│   ├── asr_segments.schema.yaml
│   ├── scenes.schema.yaml
│   ├── shots.schema.yaml
│   ├── keyframes.schema.yaml
│   ├── ocr.schema.yaml
│   ├── objects.schema.yaml
│   ├── image_captions.schema.yaml
│   ├── shot_captions.schema.yaml
│   ├── scene_summaries.schema.yaml
│   ├── feature_availability.schema.yaml
│   ├── vector_map.schema.yaml
│   ├── media_store_manifest.schema.yaml
│   ├── frame_timeline.schema.yaml
│   ├── validation_report.schema.yaml
│   ├── text_sources.schema.yaml
│   └── text_documents.schema.yaml
│
├── notebooks/
├── scripts/
├── docs/
└── README.md
```

## Configs

### `frame.yaml`

```yaml
fps_expected_default: 25
frame_id_policy: "decoded_frame_index_primary"
fallback_frame_id_formula: "floor(timestamp_sec * fps_detected)"
frame_id_method_allowed:
  - decoded_frame_index
  - timestamp_fps_fallback
interval_convention: "[start_frame, end_frame)"
```

### `media.yaml`

```yaml
keyframe:
  format: jpg
  quality: 90
  long_side: 960

thumbnail:
  format: webp
  quality: 75
  width: 256

naming:
  pattern: "{video_id}_f{frame_id:07d}"
```

### `artifact.yaml`

```yaml
table_format: parquet
debug_log_format: jsonl
embedding_format: npy_float16
transport_package: zip
per_video_atomic_artifact: true
```

### `release.yaml`

```yaml
release_name_pattern: "competition_dataset_v{version}"
include_staging_duckdb: true
include_app_sqlite: true
include_text_fts: true
include_faiss: true
```

---

# 25. Phase 1 — Master ingestion & dataset manifest

## Notebook

```text
00_master_ingestion_and_assignment.ipynb
```

## Input

```text
raw_videos/
metadata/
```

## Steps

```text
1. Scan raw_videos.
2. Scan metadata JSON.
3. Extract video_id from filenames.
4. Match video_id between video and metadata.
5. Read metadata JSON.
6. Run ffprobe for duration, FPS, resolution, codec.
7. Normalize metadata fields.
8. Create videos.parquet.
9. Create media_store_manifest.parquet.
10. Create master_manifest.parquet.
11. Create dataset_report.json.
12. Create ingestion_errors.jsonl.
```

## Output

```text
01_manifests/
├── videos.parquet
├── media_store_manifest.parquet
├── master_manifest.parquet
├── dataset_report.json
└── ingestion_errors.jsonl
```

## `media_store_manifest.parquet` schema

This is staging/debug storage metadata. System 2 resolves runtime media through `video_ref` and logical media refs, not through absolute paths.

```text
video_id
media_ref
video_ref
original_video_path
metadata_path
storage_backend
relative_path
checksum
size_bytes
created_at
```

## `videos.parquet` schema

At Phase 1, các count liên quan scene/shot/keyframe **chưa có final value**.

```text
video_id
video_filename
video_ref
title
description
keywords
author
channel_id
channel_url
watch_url
thumbnail_url
publish_date
duration_sec
frame_count
frame_count_estimated
frame_count_method
fps_detected
fps_source
is_vfr
frame_id_method
duration_source
fps_expected_default
width
height
codec
scene_count              # null/0 at Phase 1, update after merge
shot_count               # null/0 at Phase 1, update after merge
keyframe_count           # null/0 at Phase 1, update after merge
raw_metadata_json
```

## Count convention

```text
frame_count = decoded_frame_count if available
frame_count_estimated = floor(duration_sec * fps_detected)
frame_count_method = decoded | ffprobe_nb_frames | duration_x_fps_estimate
scene_count = final number of scenes after scene construction
shot_count = final number of shots after shot detection
keyframe_count = final number of keyframes after keyframe selection
```

Ở Phase 1:

```text
scene_count = null hoặc 0
shot_count = null hoặc 0
keyframe_count = null hoặc 0
```

Ở Phase 7/10 sau merge:

```text
update final scene_count, shot_count, keyframe_count
```

---

# 26. Phase 2 — Batch assignment

## Mục tiêu

Chia video cho nhiều worker Kaggle/Colab.

## Unit xử lý

```text
video_id
```

Không chia theo keyframe. Không chia một video cho nhiều người nếu không cần.

## Batch strategy

```text
Nếu có duration:
  chia batch cân bằng tổng duration.

Nếu không có duration:
  chia đều số lượng video.
```

## Output

```text
01_manifests/
├── batch_manifest.csv
├── batch_000.txt
├── batch_001.txt
├── batch_002.txt
└── ...
```

## `batch_manifest.csv`

```text
batch_id
video_id
duration_sec
assigned_to
status
structure_artifact_path
feature_artifact_path
error_note
```

## Status values

```text
pending
processing
structure_done
feature_done
validated
failed
needs_retry
```

---

# 27. Phase 3 — Worker structure pipeline

## Notebook

```text
01_worker_structure_pipeline.ipynb
```

## Ai chạy?

Nhiều thành viên trong team.

## Chạy ở đâu?

```text
Kaggle / Colab
```

## Input

```text
batch_XXX.txt
videos.parquet
media_store_manifest.parquet
raw_videos/
metadata/
```

## Output per video

```text
L21_V001_structure.zip
```

---

## Step A — Audio extraction

Input:

```text
raw video .mp4
```

Process:

```text
ffmpeg extract audio
```

Output:

```text
audio/L21_V001.wav
```

Audio có thể là file tạm, không nhất thiết giữ trong final release.

---

## Step B — ASR

Input:

```text
audio/L21_V001.wav
```

Process:

```text
Whisper / Vietnamese ASR model
```

Output:

```text
asr_segments.parquet
asr_raw.json
```

Schema:

```text
asr_id
video_id
start_sec
end_sec
start_frame
end_frame
text
language
confidence
model_name
```

Mapping:

```text
start_frame = derived from decoded frame index when available
end_frame = derived from decoded frame index when available
fallback = floor/ceil(timestamp_sec * fps_detected) only for CFR or when decoded frame index is unavailable
```

---

## Step C — Shot detection

Input:

```text
raw video
```

MVP method:

```text
PySceneDetect
```

Advanced methods:

```text
OpenCV histogram difference
CLIP similarity difference
TransNetV2
```

Output:

```text
shots.parquet
```

Schema:

```text
shot_id
video_id
shot_index
start_sec
end_sec
start_frame
end_frame
duration_sec
frame_count
keyframe_count        # null/0 initially, update after keyframe selection
detection_method
confidence
```

ID convention:

```text
shot_id = "{video_id}_SH{shot_index:05d}"
```

Example:

```text
L21_V001_SH00001
```

Derived:

```text
frame_count = end_frame - start_frame
```

Fallback rule:

```text
if shot detection fails:
  create one fallback shot covering [0, frame_count)
  detection_method = "fallback_full_video"
  confidence = 0
  status = degraded
```

---

## Step D — Align ASR to shots

Input:

```text
shots.parquet
asr_segments.parquet
```

Output:

```text
shot_transcript_links.parquet
```

Schema:

```text
shot_id
asr_id
video_id
overlap_start_sec
overlap_end_sec
overlap_ratio
text
```

---

## Step E — Scene construction

Input:

```text
shots.parquet
asr_segments.parquet
shot_transcript_links.parquet
metadata_normalized.json
```

Goal:

```text
Group consecutive shots into semantic scenes.
```

Signals:

```text
ASR transcript topic similarity
metadata title / description / keywords
shot continuity
keyword shifts
LLM optional
```

Important rule:

```text
Scene boundary must snap to shot boundary.
```

Output:

```text
scenes.parquet
scene_transcript_links.parquet
scene_summaries_initial.parquet
```

`scenes.parquet` schema:

```text
scene_id
video_id
scene_index
start_sec
end_sec
start_frame
end_frame
duration_sec
frame_count
shot_count
keyframe_count        # null/0 initially, update after keyframe selection
scene_type
grouping_method
confidence
```

ID convention:

```text
scene_id = "{video_id}_SC{scene_index:05d}"
```

Example:

```text
L21_V001_SC00001
```

`scene_summaries_initial.parquet` schema:

```text
scene_id
video_id
summary_vi
summary_en
keywords
evidence_sources
model_name
confidence
```

Initial scene summary is based mainly on:

```text
ASR
metadata
shot transcript overlap
```

---

## Step F — Keyframe selection

Input:

```text
raw video
shots.parquet
optional scenes.parquet only for scene_id assignment/remap
```

MVP stable mode:

```text
keyframes depend on shots + raw video + keyframe config.
scene_id is assigned/remapped after extraction.
Changing scene heuristic does not rerun keyframes/OCR/embeddings in MVP stable mode.
```

Rule:

```text
Shot <= 4s:
  1 primary keyframe at shot middle.

4s < shot <= 12s:
  2 keyframes.

shot > 12s:
  1 keyframe every 2–3 seconds or motion peak.

traffic/football-like shot detected by visual/motion heuristic:
  increase density.
```

Output:

```text
keyframes/
thumbnails/
keyframes.parquet
```

`keyframes.parquet` schema:

```text
keyframe_id
video_id
scene_id
shot_id
keyframe_index
frame_id
timestamp_sec
keyframe_ref
thumbnail_ref
is_primary
selection_reason
width
height
thumbnail_width
thumbnail_height
```

ID convention:

```text
keyframe_id = "{video_id}:{frame_id}"
```

---

## Step G — Update per-video counts

After keyframe selection, update per-video/per-scene/per-shot count fields inside structure artifact:

```text
videos scene_count / shot_count / keyframe_count
scenes shot_count / keyframe_count
shots keyframe_count
```

At per-video artifact level, these counts can be included in:

```text
manifest.json
```

Final global count will be recomputed again during merge.

---

## Step H — Structure manifest

Each structure artifact must include:

```text
manifest.json
```

Example:

```json
{
  "video_id": "L21_V001",
  "fps_expected_default": 25,
  "frame_id_policy": "decoded_frame_index_primary",
  "fallback_frame_id_formula": "floor(timestamp_sec * fps_detected)",
  "frame_id_method_allowed": [
    "decoded_frame_index",
    "timestamp_fps_fallback"
  ],
  "duration_sec": 1262,
  "frame_count": 31550,
  "scene_count": 28,
  "shot_count": 145,
  "keyframe_count": 390,
  "keyframe_format": "jpg",
  "thumbnail_format": "webp",
  "has_asr": true,
  "has_shots": true,
  "has_scenes": true,
  "status": "complete",
  "created_by": "worker_03",
  "batch_id": "batch_002"
}
```

---

# 28. Phase 4 — Worker feature enrichment

## Notebook

```text
02_worker_feature_enrichment.ipynb
```

## Input

```text
L21_V001_structure.zip
```

## Output

```text
L21_V001_features.zip
```

---

## Step A — Visual embeddings

Input:

```text
keyframes/*.jpg
```

Models:

```text
CLIP
SigLIP
EVA-CLIP
```

Output:

```text
visual_embeddings.npy
embeddings_meta.parquet
```

`embeddings_meta.parquet` schema:

```text
embedding_id
keyframe_id
video_id
scene_id
shot_id
frame_id
timestamp_sec
model_name
embedding_dim
dtype
vector_offset
```

Recommended:

```text
float16 .npy
```

---

## Step B — OCR

Input:

```text
keyframes/*.jpg
```

Models:

```text
PaddleOCR
VietOCR
EasyOCR
```

Output:

```text
ocr.parquet
```

Schema:

```text
ocr_id
keyframe_id
video_id
scene_id
shot_id
frame_id
text
bbox
confidence
language
model_name
```

---

## Step C — Object detection

Input:

```text
keyframes/*.jpg
```

Models:

```text
YOLO
GroundingDINO
Detectron
```

Output:

```text
objects.parquet
```

Schema:

```text
object_id
keyframe_id
video_id
scene_id
shot_id
frame_id
label
bbox
confidence
model_name
```

---

## Step D — Image captioning

Input:

```text
keyframes/*.jpg
```

Output:

```text
image_captions.parquet
```

Schema:

```text
keyframe_id
video_id
scene_id
shot_id
frame_id
caption_vi
caption_en
model_name
confidence
```

---

## Step E — Shot captioning

Shot caption is a visual summary of a shot.

It is not ASR transcript overlap.

Example:

```text
Transcript:
"Vụ tai nạn xảy ra vào sáng nay..."

Shot caption:
"Nhiều xe máy và ô tô đang ùn tắc tại một giao lộ đông đúc."
```

Output:

```text
shot_captions.parquet
```

Schema:

```text
shot_id
video_id
scene_id
summary_caption_vi
summary_caption_en
representative_keyframe_ids
model_name
confidence
```

---

## Step F — Enriched scene summaries

After OCR/object/caption are available, create enriched scene summaries.

Output:

```text
scene_summaries_enriched.parquet
```

Schema:

```text
scene_id
video_id
summary_vi
summary_en
keywords
evidence_sources
model_name
confidence
```

Enriched scene summary may use:

```text
ASR
OCR
objects
image captions
shot captions
metadata

```

---

## Step G — Text sources

Per-video feature artifact may include:

```text
text_sources.parquet
```

This is not the final global FTS table.

Schema:

```text
source_id
video_id
scene_id
shot_id
keyframe_id
level
entity_id
source_type
raw_text
normalized_text
normalized_no_diacritics
language
weight
source_priority
token_count
dedup_key
created_at
pipeline_run_id
```

Source types:

```text
video_title
video_description
video_keywords
asr
scene_summary_initial
scene_summary_enriched
scene_keywords
shot_caption
image_caption
ocr
object_labels
```

---

## Feature manifest

Example:

```json
{
  "video_id": "L21_V001",
  "embedding_model": "clip-vit-base-patch32",
  "embedding_dim": 512,
  "embedding_dtype": "float16",
  "embedding_count": 390,
  "has_ocr": true,
  "has_objects": true,
  "has_image_captions": true,
  "has_shot_captions": true,
  "has_text_sources": true,
  "status": "complete"
}
```

---

# 29. Phase 5 — Artifact packaging

## Structure artifact package

```text
L21_V001_structure.zip
```

Contains:

```text
L21_V001/
├── metadata_normalized.json
├── asr_segments.parquet
├── shots.parquet
├── scenes.parquet
├── keyframes.parquet
├── shot_transcript_links.parquet
├── scene_transcript_links.parquet
├── scene_summaries_initial.parquet
├── keyframes/
├── thumbnails/
├── manifest.json
└── errors.jsonl
```

## Feature artifact package

```text
L21_V001_features.zip
```

Contains:

```text
L21_V001/
├── visual_embeddings.npy
├── embeddings_meta.parquet
├── ocr.parquet
├── objects.parquet
├── image_captions.parquet
├── shot_captions.parquet
├── scene_summaries_enriched.parquet
├── text_sources.parquet
├── feature_manifest.json
└── errors.jsonl
```

---

# 30. Notebook 03 — Merge, text build, index build, validation, and release

## Notebook

```text
03_merge_validate_index_release.ipynb
```

## Input

```text
AIC26_release/canonical_release_vXXX/phase01_structure/artifacts/**/*.zip
AIC26_release/canonical_release_vXXX/phase02_features/artifacts/**/*.zip
```

## Steps

Phase này không nên là một script nguyên khối. Triển khai nên tách thành các sub-steps có thể chạy và test độc lập:

```text
6A. merge_structural_artifacts
6B. merge_feature_artifacts
6C. build_feature_availability
6D. build_runtime_db
6E. build_text_index
6F. build_vector_index
6G. run_release_validation
```

Detailed logical steps:

```text
1. Scan all structure.zip files.
2. Scan all features.zip files.
3. Extract artifacts into staging.
4. Validate manifest files.
5. Validate parquet schema.
6. Validate hierarchy.
7. Validate media paths.
8. Validate embedding count.
9. Merge structural tables.
10. Merge feature tables.
11. Build feature_availability.parquet.
12. Recompute final count fields.
13. Build artifact_manifest.parquet.
14. Build video_processing_status.parquet.
15. Build staging.duckdb.
16. Build global text_documents.parquet.
17. Build app.sqlite including text_documents and vector_map runtime table.
18. Build FTS5-backed text search contract inside app.sqlite.
19. Build visual.faiss.
20. Export vector_map.parquet as debug/mirror artifact.
21. Build dataset_manifest.json.
22. Build validation_report.json.
```

---

## Required validations

Validation không nên chỉ là một pass/fail duy nhất. Release report phải tách capability states:

```text
core_runtime: pass | fail
visual_search: pass | degraded | fail
text_search: pass | degraded | fail
inspection_context: pass | degraded | fail
enrichment_overall: pass | degraded | fail
release_usable: true | false
```

Ý nghĩa:

- `core_runtime=pass` mới cho phép System 2 chạy ổn định.
- `inspection_context` phản ánh chất lượng `shots`, `scenes`, nearby keyframes, captions/summaries liên quan.
- `enrichment_overall` phản ánh độ giàu dữ liệu, không phải runtime sống/chết.

`inspection_context` scoring:

```text
pass:
  - >= 95% processed videos have shot rows.
  - >= 90% processed videos have scene rows or deterministic scene fallback rows.
  - >= 95% indexed keyframes resolve to video_id and video_ref/logical media refs.
  - >= 90% indexed keyframes resolve to shot_id.
  - >= 80% indexed keyframes resolve to scene_id.

degraded:
  - core_runtime is pass.
  - shot/scene coverage exists but is below pass thresholds.
  - System 2 can still inspect keyframe/video context with reduced shot/scene UI.

fail:
  - shot/scene tables are corrupt, references are inconsistent, or validation cannot determine safe fallback behavior.
```

Thresholds are initial defaults. They may be tuned after real dataset profiling, but changes must be recorded in release notes.

Hierarchy:

```text
Each shot belongs to exactly one video.
Each scene belongs to exactly one video.
Each keyframe belongs to exactly one video.
If a shot has `scene_id`, that `scene_id` exists.
If a keyframe has `shot_id`, that `shot_id` exists.
If a keyframe has `scene_id`, that `scene_id` exists.
If `inspection_context=pass`, then every shot maps cleanly to one scene and every keyframe maps cleanly into shot/scene context.
```

Frame:

```text
frame_id is integer.
start_frame < end_frame.
frame_count = end_frame - start_frame.
All boundaries use [start_frame, end_frame).
```

Media:

```text
Every `keyframe_ref` resolves successfully.
Every `thumbnail_ref` resolves successfully.
Keyframe extension = .jpg.
Thumbnail extension = .webp.
```

Embeddings:

```text
embedding_count == embeddings_meta row count.
embedding vector_offset is unique.
Every embedding_meta.keyframe_id exists.
FAISS ntotal == vector_map row count.
```

Counts:

```text
videos.scene_count == count(scenes where video_id)
videos.shot_count == count(shots where video_id)
videos.keyframe_count == count(keyframes where video_id)
scenes.shot_count == count(shots where scene_id)
scenes.keyframe_count == count(keyframes where scene_id)
shots.keyframe_count == count(keyframes where shot_id)
videos.frame_count == decoded_frame_count when frame_count_method = decoded.
videos.frame_count_estimated ~= floor(duration_sec * fps_detected).
If only estimated count exists, validation marks frame_count confidence as estimated/degraded.
If scenes exist, scenes.frame_count == end_frame - start_frame.
If shots exist, shots.frame_count == end_frame - start_frame.
```

Text:

```text
text_sources exist for processed videos.
text_documents is not empty.
FTS index can return results.
```

---

# 31. Detail — Global text document construction

## Why this phase exists

System 2 should not need to search separate tables one by one.

System 1 should produce a unified text table:

```text
text_documents.parquet
```

This is the global text search contract.

## Input

```text
videos.parquet
asr_segments.parquet
scenes.parquet
shots.parquet
scene_summaries_initial.parquet
scene_summaries_enriched.parquet
shot_captions.parquet
image_captions.parquet
ocr.parquet
objects.parquet
text_sources.parquet
feature_availability.parquet
```

## Output

```text
tables/text_documents.parquet
```

## Schema

```text
doc_id
level
entity_id
video_id
scene_id
shot_id
keyframe_id
source_type
raw_text
normalized_text
normalized_no_diacritics
language
weight
source_priority
token_count
dedup_key
created_at
pipeline_run_id
```

## Level values

```text
video
scene
shot
keyframe
asr_segment
ocr
object
```

## Source types

```text
video_title
video_description
video_keywords
asr
scene_summary_initial
scene_summary_enriched
scene_keywords
shot_caption
image_caption
ocr
object_labels
```

## Usage by System 2

System 2 can search:

```text
text_documents
→ retrieve entity_id + level
→ map to video/scene/shot/keyframe
→ display candidate keyframe and context
```

Example:

```text
Query: "kẹt xe giao lộ đông xe máy"

Matches:
- image caption
- scene summary
- OCR if any
- ASR transcript
```

---

# 32. Detail — Runtime DB and index building

## DuckDB staging

```text
db/staging.duckdb
```

Used for:

```text
merge
analytics
validation
debugging
batch queries
```

## Runtime SQLite

```text
db/app.sqlite
```

Tables:

```text
videos
scenes
shots
keyframes
asr_segments
shot_transcript_links
scene_transcript_links
ocr
objects
image_captions
shot_captions
scene_summaries_initial
scene_summaries_enriched
embeddings_meta
text_documents
vector_map
feature_availability
release_capabilities
```

Minimum logical keys and SQLite indexes:

```sql
CREATE UNIQUE INDEX pk_videos ON videos(video_id);
CREATE UNIQUE INDEX pk_scenes ON scenes(scene_id);
CREATE UNIQUE INDEX pk_shots ON shots(shot_id);
CREATE UNIQUE INDEX pk_keyframes ON keyframes(keyframe_id);
CREATE UNIQUE INDEX pk_embeddings_meta ON embeddings_meta(embedding_id);
CREATE UNIQUE INDEX uq_vector_map_index_vector ON vector_map(index_name, vector_id);

CREATE INDEX idx_keyframes_video_frame ON keyframes(video_id, frame_id);
CREATE INDEX idx_keyframes_shot ON keyframes(shot_id);
CREATE INDEX idx_keyframes_scene ON keyframes(scene_id);
CREATE INDEX idx_shots_video_range ON shots(video_id, start_frame, end_frame);
CREATE INDEX idx_scenes_video_range ON scenes(video_id, start_frame, end_frame);
CREATE INDEX idx_vector_map_keyframe ON vector_map(keyframe_id);
CREATE INDEX idx_vector_map_vector ON vector_map(index_name, vector_id);
CREATE INDEX idx_text_documents_entity ON text_documents(level, entity_id);
```

## SQLite FTS5

```text
db/app.sqlite
```

MVP rule:

- FTS5 tables live inside `app.sqlite`.
- System 2 must not require a separate `text_fts.sqlite` file.
- If future scale requires a separate FTS DB, that must be a schema/architecture decision with migration notes.

Index from:

```text
text_documents.parquet
```

FTS columns:

```text
doc_id
level
entity_id
video_id
scene_id
shot_id
keyframe_id
source_type
normalized_text
normalized_no_diacritics
```

## FAISS

```text
indexes/visual.faiss
```

Input:

```text
visual_embeddings.npy
```

Index metadata in `index_version.json`:

```json
{
  "embedding_model": "clip-vit-base-patch32",
  "embedding_dim": 512,
  "stored_dtype": "float16",
  "faiss_build_dtype": "float32",
  "metric": "inner_product",
  "vectors_l2_normalized": true,
  "faiss_index_type": "IndexFlatIP"
}
```

Validation:

```text
embedding_dim is consistent.
No embedding vector contains NaN.
No embedding vector has zero norm.
FAISS ntotal == vector_map row count.
embedding_id model slug matches index metadata.
```

Mapping:

```text
indexes/vector_map.parquet
```

`vector_map` là contract bắt buộc, nhưng runtime source of truth nên nằm trong `app.sqlite`.

Quy ước:

- `app.sqlite.vector_map` là mapping runtime chính.
- `indexes/vector_map.parquet` là debug/export mirror artifact.
- Nếu hai nơi không khớp, release validation phải fail.

Schema:

```text
index_name
index_version
embedding_model
vector_id
embedding_id
keyframe_id
video_id
scene_id
shot_id
frame_id
timestamp_sec
thumbnail_ref
keyframe_ref
```

System 2 flow:

```text
FAISS vector_id
→ vector_map
→ keyframe_id
→ shot_id
→ scene_id
→ video_id
```

---

# 33. Phase 9 — Release package

## Output

```text
competition_dataset_v001/
```

Structure:

```text
competition_dataset_v001/
├── db/
│   ├── app.sqlite
│   └── staging.duckdb
│
├── indexes/
│   ├── visual.faiss
│   ├── vector_map.parquet
│   └── index_version.json
│
├── media/
│   ├── keyframes/
│   ├── thumbnails/
│   └── dense_frame_cache/
│
├── tables/
│   ├── videos.parquet
│   ├── asr_segments.parquet
│   ├── scenes.parquet
│   ├── shots.parquet
│   ├── frame_timeline.parquet
│   ├── keyframes.parquet
│   ├── shot_transcript_links.parquet
│   ├── scene_transcript_links.parquet
│   ├── embeddings_meta.parquet
│   ├── ocr.parquet
│   ├── objects.parquet
│   ├── image_captions.parquet
│   ├── shot_captions.parquet
│   ├── scene_summaries_initial.parquet
│   ├── scene_summaries_enriched.parquet
│   ├── text_sources.parquet
│   ├── feature_availability.parquet
│   └── text_documents.parquet
│
├── manifests/
│   ├── dataset_manifest.json
│   ├── artifact_manifest.parquet
│   ├── video_processing_status.parquet
│   ├── quality_report.parquet
│   ├── validation_report.json
│   └── validation_errors.jsonl
│
└── raw_mapping/
    └── media_store_manifest.parquet
```

## `dataset_manifest.json`

```json
{
  "dataset_id": "aic2026_v001",
  "pipeline_run_id": "run_2026_07_01_001",
  "fps_expected_default": 25,
  "frame_id_policy": "decoded_frame_index_primary",
  "fallback_frame_id_formula": "floor(timestamp_sec * fps_detected)",
  "frame_id_method_allowed": [
    "decoded_frame_index",
    "timestamp_fps_fallback"
  ],
  "schema_version": "1.0.0",
  "minimum_system2_version": "1.0.0",
  "video_count": 1000,
  "scene_count": 25000,
  "shot_count": 140000,
  "keyframe_count": 420000,
  "frame_count_total": 31500000,
  "has_asr": true,
  "has_ocr": true,
  "has_objects": true,
  "has_image_captions": true,
  "has_shot_captions": true,
  "has_scene_summaries": true,
  "has_visual_index": true,
  "has_text_fts": true,
  "created_at": "2026-xx-xx",
  "system1_version": "1.1.0"
}
```

## `feature_availability.parquet`

Mục tiêu của bảng này là giúp System 2 biết artifact nào có sẵn ở mức video/scene/shot/keyframe mà không cần suy luận từ nhiều bảng khác nhau.

Schema gợi ý:

```text
entity_level
entity_id
video_id
scene_id
shot_id
keyframe_id
has_asr
has_ocr
has_objects
has_image_caption
has_shot_caption
has_scene_summary
inspection_ready
text_search_ready
visual_search_ready
status
```

Field semantics:

| Field | Meaning |
| --- | --- |
| `entity_level` | One of `video`, `scene`, `shot`, `keyframe`. |
| `entity_id` | ID at the declared `entity_level`. |
| `video_id` | Always populated for runtime resolution. |
| `scene_id` | Populated when scene context exists; nullable otherwise. |
| `shot_id` | Populated when shot context exists; nullable otherwise. |
| `keyframe_id` | Populated for keyframe-level rows; nullable for higher-level rows. |
| `has_*` | `true` only when the artifact exists and passed schema validation. |
| `inspection_ready` | `true` when the entity can load useful shot/scene/nearby context. |
| `text_search_ready` | `true` when the entity contributes at least one valid `text_documents` row. |
| `visual_search_ready` | `true` when the entity resolves to at least one indexed keyframe/vector. |
| `status` | One of `pass`, `degraded`, `missing`, `failed`. |

Status semantics:

- `pass`: artifact exists, schema is valid, references resolve.
- `degraded`: artifact exists but quality threshold or coverage is below target.
- `missing`: artifact is not produced for this entity, but release can continue.
- `failed`: artifact was expected for this release tier and failed validation.

Nguyên tắc:

- đây là convenience contract cho runtime/UI;
- không thay thế source-of-truth chính ở các bảng nghiệp vụ;
- được build sau khi merge toàn dataset;
- cho phép System 2 render feature blocks có điều kiện một cách đơn giản.

---

# 34. Hugging Face storage contract

System 1 uses two Hugging Face Dataset repos for shared storage:

```text
AIC26_raw
AIC26_release
```

No Team Drive tree is part of the primary shared storage contract. Google
Drive may still be used as an organizer handoff source or operator scratch
area, but durable shared state belongs in Hugging Face.

## `AIC26_raw`

`AIC26_raw` is the canonical raw dataset repo:

```text
AIC26_raw/
└── canonical_raw_v003/
    ├── raw_videos/
    │   ├── L21_V001.mp4
    │   ├── L21_V002.mp4
    │   └── ...
    │
    ├── metadata/
    │   ├── L21_V001.json
    │   ├── L21_V002.json
    │   └── ...
    │
    └── manifests/
        ├── canonical_file_manifest.jsonl
        ├── canonical_import_report.json
        └── canonical_video_inventory.parquet
```

`AIC26_raw` must not contain structure artifacts, feature artifacts, merged
tables, `app.sqlite`, FAISS indexes, or final release packages.

`missing_metadata.json` and `unmatched_metadata.json` are raw-level audit
manifests in `AIC26_raw`. The release repo may carry snapshots of them under
phase00 ingestion reports for a particular release run.

```text
AIC26_raw/canonical_raw_vXXX/manifests/
```

## `AIC26_release`

`AIC26_release` is the processed workspace plus final release repo:

```text
AIC26_release/
└── canonical_release_v003/
    ├── phase00_ingestion/
    │   ├── tables/
    │   │   └── videos.parquet
    │   ├── raw_mapping/
    │   │   └── media_store_manifest.parquet
    │   ├── manifests/
    │   │   ├── batch_manifest.csv
    │   │   ├── batch_000.txt
    │   │   ├── batch_001.txt
    │   │   └── ...
    │   └── reports/
    │       ├── dataset_report.json
    │       ├── ingestion_errors.jsonl
    │       ├── missing_metadata.json
    │       ├── unmatched_metadata.json
    │       ├── drive_shadow_report.json
    │       ├── standardize_archives_report.json
    │       └── standardize_progress.jsonl
    │
    ├── phase01_structure/
    │   ├── artifacts/
    │   │   ├── batch_000/
    │   │   │   ├── L21_V001_structure.zip
    │   │   │   ├── L21_V002_structure.zip
    │   │   │   └── ...
    │   │   └── batch_001/
    │   │       └── ...
    │   └── worker_reports/
    │       ├── batch_000_worker_kaggle_A_01.json
    │       └── ...
    │
    ├── phase02_features/
    │   ├── artifacts/
    │   │   ├── batch_000/
    │   │   │   ├── L21_V001_features.zip
    │   │   │   ├── L21_V002_features.zip
    │   │   │   └── ...
    │   │   └── batch_001/
    │   │       └── ...
    │   └── worker_reports/
    │       ├── batch_000_worker_kaggle_A_01.json
    │       └── ...
    │
    ├── phase03_merged/
    │   ├── tables/
    │   │   ├── videos.parquet
    │   │   ├── keyframes.parquet
    │   │   ├── shots.parquet
    │   │   ├── scenes.parquet
    │   │   ├── text_sources.parquet
    │   │   ├── text_documents.parquet
    │   │   ├── feature_availability.parquet
    │   │   └── ...
    │   ├── raw_mapping/
    │   │   └── media_store_manifest.parquet
    │   ├── manifests/
    │   │   ├── artifact_manifest.parquet
    │   │   ├── video_processing_status.parquet
    │   │   └── merge_report.json
    │   └── db/
    │       └── staging.duckdb
    │
    ├── releases/
    │   ├── competition_dataset_v001/
    │   │   ├── db/
    │   │   │   ├── app.sqlite
    │   │   │   └── staging.duckdb
    │   │   ├── indexes/
    │   │   │   ├── visual.faiss
    │   │   │   ├── vector_map.parquet
    │   │   │   └── index_version.json
    │   │   ├── media/
    │   │   │   ├── keyframes/
    │   │   │   ├── thumbnails/
    │   │   │   └── dense_frame_cache/
    │   │   ├── tables/
    │   │   ├── manifests/
    │   │   └── raw_mapping/
    │   │
    │   └── competition_dataset_v001.zip
    │
    ├── checkpoints/
    │   ├── phase00_ingestion/
    │   ├── phase01_structure/
    │   ├── phase02_features/
    │   └── phase03_release/
    │
    └── logs/
        ├── validation_errors.jsonl
        ├── artifact_validation_errors.jsonl
        └── worker_errors/
```

`phase00_ingestion` is Notebook 00 output and is not the final runtime release.
Only `releases/competition_dataset_vXXX/` is the final app-ready release for
System 2.

Legacy flat layout under:

```text
canonical_release_vXXX/manifests
canonical_release_vXXX/tables
canonical_release_vXXX/raw_mapping
```

is deprecated. A future implementation may read it temporarily for migration,
but all new outputs must use:

```text
canonical_release_vXXX/phase00_ingestion/{manifests,tables,raw_mapping,reports}
```

## Notebook upload/download contract

Notebook 00 uploads canonical raw output to:

```text
AIC26_raw/canonical_raw_vXXX/raw_videos/
AIC26_raw/canonical_raw_vXXX/metadata/
AIC26_raw/canonical_raw_vXXX/manifests/canonical_file_manifest.jsonl
AIC26_raw/canonical_raw_vXXX/manifests/canonical_import_report.json
AIC26_raw/canonical_raw_vXXX/manifests/canonical_video_inventory.parquet
```

Notebook 00 uploads phase00 ingestion and batch-planning outputs to:

```text
AIC26_release/canonical_release_vXXX/phase00_ingestion/tables/videos.parquet
AIC26_release/canonical_release_vXXX/phase00_ingestion/raw_mapping/media_store_manifest.parquet
AIC26_release/canonical_release_vXXX/phase00_ingestion/manifests/batch_manifest.csv
AIC26_release/canonical_release_vXXX/phase00_ingestion/manifests/batch_*.txt
AIC26_release/canonical_release_vXXX/phase00_ingestion/reports/dataset_report.json
AIC26_release/canonical_release_vXXX/phase00_ingestion/reports/ingestion_errors.jsonl
AIC26_release/canonical_release_vXXX/phase00_ingestion/reports/missing_metadata.json
AIC26_release/canonical_release_vXXX/phase00_ingestion/reports/unmatched_metadata.json
AIC26_release/canonical_release_vXXX/phase00_ingestion/reports/drive_shadow_report.json
AIC26_release/canonical_release_vXXX/phase00_ingestion/reports/standardize_archives_report.json
AIC26_release/canonical_release_vXXX/phase00_ingestion/reports/standardize_progress.jsonl
```

`batch_manifest.csv` and `batch_*.txt` do not belong in `AIC26_raw` because
they depend on a pipeline run: `num_batches`, worker strategy, execution
profile, and release version.

Notebook 01 reads:

```text
AIC26_raw/canonical_raw_vXXX/raw_videos/
AIC26_raw/canonical_raw_vXXX/metadata/
AIC26_release/canonical_release_vXXX/phase00_ingestion/tables/videos.parquet
AIC26_release/canonical_release_vXXX/phase00_ingestion/raw_mapping/media_store_manifest.parquet
AIC26_release/canonical_release_vXXX/phase00_ingestion/manifests/batch_XXX.txt
```

Notebook 01 uploads:

```text
AIC26_release/canonical_release_vXXX/phase01_structure/artifacts/{batch_id}/{video_id}_structure.zip
AIC26_release/canonical_release_vXXX/phase01_structure/worker_reports/{batch_id}_{worker_id}.json
```

Notebook 02 reads:

```text
AIC26_release/canonical_release_vXXX/phase01_structure/artifacts/{batch_id}/*_structure.zip
```

Notebook 02 uploads:

```text
AIC26_release/canonical_release_vXXX/phase02_features/artifacts/{batch_id}/{video_id}_features.zip
AIC26_release/canonical_release_vXXX/phase02_features/worker_reports/{batch_id}_{worker_id}.json
```

Notebook 03 reads:

```text
AIC26_release/canonical_release_vXXX/phase01_structure/artifacts/**/*.zip
AIC26_release/canonical_release_vXXX/phase02_features/artifacts/**/*.zip
```

Notebook 03 uploads:

```text
AIC26_release/canonical_release_vXXX/phase03_merged/
AIC26_release/canonical_release_vXXX/releases/competition_dataset_vXXX/
AIC26_release/canonical_release_vXXX/releases/competition_dataset_vXXX.zip
AIC26_release/canonical_release_vXXX/logs/
```

---

# 35. Mapping contract for System 2

System 2 must rely on these mappings.

Runtime design goal:

- initial retrieval thường trả candidate ở mức keyframe hoặc text hit;
- từ candidate đó, System 2 có thể inspect sâu hơn theo shot và scene nếu artifacts có sẵn;
- runtime không được phụ thuộc vào raw absolute path.

## Video → Scene

```text
video_id
scene_id
scene_index
start_frame
end_frame
```

## Scene → Shot

```text
scene_id
shot_id
shot_index
start_frame
end_frame
```

## Shot → Keyframe

```text
shot_id
keyframe_id
frame_id
timestamp_sec
thumbnail_ref
keyframe_ref
```

## Keyframe → Features

```text
keyframe_id
embedding_id
ocr rows
object rows
caption rows

```

## Vector → Keyframe

```text
index_name
index_version
embedding_model
vector_id
keyframe_id
video_id
scene_id
shot_id
frame_id
```

## Text document → Entity

```text
doc_id
level
entity_id
video_id
scene_id
shot_id
keyframe_id
source_type
```

Goal:

```text
candidate
→ keyframe
→ shot
→ scene
→ video
→ transcript / OCR / caption / video_ref/logical media refs
```

---

# 36. System 1 ready checklist

System 1 release is ready only when:

```text
[ ] All videos have normalized metadata.
[ ] All videos have video_ref/logical media ref mapping.
[ ] All videos have ASR or explicit ASR failed status.
[ ] All videos have shot detection output.
[ ] If `inspection_context=pass`, all shots map to scenes.
[ ] If `inspection_context=pass`, keyframes map cleanly to shots and scenes.
[ ] Keyframe .jpg files exist.
[ ] Thumbnail .webp files exist.
[ ] Visual embeddings exist for indexed keyframes.
[ ] embeddings_meta maps every vector to a keyframe.
[ ] OCR/object/caption follow schema.
[ ] feature_availability.parquet exists.
[ ] text_sources.parquet exists.
[ ] global text_documents.parquet exists.
[ ] quality_report.parquet exists.
[ ] app.sqlite is built.
[ ] FTS5-backed text search contract is built.
[ ] visual.faiss is built.
[ ] vector_map.parquet maps vector_id to keyframe_id.
[ ] dataset_manifest.json has final counts.
[ ] validation_report.json has no critical errors.
[ ] smoke test passes.
```

---

# 37. Smoke test

Script:

```text
smoke_test_system1_release.py
```

Test cases:

```text
1. Load app.sqlite.
2. Count videos/scenes/shots/keyframes.
3. Random 100 keyframes: check .jpg and .webp exist.
4. Load FAISS.
5. Search 5 random vectors.
6. Lookup vector_id → keyframe_id.
7. Lookup keyframe_id → shot_id → scene_id → video_id.
8. Search text FTS.
9. Resolve media refs successfully.
10. Check frame_id is integer.
11. Validate count consistency.
12. Validate System 2 can load dataset config.
```

Output:

```text
smoke_test_report.json
```

---

# 38. Handoff to System 2

System 2 should only need:

```yaml
dataset:
  root: "./competition_dataset"
  runtime_db: "./competition_dataset/db/app.sqlite"
  text_fts_db: "./competition_dataset/db/app.sqlite"
  visual_index: "./competition_dataset/indexes/visual.faiss"
  vector_map_table: "app.sqlite.vector_map"
  vector_map_export: "./competition_dataset/indexes/vector_map.parquet"
  thumbnails_root: "./competition_dataset/media/thumbnails"
  keyframes_root: "./competition_dataset/media/keyframes"
  media_store_manifest: "./competition_dataset/raw_mapping/media_store_manifest.parquet"
  fps_expected_default: 25
```

System 2 does not need to know how preprocessing was done.

---

# 39. Final summary

System 1 is:

```text
A distributed multimedia dataset factory.
```

It converts:

```text
raw videos + metadata JSON
```

into:

```text
hierarchical multimedia dataset:
Video → Scene → Shot → Keyframe
```

with:

```text
ASR
OCR
object detections
image captions
shot captions
scene summaries

visual embeddings
text documents
FAISS index
SQLite runtime DB
SQLite FTS5 text index
all mappings
validation reports
```

System 1 ends when it releases:

```text
competition_dataset_vXXX/
```

System 2 begins when it loads that release.
