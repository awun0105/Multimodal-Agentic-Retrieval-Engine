# System 1 Throughput Plan

Tài liệu này mô tả cách vận hành **System 1 preprocessing pipeline** để xử lý dataset video nhanh, ổn định, dễ chia việc cho nhiều teammate, và dễ khôi phục khi một session Kaggle/Colab bị lỗi.

`docs/onboarding/system1_spec.md` là tài liệu mô tả **System 1 phải tạo ra data gì**.
Tài liệu này mô tả **cách chạy System 1 sao cho nhanh và phối hợp tốt**.

---

## 1. Mục tiêu

System 1 cần xử lý một lượng lớn video để tạo ra dataset sẵn sàng cho System 2.

Luồng tổng quát:

```text
raw videos + metadata
→ ingestion
→ batch assignment
→ structure pipeline
→ feature enrichment
→ artifact ZIP
→ merge
→ SQLite / FTS5 / FAISS
→ validation
→ release
```

Mục tiêu của throughput plan:

```text
- chia việc công bằng cho nhiều worker
- tránh worker bị rảnh quá lâu
- tránh xử lý trùng video
- tránh phải chạy lại từ đầu khi lỗi
- tái sử dụng artifact đã có
- giảm thời gian upload/download
- đo được chậm ở đâu để tối ưu tiếp
```

---

## 1.1. Shared storage contract

System 1 shared storage uses exactly two Hugging Face Dataset repos:

```text
AIC26_raw
AIC26_release
```

`AIC26_raw` is the canonical raw dataset repo. It contains standardized
`raw_videos/`, `metadata/`, and raw-level manifests such as
`canonical_file_manifest.jsonl`, `canonical_import_report.json`, and
`canonical_video_inventory.parquet`.

`AIC26_release` is the processed workspace plus final release repo. It contains:

```text
canonical_release_vXXX/
  phase00_ingestion/
  phase01_structure/
  phase02_features/
  phase03_merged/
  releases/
  checkpoints/
  logs/
```

Notebook 00 uploads batch planning and ingestion reports to
`AIC26_release/canonical_release_vXXX/phase00_ingestion/`. This phase is not
the final runtime release. The app-ready System 2 package lives under
`AIC26_release/canonical_release_vXXX/releases/competition_dataset_vXXX/`.

`missing_metadata.json` and `unmatched_metadata.json` are raw-level audit
manifests in `AIC26_raw`. The release repo may also snapshot them under
`AIC26_release/canonical_release_vXXX/phase00_ingestion/reports/` for a
particular run.

Legacy flat paths under
`canonical_release_vXXX/{manifests,tables,raw_mapping}` are deprecated for new
outputs.

## 2. Khái niệm chính

### 2.1. Teammate

`teammate` là người trong team.

Teammate là người mở notebook, chọn batch hoặc worker mode, rồi chạy pipeline.

---

### 2.2. Worker

`worker` là một phiên xử lý đang chạy.

Một worker có thể là:

```text
- một Kaggle Notebook session
- một Colab session
- một máy local
- một server nội bộ
- một GPU job
```

Một teammate có thể chạy một hoặc nhiều worker.

Ví dụ:

```text
Teammate A mở Kaggle notebook → worker_kaggle_A_01
Teammate B mở Colab notebook → worker_colab_B_01
Bạn mở local server → worker_local_01
```

Pipeline không cần biết người thật là ai. Pipeline chỉ cần biết `worker_id`.

---

### 2.3. Batch

`batch` là một phần việc được giao cho worker.

Ví dụ:

```text
batch_000.txt
batch_001.txt
batch_002.txt
```

Mỗi batch chứa danh sách video cần xử lý.

Ví dụ:

```text
batch_001.txt:
L21_V001
L21_V004
L21_V017
L22_V003
```

---

### 2.4. Artifact

`artifact` là kết quả mà worker tạo ra sau khi xử lý video hoặc batch.

Ví dụ:

```text
L21_V001_structure.zip
L21_V001_features.zip
```

Artifact phải có manifest và checksum để merge/release có thể kiểm tra tự động.

---

## 3. Production profile, not execution modes

Production notebooks should run the full end-to-end profile. Operators choose
batch/workers and provider credentials, not bronze/silver/gold execution modes.

Legacy names such as `debug_small_sample`, `bronze_fast`, `silver_balanced`, and
`gold_full` may remain package-internal while tests and older CLIs are being
refactored, but they are not the production notebook contract.

The production profile runs:

```text
Phase00 ingest + batch planning
Phase01 semantic structure
Phase02 feature extraction
Phase03 merge + index + validate + release
```

Each phase owns one responsibility and should not defer core work to a later
phase. In particular, Phase01 owns canonical shot captions and scene summaries;
Phase02 does not add caption/enriched-summary work.

The older mode sections below are retained as historical capacity-planning
notes until the package/CLI is fully refactored. Do not use them as the
production notebook contract.

---

## 4. Mode 1 — debug_small_sample

Dùng để test nhanh pipeline trên vài video nhỏ.

Mục tiêu:

```text
- kiểm tra notebook chạy được không
- kiểm tra config đúng không
- kiểm tra artifact sinh ra đúng schema không
- kiểm tra merge/release skeleton hoạt động không
```

Đặc điểm:

```text
- chạy 1–5 video
- có thể dùng model nhỏ hoặc mock/stub
- ưu tiên debug, không ưu tiên chất lượng
```

Nên dùng khi:

```text
- mới setup repo
- mới sửa pipeline
- mới thêm module mới
- muốn test trước khi chạy nhiều video
```

Output của mode này không nhất thiết dùng cho release chính.

---

## 5. Legacy note — bronze_fast

Legacy planning note only. Production notebooks should not expose this as an
operator mode.

Mục tiêu:

```text
- có video metadata
- có shot/keyframe metadata
- có keyframes
- có thumbnails
- có SigLIP/BEiT3 embeddings
- có hai FAISS indexes
- có SQLite/FTS cơ bản
- có release chạy được
```

This legacy profile could skip or use a lightweight version of:

```text
- ASR
- OCR
- object detection
```

Đặc điểm:

```text
- chạy nhanh
- đủ để test System 2
- đủ để test UI/retrieval core
- chất lượng retrieval chưa tối đa
```

This legacy profile created artifacts such as:

```text
- videos.parquet
- frame_timeline/{video_id}.parquet
- shots.parquet
- scenes.parquet hoặc fallback scene
- keyframes
- thumbnails
- SigLIP/BEiT3 embeddings
- two FAISS indexes/vector_map
- app.sqlite base
```

---

## 6. Legacy note — silver_balanced

Legacy planning note only. The production profile now targets the full release
contract directly.

The older plan reused bronze artifacts if still valid.

It reused:

```text
- video metadata
- frame_timeline/{video_id}.parquet
- shots/scenes
- keyframes
- thumbnails
- SigLIP/BEiT3 embeddings nếu model tương ứng không đổi
- FAISS/vector_map rows của model không đổi
```

It added or upgraded:

```text
- OCR
- ASR
- text_sources
- text_documents
- SQLite FTS5 rebuild
- validation report mới
- release version mới
```

Đặc điểm:

```text
- cân bằng giữa tốc độ và chất lượng
- phù hợp làm release chính ban đầu
- hỗ trợ tốt hơn cho query có chữ trong ảnh, lời thoại, bảng hiệu, địa danh
```

Legacy example:

```text
competition_dataset_v001_bronze
→ add OCR + ASR
→ competition_dataset_v002_silver
```

---

## 7. Legacy note — gold_full

Legacy planning note only. This should not be implemented as a production
notebook mode.

The older plan reused bronze/silver artifacts if inputs/configs were unchanged.

It reused:

```text
- video metadata
- keyframes/thumbnails
- OCR
- ASR
- embeddings
- FAISS/vector_map
- SQLite base tables
```

It added:

```text
- object detection
- richer text_documents
- SQLite FTS5 rebuild nếu text thay đổi
- validation report mới
- release version mới
```

Đặc điểm:

```text
- chạy lâu hơn
- tốn GPU hơn
- chất lượng evidence và retrieval tốt hơn
```

Ví dụ:

```text
competition_dataset_v002_silver
→ add object/caption/enriched summaries
→ competition_dataset_v003_gold
```

---

## 8. Reuse rule

Pipeline phải kiểm tra artifact cũ trước khi chạy lại một bước.

Một artifact được reuse nếu các thông tin sau không đổi:

```text
- input checksum
- model name
- model version
- config hash
- schema version
- artifact checksum
```

Nếu artifact còn hợp lệ:

```text
reuse artifact
```

Nếu artifact không hợp lệ hoặc config/model đổi:

```text
rerun đúng phase bị ảnh hưởng
```

Không rerun toàn bộ pipeline nếu không cần.

---

## 9. Khi nào phải chạy lại phần nào?

### 9.1. Đổi OCR model

Chỉ cần chạy lại:

```text
OCR
→ text_sources
→ text_documents
→ FTS5
→ validation
→ release
```

Không cần chạy lại:

```text
keyframes
thumbnails
ASR
visual embeddings
FAISS
```

---

### 9.2. Đổi ASR model

Chỉ cần chạy lại:

```text
ASR
→ text_sources
→ text_documents
→ FTS5
→ validation
→ release
```

Không cần chạy lại:

```text
keyframes
thumbnails
OCR
visual embeddings
FAISS
```

---

### 9.3. Đổi embedding model

Chỉ cần chạy lại:

```text
affected SigLIP or BEiT3 embeddings
→ affected FAISS index
→ affected vector_map rows
→ validation
→ release
```

Không cần chạy lại:

```text
keyframes
thumbnails
OCR
ASR
```

---

### 9.4. Đổi keyframe extraction config

Đây là thay đổi lớn vì nhiều output downstream phụ thuộc vào keyframe.

Cần chạy lại:

```text
keyframes
→ thumbnails
→ OCR
→ SigLIP + BEiT3 embeddings
→ canonical bilingual shot captions
→ scene grouping + bilingual scene summaries
→ object detection
→ both FAISS indexes/vector_map
→ text_documents
→ validation
→ release
```

---

### 9.5. Chỉ sửa schema merge/release

Nếu artifact gốc không đổi, thường chỉ cần chạy lại:

```text
merge
→ SQLite/FTS5
→ FAISS nếu vector_map/index logic đổi
→ validation
→ release
```

---

## 10. Default MVP strategy

MVP không cần dynamic queue phức tạp ngay.

Chiến lược mặc định:

```text
1. Master notebook scan toàn bộ video.
2. Tính estimated_compute_cost cho từng video.
3. Chia batch cố định nhưng cân bằng theo cost.
4. Mỗi worker nhận một batch.
5. Worker chạy notebook 01 hoặc 02.
6. Worker upload artifact ZIP.
7. Notebook 03 merge/validate/release.
```

Nói ngắn gọn:

```text
MVP = cost-aware static batch assignment
```

Dynamic queue là optional advanced mode, không bắt buộc cho MVP.

---

## 11. Cost-aware static batch assignment

### 11.1. Vấn đề

Không nên chia đều theo số lượng video.

Ví dụ:

```text
Worker 1: 20 video dài
Worker 2: 20 video ngắn
Worker 3: 20 video trung bình
```

Như vậy Worker 2 có thể xong sớm và ngồi chờ, còn Worker 1 chạy rất lâu.

Tổng thời gian bị kéo dài.

---

### 11.2. Cách làm đúng

Master ingestion notebook cần scan metadata của video bằng `ffprobe` hoặc công cụ tương đương.

Mỗi video nên có thông tin:

```text
video_id
video_ref
duration_sec
width
height
fps_detected
frame_count
frame_count_estimated
frame_count_method
is_vfr
has_frame_timeline
frame_timeline_ref
file_size_bytes
has_audio
```

`frame_count` should come from `ffprobe -count_packets` / `nb_read_packets`
when available. Header `nb_frames` is only a fallback, and `duration_sec *
fps_detected` is a last-resort estimate that must set
`frame_count_estimated=true` because it can cause frame ID drift on VFR or
malformed videos.

Sau đó tính:

```text
estimated_compute_cost
```

Đây là điểm ước lượng độ nặng của video.

---

### 11.3. Công thức MVP đơn giản

Công thức ban đầu không cần quá phức tạp.

Ví dụ:

```text
estimated_compute_cost =
  duration_sec
  × resolution_factor
  × fps_factor
  × audio_factor
  × tier_factor
```

Gợi ý:

```text
resolution_factor:
  <= 720p  → 1.0
  1080p    → 1.5
  2K       → 2.0
  4K       → 3.0

fps_factor:
  <= 25 fps → 1.0
  30 fps    → 1.2
  50/60 fps → 1.5

audio_factor:
  has_audio = true  → 1.2
  has_audio = false → 1.0

profile_factor:
  production_full → 1.0
```

Công thức này chỉ là ước lượng. Không cần chính xác tuyệt đối. Mục tiêu là chia batch cân bằng hơn.

`<= 25 fps` ở đây chỉ là **bucket ước lượng chi phí scheduling** để chia batch, không phải FPS runtime hardcoded. Runtime FPS detection, `fps_detected`, `frame_id_method`, và frame mapping vẫn phải theo `docs/onboarding/system1_spec.md`.

---

### 11.4. Output cần có

`videos.parquet` chỉ nên chứa metadata cấp video và cost estimate:

```text
video_id
video_ref
duration_sec
width
height
fps_detected
frame_count
frame_count_estimated
frame_count_method
file_size_bytes
has_audio
estimated_compute_cost
```

Không đưa `image_sha256`, `embedding_model`, hoặc `embedding_model_version` vào `videos.parquet`. `image_sha256` thuộc metadata của keyframe/image artifact. `embedding_model`, `embedding_model_version`, và các field embedding liên quan thuộc `embeddings_meta`, `feature_manifest`, `vector_map` metadata, hoặc metadata cấp feature tương đương.

`batch_manifest.csv` nên có:

```text
batch_id
video_id
estimated_compute_cost
assigned_worker
status
```

Batch files:

```text
batch_000.txt
batch_001.txt
batch_002.txt
```

Mục tiêu:

```text
tổng estimated_compute_cost của các batch gần bằng nhau
```

Không nhất thiết số lượng video mỗi batch phải bằng nhau.

---

### 11.5. Fallback rule

Nếu thiếu metadata, dùng fallback:

```text
1. Nếu có estimated_compute_cost → chia theo estimated_compute_cost
2. Nếu chưa có cost nhưng có duration_sec → chia theo duration_sec
3. Nếu không có duration_sec → chia đều theo số lượng video
```

---

## 12. Worker workflow trong MVP

Mỗi teammate làm theo flow đơn giản:

```text
1. Mở notebook phù hợp.
2. Clone/install repo.
3. Mount hoặc connect storage.
4. Nhập worker_id.
5. Chọn batch_id.
6. Chọn provider credentials/config nếu cần.
7. Bấm Run All.
8. Notebook kiểm tra artifact nào đã có thể reuse.
9. Notebook chỉ chạy phần còn thiếu hoặc phần cần rebuild.
10. Notebook xuất artifact ZIP vào local package layout.
11. Notebook ghi worker report không overwrite.
12. HF phase01/phase02 sync là workflow riêng, không phải hành vi mặc định của local package CLI hiện tại.
```

Ví dụ:

```text
worker_id = worker_kaggle_an_01
batch_id = batch_003
```

Output:

```text
output/competition_dataset_v001/
├── artifacts/
│   ├── structure/
│   │   ├── L21_V001_structure.zip
│   │   └── L21_V004_structure.zip
│   └── features/
│       ├── L21_V001_features.zip
│       └── L21_V004_features.zip
└── manifests/
    └── worker_reports/
        └── structure_batch_003_worker_kaggle_an_01.json
```

---

## 13. Optional dynamic worker queue

Dynamic queue là mode nâng cao. Chỉ nên làm sau khi MVP static batch đã ổn.

### 13.1. Khi nào cần dynamic queue?

Cần dynamic queue nếu:

```text
- nhiều worker chạy song song
- batch cố định vẫn bị lệch nặng/nhẹ
- worker thường xuyên bị crash/disconnect
- muốn worker tự lấy video tiếp theo khi rảnh
```

---

### 13.2. Ý tưởng

Thay vì mỗi worker nhận batch cố định, tất cả worker cùng nhìn vào một queue chung:

```text
work_queue.csv
```

hoặc:

```text
work_queue.parquet
```

Worker nào rảnh thì tự claim video tiếp theo.

Flow:

```text
worker starts
→ read work_queue
→ find pending video
→ create claim lock
→ process video
→ upload artifact
→ mark video complete
→ claim next video
```

---

### 13.3. work_queue fields

`work_queue` nên có:

```text
video_id
video_ref
estimated_compute_cost
status
assigned_worker
claimed_at
lease_until
attempt_count
last_error
structure_done
feature_done
artifact_path
updated_at
```

Status values:

```text
pending
running
structure_done
feature_done
completed
failed_retryable
failed_final
skipped
```

---

### 13.4. Claim lock

Để tránh hai worker cùng xử lý một video, worker phải tạo lock file trước khi chạy.

Ví dụ:

```text
claims/L21_V001.lock
```

Nội dung:

```json
{
  "video_id": "L21_V001",
  "worker_id": "worker_kaggle_an_01",
  "claimed_at": "2026-07-01T09:00:00+07:00",
  "lease_until": "2026-07-01T11:00:00+07:00"
}
```

Nếu lock đã tồn tại và chưa hết hạn, worker khác không được xử lý video đó.

---

### 13.5. Heartbeat

Mỗi worker nên ghi heartbeat để báo rằng nó vẫn còn sống.

Ví dụ:

```text
worker_heartbeat/worker_kaggle_an_01.json
```

Nội dung:

```json
{
  "worker_id": "worker_kaggle_an_01",
  "platform": "kaggle",
  "current_video_id": "L21_V001",
  "current_phase": "feature_enrichment",
  "updated_at": "2026-07-01T09:30:00+07:00"
}
```

Nếu heartbeat quá lâu không cập nhật, worker có thể đã crash.

---

### 13.6. lease_until và retry

`lease_until` là thời điểm claim hết hạn.

Ví dụ:

```text
worker claim video lúc 09:00
lease_until = 11:00
```

Nếu đến sau 11:00 mà video vẫn chưa complete và heartbeat không còn cập nhật, video có thể được đưa về:

```text
failed_retryable
```

hoặc:

```text
pending
```

để worker khác xử lý lại.

---

### 13.7. Lưu ý

Dynamic queue có lợi nhưng phức tạp hơn static batch.

Vì vậy:

```text
MVP không bắt buộc dynamic queue.
Chỉ implement dynamic queue khi static batch không còn đủ nhanh.
```

---

## 14. Model batching policy

Model inference thường là phần tốn thời gian nhất. Không nên chạy từng ảnh một nếu model hỗ trợ batch.

### 14.1. Embedding

Dùng riêng cho SigLIP và BEiT3; mỗi model có batch/config/checkpoint độc lập.

Gợi ý:

```yaml
embedding:
  batch_size: 64-256
  precision: fp16
  num_workers: 2-4
```

Nguyên tắc:

```text
- tăng batch_size đến khi gần đầy GPU memory
- nếu OOM thì giảm batch_size
- luôn ghi model_name, model_version, embedding_dim
```

---

### 14.2. OCR

Gợi ý:

```yaml
ocr:
  batch_size: 16-64
  max_image_side: 1280
```

Nguyên tắc:

```text
- resize ảnh quá lớn trước khi OCR
- giữ mapping về keyframe_id
- lưu OCR confidence nếu có
```

---

### 14.3. Captioning / VLM

Gợi ý:

```yaml
caption:
  batch_size: 4-32
  precision: fp16
  max_image_side: 1024
```

Nguyên tắc:

```text
- canonical shot captioning thuộc Phase01
- chỉ caption representative keyframe của mỗi shot
- output phải có model version
```

---

### 14.4. Object detection

Gợi ý:

```yaml
object_detection:
  batch_size: 8-64
  precision: fp16
  max_image_side: 1280
```

Nguyên tắc:

```text
- chỉ lưu object quan trọng/confidence đủ cao
- không để object output phình quá lớn
```

---

### 14.5. ASR

Gợi ý:

```yaml
asr:
  model_tier: small | medium | large
  chunk_sec: 30
  vad_enabled: true
```

Nguyên tắc:

```text
- ASR thường là bottleneck lớn
- production profile yêu cầu ASR
- model/provider có thể thay đổi qua config nhưng không qua notebook mode selector
```

---

### 14.6. OOM retry policy

Nếu GPU out-of-memory:

```text
1. clear GPU cache nếu framework hỗ trợ
2. giảm batch_size một nửa
3. retry phase hiện tại
4. nếu vẫn lỗi, ghi failed_retryable
5. không làm hỏng toàn bộ batch
```

---

## 15. Cache/reuse policy

Cache giúp tránh chạy lại phần đã có kết quả.

### 15.1. Nguyên tắc cache

Một output có thể reuse nếu input và model không đổi.

Cache key nên dựa trên:

```text
input checksum
model name
model version
config hash
```

Ví dụ:

```text
image_sha256 + embedding_model + embedding_model_version
```

---

### 15.2. Những thứ nên cache

Nên cache:

```text
- frame_timeline/{video_id}.parquet
- extracted keyframes
- thumbnails
- decoded audio
- ASR result
- OCR result
- SigLIP/BEiT3 embeddings
- Gemini shot-caption responses and canonical bilingual rows
- object detections
```

---

### 15.3. Khi nào phải rebuild?

Ví dụ:

```text
đổi OCR model
→ chỉ rebuild OCR + text_sources + text_documents + FTS

đổi embedding model
→ rebuild only that model's embeddings + FAISS index + vector_map rows

đổi keyframe extraction config
→ rebuild keyframes + thumbnails + downstream visual/text features

đổi ASR model
→ rebuild ASR + text_documents + FTS
```

Không nên rerun toàn bộ pipeline nếu chỉ một phần thay đổi.

---

## 16. Artifact ZIP/upload/download policy

Artifact ZIP giúp tránh upload hàng trăm nghìn file nhỏ lên Drive/Kaggle.

### 16.1. Vì sao dùng ZIP?

Không nên upload từng keyframe/thumbnails rời rạc vì:

```text
- rất chậm
- dễ lỗi
- dễ rate limit
- khó retry
- khó kiểm tra đủ file
```

Nên upload theo artifact ZIP:

```text
L21_V001_structure.zip
L21_V001_features.zip
```

---

### 16.2. ZIP size

Gợi ý:

```text
target_zip_size_mb: 256–1024MB
```

Không nên quá nhỏ vì merge sẽ tốn overhead.
Không nên quá lớn vì lỗi upload sẽ phải retry lại nhiều.

---

### 16.3. Compression mode

Với file đã nén như:

```text
.jpg
.webp
.npy
.parquet
```

Không cần nén ZIP quá mạnh.

Gợi ý:

```text
zip_compression = store hoặc fast
```

Mục tiêu là đóng gói nhanh, không phải giảm dung lượng tối đa.

---

### 16.4. Upload retry

Khi upload artifact:

```text
1. upload ZIP
2. upload manifest/checksum
3. verify file size
4. verify checksum nếu có thể
5. nếu fail thì retry
```

Không đánh dấu `completed` nếu artifact chưa upload/validate xong.

---

### 16.5. Artifact validation

Mỗi artifact phải có:

```text
artifact_manifest.json
checksums.json
errors.jsonl nếu có lỗi
```

Notebook 03 chỉ merge artifact hợp lệ.

Nếu artifact lỗi:

```text
- không merge im lặng
- ghi vào validation_report
- yêu cầu rerun video/batch bị lỗi
```

---

## 17. Worker runtime report

Mỗi worker nên xuất report không overwrite theo phase, batch, và worker:

```text
manifests/worker_reports/{phase}_{batch_id}_{worker_id}.json
```

Report này giúp team biết worker chạy gì, mất bao lâu, lỗi ở đâu.

---

### 17.1. Fields khuyến nghị

```json
{
  "worker_id": "worker_kaggle_an_01",
  "platform": "kaggle",
  "profile": "production_full",
  "batch_id": "batch_003",
  "gpu_name": "Tesla T4",
  "started_at": "2026-07-01T09:00:00+07:00",
  "finished_at": "2026-07-01T15:30:00+07:00",
  "videos_processed": 12,
  "videos_failed": 1,
  "total_input_duration_sec": 14400,
  "phase_wall_time_sec": {
    "ingestion": 120,
    "shot_detection": 1800,
    "keyframe_extraction": 1600,
    "asr": 7200,
    "ocr": 2400,
    "embedding": 900,
    "artifact_upload": 600
  },
  "throughput": {
    "videos_per_hour": 1.85,
    "minutes_video_per_gpu_hour": 36.9,
    "keyframes_per_second": 4.2,
    "embedding_images_per_second": 120.0,
    "ocr_images_per_second": 18.5,
    "asr_realtime_factor": 0.7,
    "upload_MBps": 8.4
  },
  "status": "completed_with_warnings"
}
```

---

### 17.2. Vì sao cần report?

Không có report thì team không biết bottleneck ở đâu.

Có report thì biết:

```text
- ASR chậm hay OCR chậm
- GPU có dùng hiệu quả không
- upload Drive/Kaggle có nghẽn không
- batch nào quá nặng
- worker nào hay bị lỗi
```

---

## 18. Throughput metrics cần theo dõi

Các metric quan trọng:

```text
videos_per_hour
minutes_video_per_gpu_hour
keyframes_per_second
embedding_images_per_second
ocr_images_per_second
asr_realtime_factor
upload_MBps
phase_wall_time_sec
failed_video_count
retry_count
artifact_validation_fail_count
```

Ý nghĩa:

```text
videos_per_hour:
  xử lý được bao nhiêu video mỗi giờ

minutes_video_per_gpu_hour:
  một giờ GPU xử lý được bao nhiêu phút video

keyframes_per_second:
  tốc độ extract/đọc keyframe

embedding_images_per_second:
  tốc độ tạo embedding

ocr_images_per_second:
  tốc độ OCR

asr_realtime_factor:
  ASR nhanh/chậm so với độ dài video

upload_MBps:
  tốc độ upload artifact

retry_count:
  số lần phải chạy lại

artifact_validation_fail_count:
  số artifact bị lỗi schema/checksum
```

---

## 19. Recommended team workflow

### 19.1. Giai đoạn đầu

Team lead chạy:

```text
00_master_ingestion_and_assignment.ipynb
```

Notebook này làm:

```text
- scan raw videos
- lấy metadata bằng ffprobe
- tính estimated_compute_cost
- tạo videos.parquet
- tạo batch_manifest.csv
- tạo batch_000.txt, batch_001.txt...
```

---

### 19.2. Giai đoạn structure

Mỗi worker chạy:

```text
01_worker_structure_pipeline.ipynb
```

Notebook này làm:

```text
- setup runtime, HF token, GitHub package checkout, and editable package install
- restore AIC26_release/canonical_release_vXXX/phase00_ingestion/
- materialize tables/, raw_mapping/, manifests/ into local active release root
- đọc batch được giao
- đọc videos.parquet + media_store_manifest.parquet để reuse phase00 video facts
- kiểm tra structure artifact nào đã có thể reuse
- stage đúng video/metadata hiện tại từ AIC26_raw hoặc local input vào scratch nếu cần
- chạy TransNet V2 shot detection provider
- extract các frame gần 20%/50%/80% của mỗi shot
- tạo thumbnails nếu cần
- chọn middle làm representative, rồi early/late nếu quality check thất bại
- tạo đúng 1 hàng caption song ngữ/shot bằng Gemini từ representative keyframe
- chạy faster-whisper large-v3 với language auto và VAD
- link transcript vào shot
- construct scenes từ images, shot captions, transcript, và timeline
- tạo scene_summaries.parquet song ngữ bằng Gemini sau khi boundary cố định
- tạo structure artifact ZIP
- ghi local artifact to artifacts/structure/{video_id}_structure.zip
- ghi local runtime report to manifests/worker_reports/structure_{batch_id}_{worker_id}.json
- cleanup scratch
- sync local batch artifact/report lên HF phase01_structure
```

HF sync target cho phase này, khi workflow sync riêng được implement:

```text
AIC26_release/canonical_release_vXXX/phase01_structure/artifacts/{batch_id}/{video_id}_structure.zip
AIC26_release/canonical_release_vXXX/phase01_structure/worker_reports/structure_{batch_id}_{worker_id}.json
```

---

### 19.3. Giai đoạn feature

Mỗi worker chạy:

```text
02_worker_feature_enrichment.ipynb
```

Notebook này làm:

```text
- đọc batch được giao
- kiểm tra feature artifact nào đã có thể reuse
- chạy riêng SigLIP và BEiT3 embedding nếu cần
- chạy Gemini OCR nếu artifact chưa có
- chạy object detection nếu artifact chưa có
- tạo text_sources từ OCR/object labels nếu cần
- tạo feature artifact ZIP
- ghi local artifact to artifacts/features/{video_id}_features.zip
- ghi local runtime report to manifests/worker_reports/features_{batch_id}_{worker_id}.json
```

HF sync target cho phase này, khi workflow sync riêng được implement:

```text
AIC26_release/canonical_release_vXXX/phase02_features/artifacts/{batch_id}/{video_id}_features.zip
AIC26_release/canonical_release_vXXX/phase02_features/worker_reports/features_{batch_id}_{worker_id}.json
```

---

### 19.4. Giai đoạn merge/release

Team lead hoặc một worker chính chạy:

```text
03_merge_validate_index_release.ipynb
```

Notebook này làm:

```text
- scan artifact ZIP từ local package layout hoặc từ HF target layout đã được restore riêng
- validate manifest/checksum/schema
- merge parquet tables
- build text_documents
- build/write feature_availability
- build/write release_capabilities
- build app.sqlite + FTS5
- build riêng siglip.faiss và beit3.faiss + shared vector_map
- write validation_report
- chạy smoke test
- upload phase03_merged, releases, and logs under AIC26_release/canonical_release_vXXX/
```

---

## 20. Trách nhiệm của teammate

Mỗi teammate cần làm đúng 5 việc:

```text
1. Không sửa code trực tiếp trong notebook nếu không được phân công.
2. Chọn đúng batch_id hoặc worker mode.
3. Chạy đúng notebook.
4. Kiểm tra notebook báo completed hoặc completed_with_warnings.
5. Upload artifact và runtime report đúng thư mục.
```

Nếu lỗi:

```text
- không tự sửa output thủ công
- lưu log/error
- báo video_id, batch_id, worker_id, phase bị lỗi
- để team lead quyết định retry hay mark failed
```

---

## 21. MVP recommendation

MVP nên làm theo thứ tự:

```text
1. Implement cost-aware static batch assignment.
2. Implement artifact manifest/checksum.
3. Implement artifact reuse check bằng checksum/model version/config hash.
4. Implement manifests/worker_reports/{phase}_{batch_id}_{worker_id}.json.
5. Implement basic upload/validate flow.
6. Implement merge/release skeleton.
7. Chạy full production profile trên một batch nhỏ để smoke test.
8. Mở rộng full production profile sang các batch còn lại.
9. Chỉ thêm dynamic queue nếu static batch không đủ nhanh.
```

Không nên implement dynamic queue quá sớm.

Lý do:

```text
- static batch dễ hiểu hơn
- dễ debug hơn
- ít lỗi đồng bộ hơn
- đủ tốt cho MVP
- dynamic queue cần lock/heartbeat/lease phức tạp hơn
```

---

## 22. Kết luận

System 1 nên được vận hành theo nguyên tắc:

```text
Làm đúng trước.
Chia việc rõ trước.
Có artifact/validation trước.
Có reuse trước.
Có runtime report trước.
Tối ưu dynamic queue sau.
```

Mặc định dùng:

```text
cost-aware static batch assignment
```

Production profile là:

```text
full end-to-end release contract
```

Không phải:

```text
bronze/silver/gold modes cho operator chọn trong notebook production
```

Dynamic queue là advanced mode:

```text
optional, không bắt buộc cho MVP
```

Cách hiểu cuối cùng:

```text
docs/onboarding/system1_spec.md
  = thiết kế pipeline và data contract

docs/onboarding/throughput-plan.md
  = hướng dẫn chạy pipeline nhanh, phối hợp nhiều worker, tránh trùng việc, reuse artifact, dễ retry
```
