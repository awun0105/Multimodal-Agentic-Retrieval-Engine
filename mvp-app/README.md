# AIoU MVP Retrieval App

This is a local monolith app for keyframe retrieval.

It uses:

- keyframe images
- CLIP image embeddings
- object detection data
- video metadata

The app runs on your local machine. It is not a Hugging Face Space runtime.

## What the app does

You type a text query. The app embeds the query with CLIP, searches the prepared
image index, and shows the best keyframes.

You can also filter by:

- collection
- video ID
- author or channel
- object label
- publish date

Vietnamese queries are translated to English before CLIP search.

## Folder layout

The app code is in this folder:

```text
mvp-app/
├── app.py
├── requirements.txt
├── .env.example
└── README.md
```

The data is downloaded from this Hugging Face bucket:

```text
https://huggingface.co/buckets/1thesudden/aiou-app-storage
```

The app expects one ready release folder like this:

```text
data/aic25-b1-v1/
├── keyframes/
├── index/
│   ├── embeddings.f16.npy
│   ├── keyframes.faiss
│   └── faiss.meta.json
├── metadata/
│   ├── videos.parquet
│   ├── keyframes.parquet
│   ├── detections.parquet
│   └── runtime.sqlite
├── reports/
├── manifest.json
└── READY.json
```

`manifest.json` and `READY.json` are required. The app checks them at startup.

## Requirements

- Python 3.10
- Git
- Hugging Face CLI `hf`
- Enough disk space for the release data

The data bucket is public, so login is not required for normal download.

## 1. Go to the app folder

```bash
cd mvp-app
```

## 2. Create Python env

```bash
python3.10 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

If `python3.10` is not found, install Python 3.10 first.

## 3. Install Hugging Face CLI

Install `hf` if you do not have it:

```bash
curl -LsSf https://hf.co/cli/install.sh | bash -s
```

No login is needed for the public bucket.

Only login if the command later fails with an auth or permission error:

```bash
hf auth login
hf auth whoami
```

## 4. Download the data

From inside `mvp-app`, run:

```bash
mkdir -p data
hf buckets sync \
  hf://buckets/1thesudden/aiou-app-storage/releases/aic25-b1-v1 \
  ./data/aic25-b1-v1
```

After download, check:

```bash
test -f data/aic25-b1-v1/READY.json
test -f data/aic25-b1-v1/manifest.json
test -d data/aic25-b1-v1/keyframes
```

No output means the files exist.

## 5. Create local config

```bash
cp .env.example .env
```

Edit `.env` and set `DATA_ROOT` to the full path of your data folder.

Example:

```env
DATA_ROOT=/home/your-user/PROJECT/Multimodal-Agentic-Retrieval-Engine/mvp-app/data/aic25-b1-v1
CACHE_ROOT=/tmp/aiou-cache
```

Use a full path. Do not use `~` in `.env`.

Keep these model values unchanged unless you rebuild the index:

```env
MODEL_ID=openai/clip-vit-base-patch32
MODEL_REVISION=3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268
TRANSLATION_MODEL_ID=Helsinki-NLP/opus-mt-vi-en
TRANSLATION_MODEL_REVISION=c8d2853e77f5fae31124d993e0b35176b1c8914e
```

## 6. Run the app

```bash
. .venv/bin/activate
python app.py
```

Open:

```text
http://localhost:7860
```

To use another port:

```bash
PORT=7861 python app.py
```

Set `PORT` in the command line. Do not put it in `.env`.

## Normal local flow

```text
download data from bucket
        ↓
set DATA_ROOT in .env
        ↓
run python app.py
        ↓
open browser
        ↓
search keyframes
```

## What happens at startup

The app checks the release files, then copies these files to the local cache:

- `index/keyframes.faiss`
- `index/embeddings.f16.npy`
- `metadata/runtime.sqlite`

Images stay in `DATA_ROOT/keyframes`.

Default cache path:

```text
/tmp/aiou-cache
```

You can change it with `CACHE_ROOT` in `.env`.

## Quick test

Run:

```bash
pytest
```

Then run:

```bash
python app.py
```

Search for:

```text
person riding a motorbike
```

You should see keyframe results.

## API endpoints

When the app is running, Gradio exposes:

- `/search_keyframes`
- `/get_keyframe_details`

Use the browser UI first. Use the API only if you need script access.

## Common problems

### `Release is not ready`

`DATA_ROOT` is wrong, or the data download is not complete.

Check:

```bash
ls /full/path/to/mvp-app/data/aic25-b1-v1
```

It must show `READY.json` and `manifest.json`.

### `Release manifest not found`

`manifest.json` is missing. Download the full release again.

### Model download is slow

The first run downloads CLIP and translation model files. Later runs use the
local Hugging Face cache.

### Port already in use

Run on another port:

```bash
PORT=7861 python app.py
```

### No images in results

Check that this folder exists:

```bash
ls /full/path/to/mvp-app/data/aic25-b1-v1/keyframes
```

If it is missing, download the full bucket release again.
