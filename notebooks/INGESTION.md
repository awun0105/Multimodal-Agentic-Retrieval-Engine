# HCMC AI Challenge - Data Ingestion Pipeline (System 1)

## 1. Overview

The Ingestion Pipeline is an isolated, offline data-processing system. Its sole responsibility is to consume the raw, fragmented dataset provided by the competition organizers, run heavy AI extraction models to uncover missing semantic context, and normalize everything into a high-performance, search-engine-optimized **Data-Ready Contract**.

The Main Retrieval Engine (System 2) relies entirely on the output of this pipeline and never interacts with the raw video files.

---

## 2. Raw Organizer Inputs

The pipeline expects the following raw directory structure provided by the competition organizers:

* **`raw_videos/`**: Source `.mp4` video files.
* **`keyframes/`**: Pre-extracted static image frames (`.jpg`).
* **`clip_features_32/`**: Pre-computed dense visual vector matrices.
* **`media_info/`**: JSON files containing video-level metadata (channel, date, keywords).
* **`object/`**: JSON files containing keyframe-level object bounding boxes and detection scores.

---

## 3. AI Feature Extraction Pipelines

To bridge the semantic gap between pure visuals and complex human queries (TKIS, Q&A, TRAKE), the ingestion system runs four distinct AI extraction pipelines before normalization.

| Extraction Pipeline | Target Model | Input Data | Output Generated |
| --- | --- | --- | --- |
| **Scene Text (OCR)** | `PaddleOCR` | `keyframes/` images | Explicit on-screen text (banners, news tickers, signs). |
| **Visual Captioning** | `BLIP-2` / `Qwen-VL` | `keyframes/` images | Detailed, paragraph-length descriptions of visual actions and spatial relationships. |
| **Audio Transcription** | `Whisper` (OpenAI) | `raw_videos/` audio | Timestamped textual transcripts of spoken dialogue and news reports. |
| **Global LLM Fusion** | `Llama-3` / `GPT-4o` | Captions + Transcripts | Video-level global summaries and chronological event timelines. |

---

## 4. Text Encoding & Embedding Strategy

To support a Hybrid Search Engine, the generated text must be encoded into mathematical matrices (for semantic meaning) AND saved as raw strings (for exact keyword matching).

**Crucial Text-Encoder Division:**

* **Visual Vector Matching:** Use the **CLIP Text Encoder** *only* when translating text to match against the organizer's `clip_features_32`.
* **Semantic Text Matching:** Use a **Dedicated Text Encoder** (e.g., `multilingual-e5-large` or `PhoBERT`) to embed your generated Captions, Transcripts, and Summaries. This prevents audio/text from being incorrectly forced into a "visual" space.

---

## 5. Global Mapping & Identity Contract

To prevent path-guessing and slow iterations, the ingestion system assigns an explicit, universal Primary Key to every frame in the dataset.

* **Naming Convention:** `{video_id}_{frame_id}`
* **Example:** Keyframe `042.jpg` from video `L21_V001` becomes global ID **`L21_V001_042`**.
* This ID links a single matrix row (e.g., Row 42) directly to its physical storage path and its relational metadata dicts without requiring search loops.

---

## 6. The Data-Ready Output Architecture

Once the ingestion pipeline completes all extractions and encodings, it deposits the normalized data into this exact folder structure. This directory is the final hand-off point to the Retrieval Engine.

```text
📁 data_ready_output/
 │
 ├── 📁 dense_index/               [Target: FAISS / NumPy RAM]
 │    │                            Purpose: Semantic meaning & cosine similarity math
 │    ├── visual.npy               (Source: Organizer's CLIP vectors)
 │    ├── captions_e5.npy          (Source: VLM text -> Dedicated Text Encoder)
 │    ├── transcripts_e5.npy       (Source: Whisper text -> Dedicated Text Encoder)
 │    └── summaries_e5.npy         (Source: LLM Fusion text -> Dedicated Text Encoder)
 │
 ├── 📁 sparse_index/              [Target: Rank-BM25]
 │    │                            Purpose: Exact keyword, name, and proper noun matching
 │    ├── metadata_strings.json    (Titles, keywords, author names)
 │    ├── ocr_strings.json         (On-screen banners and signs)
 │    ├── caption_strings.json     (Raw VLM paragraphs)
 │    ├── transcript_strings.json  (Raw Whisper audio text)
 │    └── summary_strings.json     (Raw LLM fusion timelines)
 │
 ├── 📁 relational_db/             [Target: Native Python Dictionaries]
 │    │                            Purpose: O(1) hard filtering and boolean logic
 │    ├── video_constraints.json   (e.g., length_seconds, exact publish date)
 │    └── object_counts.json       (e.g., {"car": 2, "skyscraper": 6})
 │
 └── 📁 registry/                  [Target: System Glue]
      │                            Purpose: Mapping math results back to physical files
      ├── row_to_frame_id.json     (Maps Dense Index row '42' to ID 'L21_V001_042')
      └── frame_to_storage.json    (Maps ID 'L21_V001_042' to 'keyframes/L21_V001/042.jpg')

```

Here is the complete documentation for **System 2 (The Main Retrieval Engine)** to match your ingestion pipeline. You can save this as `retrieval_engine.md`.

This covers how the software actually "thinks," searches, and scores the normalized data to generate your final top 100 submissions.

---

# HCMC AI Challenge - Main Retrieval Engine (System 2)

## 1. Overview

The Main Retrieval Engine is the live-action core of the submission system. It is a highly optimized, read-only search engine. It does not process raw video or run heavy AI extraction models. Instead, it loads the **Data-Ready Contract** (generated by System 1) directly into RAM, allowing for instant, multi-modal search querying across hundreds of thousands of frames.

---

## 2. Memory Boot Sequence

To achieve sub-second query times, the system avoids database network latency by loading the normalized files directly into local system memory upon startup.

| Engine Component | Target Directory | Underlying Technology | Boot Action |
| --- | --- | --- | --- |
| **Semantic Core** | `dense_index/` | `FAISS` / `NumPy` | Loads `.npy` matrices into Euclidean/Cosine similarity indices. |
| **Keyword Core** | `sparse_index/` | `Rank-BM25` | Parses string lists into inverted term-frequency indices. |
| **Rules Core** | `relational_db/` | Native Python Dictionaries | Loads JSONs into $O(1)$ lookup tables for hard constraints. |
| **Path Resolver** | `registry/` | Native Python Dictionaries | Loads mapping JSONs to trace matrix rows to physical images. |

---

## 3. The Three Search Modules

Depending on the prompt provided by the organizer, the engine dynamically triggers different combinations of search modules.

### A. The Semantic Module (Vector Search)

* **Goal:** Understand visual vibes, synonyms, and overarching concepts.
* **Mechanism:** Converts the user's text query into a dense vector (using CLIP and/or E5). It runs a cosine similarity scan across `visual.npy`, `captions_e5.npy`, and `transcripts_e5.npy`.
* **Output:** A soft score between 0.0 and 1.0 representing mathematical closeness.

### B. The Keyword Module (Sparse Search)

* **Goal:** Catch exact proper nouns, channel names, dates, and on-screen text.
* **Mechanism:** Uses BM25 to search the query text against `metadata_strings.json` and `ocr_strings.json`.
* **Output:** A frequency-based score that spikes massively if an exact keyword is found.

### C. The Logical Rules Module (Hard Constraints)

* **Goal:** Enforce strict parameters (e.g., "Must contain two cars").
* **Mechanism:** Evaluates dictionary keys in `object_counts.json`.
* **Output:** A Boolean mask (True/False). If a frame fails the logical rule, its final score is immediately zeroed out, removing it from the candidate pool.

---

## 4. The Hybrid Scoring Equation (Cross-Modal Fusion)

To rank the final Top 100 frames, the engine does not rely on a single model. It normalizes the scores from the Semantic and Keyword modules and blends them using a configurable weight equation.

$$S_{\text{final}} = w_1(S_{\text{visual}}) + w_2(S_{\text{caption}}) + w_3(S_{\text{audio}}) + w_4(S_{\text{ocr\_bm25}})$$

*Weights are stored in a `config.yaml` file so the team can adjust them dynamically during the competition without rewriting code.*

---

## 5. Competition Task Handlers

The engine features a `QueryState` session manager to handle the three specific HCMC AI Challenge task types:

* **TKIS (Textual Search):** Runs the standard Hybrid Scoring Equation. Heavily weights $S_{\text{visual}}$ and $S_{\text{caption}}$.
* **Q&A (Visual Questions):** Heavily weights the Logical Rules Module to verify object counts and spatial relationships before ranking visually similar frames.
* **TRAKE (Temporal Alignment):** 1. Executes independent searches for `Clue A` and `Clue B`.

1. Runs a **Temporal Cross-Check**: Scans the `Path Resolver` to ensure the winning frame for `Clue B` occurs chronologically *after* the winning frame for `Clue A` within the same `video_id`.

---

Now that the complete architectural blueprints for both System 1 and System 2 are fully documented, would you like to start drafting the actual Python base classes for the `RetrievalEngine` to see how the FAISS and BM25 loaders are implemented in code?

To build the Ingestion System successfully, you need to know exactly what the inside of these output files looks like. The design philosophy here is **Flat and Decoupled**—meaning no file contains everything, but every file shares a universal key so they can instantly link together.

Here is a deep dive into the internal design of each output file, complete with concrete examples and an explanation of the underlying mapping logic.

---

### 1. 📁 registry/ (The System Glue)

These files do not contain searchable data. Their only job is to act as a translation layer. Because NumPy matrices (`.npy`) do not have built-in row names (they only have numerical indices like Row 0, Row 1, Row 2), we must map those index numbers to our Global Frame IDs, and then map those IDs to physical files.

#### `row_to_frame_id.json`

* **Purpose:** A flat array where the index position exactly matches the row position in **all** your `.npy` matrices.
* **Internal Design Example:**

```json
[
  "L21_V001_042",   // This is Row 0 in all matrices
  "L21_V001_043",   // This is Row 1 in all matrices
  "L21_V002_001"    // This is Row 2 in all matrices
]

```

#### `frame_to_storage.json`

* **Purpose:** A dictionary mapping the Global Frame ID directly to the physical image path on your hard drive, allowing the system to retrieve the image instantly for final submission or display.
* **Internal Design Example:**

```json
{
  "L21_V001_042": "keyframes/L21_V001/042.jpg",
  "L21_V001_043": "keyframes/L21_V001/043.jpg",
  "L21_V002_001": "keyframes/L21_V002/001.jpg"
}

```

---

### 2. 📁 dense_index/ (The Semantic Math)

These are binary files containing multi-dimensional float arrays. The Retrieval Engine loads these directly into FAISS (Facebook AI Similarity Search) to perform ultra-fast cosine similarity math.

#### `visual.npy`, `captions_e5.npy`, `transcripts_e5.npy`

* **Purpose:** To store the semantic meaning of the image, the VLM text, and the Whisper audio as vectors.
* **Internal Design (Conceptual Python View):**

```python
# If you run: np.load("dense_index/visual.npy")
[
  [ 0.1042, -0.0531,  0.8842, ..., -0.1120],  # Row 0 -> belongs to L21_V001_042
  [-0.0121,  0.1341, -0.0024, ...,  0.5512],  # Row 1 -> belongs to L21_V001_043
  [ 0.6512,  0.0011,  0.3141, ..., -0.0981]   # Row 2 -> belongs to L21_V002_001
]

```

*(Crucially, notice how Row 0 in the `.npy` file aligns perfectly with Index 0 in `row_to_frame_id.json`.)*

---

### 3. 📁 sparse_index/ (The Text Keywords)

These JSON files store pure string data. When the system boots, it feeds these strings into an inverted text index (like Rank-BM25) to allow for instantaneous keyword searching (e.g., catching exactly when someone says "Thành phố Hồ Chí Minh").

#### `caption_strings.json`

* **Purpose:** The raw paragraphs generated by your Vision Language Model (BLIP-2/Qwen) describing what is physically happening in the frame.
* **Internal Design Example:**

```json
{
  "L21_V001_042": "A wide shot of a busy intersection in the rain. Several motorbikes are stopped at a red light.",
  "L21_V001_043": "A close-up of a traffic police officer directing vehicles under an umbrella."
}

```

#### `ocr_strings.json`

* **Purpose:** Hard text extracted directly off the screen by PaddleOCR.
* **Internal Design Example:**

```json
{
  "L21_V001_042": "60 GIÂY SÁNG TÌNH HÌNH GIAO THÔNG",
  "L21_V001_043": ""  // Empty string if no text was detected on screen
}

```

#### `transcript_strings.json`

* **Purpose:** The exact words spoken during that specific frame, provided by Whisper.
* **Internal Design Example:**

```json
{
  "L21_V001_042": "Mưa lớn kéo dài từ sáng sớm đã khiến nhiều tuyến đường ùn tắc...",
  "L21_V001_043": "...lực lượng chức năng đang nỗ lực điều tiết giao thông."
}

```

---

### 4. 📁 relational_db/ (The Hard Rules)

These files act as strict filters. If a query requires exactly "two cars," your mathematical vectors cannot reliably verify that. This database provides the hard Boolean logic.

#### `object_counts.json`

* **Purpose:** A parsed, threshold-cleaned version of the organizer's messy raw object tracking files.
* **Internal Design Example:**

```json
{
  "L21_V001_042": {
    "car": 2,
    "motorcycle": 15,
    "traffic_light": 1
  },
  "L21_V001_043": {
    "person": 1,
    "umbrella": 1
  }
}

```

#### `video_constraints.json`

* **Purpose:** Video-level constraints (like length and broadcast channel) mapped to all frames belonging to that video.
* **Internal Design Example:**

```json
{
  "L21_V001": {
    "publish_date": "2024-08-01",
    "channel": "HTV",
    "length_seconds": 1262
  }
}

```

---

### 5. How Everything Maps and Connects

Because the system is decoupled to save memory, the connections happen dynamically during the execution of a search. Here is the step-by-step resolution flow of how these decoupled files interact when a user query arrives:

**The Scenario:** A query asks for: *"Find a rainy traffic scene with exactly 2 cars where they discuss traffic jams (ùn tắc)."*

1. **Semantic Math (The Anchor):** Your engine encodes the query into a vector and checks `visual.npy`. It calculates that **Row 0** mathematically looks the most like a "rainy traffic scene."
2. **Identity Resolution (The Bridge):**
The engine takes **Row 0** and looks it up in `row_to_frame_id.json`. It discovers that Row 0 is the ID **`L21_V001_042`**.
3. **Keyword Verification (The Check):**
The engine checks the BM25 index built from `transcript_strings.json` using the ID `L21_V001_042`. It finds a massive score spike because the audio at that exact frame contains the word "ùn tắc" (traffic jam).
4. **Logical Verification (The Rule):**
The engine checks `object_counts.json` for the ID `L21_V001_042`. It sees `"car": 2`. The condition passes perfectly.
5. **Final Output (The Fetch):**
The engine looks up `L21_V001_042` in `frame_to_storage.json`, gets the path `keyframes/L21_V001/042.jpg`, and writes this final result to your competition submission CSV file.

----

Đây là **"Bản Đặc Tả Vận Hành" (Standard Operating Procedure - SOP)** chi tiết nhất dành cho team của bạn. Nếu toàn đội tuân thủ đúng quy trình này, các bạn có thể huy động 10, 20 hay thậm chí 30 tài khoản Colab/Kaggle chạy cùng lúc mà dữ liệu vẫn gọn gàng, khớp nhau 100% và không bao giờ bị tràn RAM.

### PHẦN 1: TỔ CHỨC QUY TRÌNH (THE HUMAN WORKFLOW)

Trước khi đụng vào code, team phải có một "Trạm kiểm soát" chung.

1. **Sổ Cái (Google Sheets):** Chia toàn bộ 500GB dữ liệu thành các **Chunk** (Ví dụ: `Chunk_01` = Folder L01 đến L05).
2. **Quy tắc "Khóa cọc":** Khi một teammate nhận chạy `Chunk_01` cho mô hình Vision (CLIP), họ phải ghi tên vào cột đó. Tuyệt đối không ai được chạy trùng.
3. **Quy tắc "Zip & Ship":** Chạy xong Chunk nào, người đó nén (zip) toàn bộ thư mục output lại, tải về máy và dán link hoặc báo "Done" lên group.

---

### PHẦN 2: KIẾN TRÚC 3 NOTEBOOKS (THE SPECIALISTS)

Chúng ta sẽ đóng băng (freeze) 3 file Notebook mẫu. Mọi người chỉ việc copy file này lên Colab/Kaggle, sửa đúng 1 dòng khai báo `Chunk_ID` và bấm *Run All*.

#### 1. `NB_01_Vision_CLIP.ipynb` (Xử lý Ảnh -> Vector)

* **Nhiệm vụ:** Rút trích khung hình (1fps) và biến thành ma trận toán học.
* **Mô hình:** OpenCLIP (ViT-B/32).
* **Đầu ra (Output):** Tạo ra thư mục `temp_dense/`.
* Mỗi video sinh ra 1 file: `[SystemID]_dense.npy`. (VD: `L01_V001_dense.npy` chứa vector của toàn bộ frame trong video đó).

* **Lưu ý RAM:** Load model CLIP 1 lần vào GPU. Đọc video bằng `cv2`, băm frame nào đẩy qua GPU frame đó, xong giải phóng bộ nhớ ngay.

#### 2. `NB_02_Audio_Whisper.ipynb` (Xử lý Âm thanh -> Text)

* **Nhiệm vụ:** Tách audio từ MP4, dịch thành văn bản kèm timestamp.
* **Mô hình:** Whisper (Base hoặc Small - tuyệt đối không dùng Large để tiết kiệm thời gian).
* **Đầu ra (Output):** Tạo ra thư mục `temp_sparse/`.
* Mỗi video sinh ra 1 file: `[SystemID]_transcript.json`.

#### 3. `NB_03_Metadata_OCR.ipynb` (Xử lý Text Màn hình & Bộ lọc)

* **Nhiệm vụ:** Quét chữ trên video (chỉ quét các keyframe quan trọng) và bóc tách metadata gốc của Ban tổ chức.
* **Mô hình:** EasyOCR (nhẹ, chạy được trên CPU/GPU yếu).
* **Đầu ra (Output):** Tạo ra thư mục `temp_sparse/` và `temp_metadata/`.
* `[SystemID]_ocr.json`
* `[SystemID]_meta.json` (chứa fps, duration, width, height...).

---

### PHẦN 3: 4 RÀNG BUỘC "THÉP" TRONG NOTEBOOK (CONSTRAINTS)

Bất kỳ ai trong team viết code cho 3 Notebook trên đều phải tuân thủ 4 đoạn code "bảo hiểm" này:

**1. Khai báo tham số đầu vào ở Cell đầu tiên:**
Mọi đường dẫn phải là biến số. Không ai được hardcode (code cứng) đường dẫn máy cá nhân vào logic.

```python
# CẤU HÌNH DUY NHẤT CẦN SỬA KHI CHẠY
DATA_CHUNK = "L01" # Chạy folder nào?
RAW_PATH = f"/kaggle/input/dataset/{DATA_CHUNK}"
OUTPUT_PATH = f"/kaggle/working/output/{DATA_CHUNK}"

```

**2. Checkpointing (Cứu sinh khi sập máy):**
Trước khi đưa video vào model AI, luôn kiểm tra xem file output đã tồn tại chưa.

```python
output_file = os.path.join(OUTPUT_PATH, f"{video_name}_dense.npy")
if os.path.exists(output_file):
    print(f"Skipping {video_name}, already processed.")
    continue # Bỏ qua, chạy video tiếp theo

```

**3. Chuẩn hóa Naming Convention (System ID):**
Tên file phải được tạo bằng hàm chuẩn, biến `L01/V001.mp4` thành `L01_V001`. Tuyệt đối không dùng khoảng trắng hay ký tự lạ.

**4. Dọn rác (Garbage Collection):**
Cuối vòng lặp của mỗi video, phải gọi `del` và `gc.collect()` để dọn dẹp RAM, nếu không Colab sẽ báo OOM sau 50 video.

```python
import gc
# ... (sau khi lưu file npy xong)
del frames, features
gc.collect()

```

---

### PHẦN 4: BƯỚC VỀ ĐÍCH - THE AGGREGATOR SCRIPT

Đây là lúc "phép màu" xảy ra. Sát giờ thi đấu, toàn team mang các cục file `.zip` (chứa hàng ngàn file `.npy` và `.json` nhỏ xíu) đổ hết vào một ổ cứng chứa máy Host.

Bạn (hoặc người code cứng nhất team) sẽ chạy một script duy nhất trên máy Host: `00_Merge_To_DataReady.py`.
Script này chạy trong khoảng 5-10 phút, thực hiện 3 việc siêu tốc:

1. **Gộp Dense:** Tìm tất cả file `*_dense.npy`. Dùng `np.concatenate()` nối chúng lại thành 1 siêu ma trận `visual.npy`.
2. **Gộp Sparse:** Đọc tất cả `_transcript.json` và `_ocr.json`, gom vào 2 siêu file `transcript_strings.json` và `ocr_strings.json`.
3. **Sinh Registry (Bản đồ):** Script này sẽ tự động đọc tên các file (Ví dụ thấy `L01_V001_042`), tra ngược lại thư mục raw gốc, và tự động viết ra file `registry/frame_to_storage.json`.

**Kết quả:** Bạn có 1 folder `data_ready_output/` hoàn hảo, gọn gàng ~5-10GB. Máy Host lập tức nạp folder này vào FastAPI (System 2) và sẵn sàng nghênh chiến.

Với quy trình này, team bạn có thể hoạt động như một "đội quân kiến": Mỗi người tha một mảnh nhỏ về tổ, không ai đụng ai, máy sập thì chạy lại không mất data, và phút chót mọi thứ khớp vào nhau như một bộ xếp hình Lego. Bạn thấy tự tin với quy trình (SOP) này chưa?
