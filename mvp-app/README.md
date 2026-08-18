# AIoU MVP Retrieval App

Local keyframe retrieval app for the AIoU MVP. The app runs on your machine with
Gradio, CLIP text search, metadata filters, object filters, and Vietnamese to
English query translation.

## What the App Does

You type a text query. The app embeds the query with CLIP, searches the prepared
image index, and returns the best keyframes.

You can filter results by:

- collection
- video ID
- author or channel
- object label
- publish date

Vietnamese queries are translated to English before CLIP search.

## Setup Flow

Follow these sections in order:

1. Get only the `mvp-app` folder from GitHub.
2. Install Python dependencies.
3. Install Hugging Face CLI.
4. Download the release data.
5. Configure `.env`.
6. Run the app.

## 1. Get Only the `mvp-app` Folder from GitHub

Normal `git clone` downloads the whole repository. To download only this app
folder, use Git sparse checkout. This requires Git 2.25 or newer.

### Option A: Git Sparse Checkout

Linux/macOS/Git Bash:

```bash
git clone --no-checkout --depth 1 --single-branch -b monolith-mvp-app \
  https://github.com/awun0105/Multimodal-Agentic-Retrieval-Engine.git
cd Multimodal-Agentic-Retrieval-Engine
git sparse-checkout set mvp-app
git checkout
cd mvp-app
```

Windows PowerShell:

```powershell
git clone --no-checkout --depth 1 --single-branch -b monolith-mvp-app https://github.com/awun0105/Multimodal-Agentic-Retrieval-Engine.git
cd Multimodal-Agentic-Retrieval-Engine
git sparse-checkout set mvp-app
git checkout
cd mvp-app
```

What each option means:

- `--no-checkout`: creates the repo folder before downloading files.
- `--depth 1`: downloads only the latest commit history.
- `--single-branch -b monolith-mvp-app`: downloads only the app branch.
- `git sparse-checkout set mvp-app`: keeps only the `mvp-app/` folder in your
  working tree.

### Option B: SVN Export from GitHub

Use this if you only want a copy of the folder and do not need Git history,
commit, or push.

Linux/macOS/Git Bash:

```bash
svn export \
  https://github.com/awun0105/Multimodal-Agentic-Retrieval-Engine/branches/monolith-mvp-app/mvp-app
cd mvp-app
```

Windows PowerShell:

```powershell
svn export https://github.com/awun0105/Multimodal-Agentic-Retrieval-Engine/branches/monolith-mvp-app/mvp-app
cd mvp-app
```

Do not use `git archive --remote` for GitHub. GitHub blocks that mode.

## 2. Requirements

- `uv`
- Git 2.25 or newer
- Hugging Face CLI `hf`
- Enough disk space for the release data

The data bucket is public. Hugging Face login is normally not required.

## Folder Layout

```text
mvp-app/
├── app.py
├── requirements.txt
├── requirements-dev.txt
├── .env.example
├── tests/
└── README.md
```

The app expects one ready release folder:

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

## 3. Install the App

From inside `mvp-app` folder:

Install `uv` first if the command is missing.

Linux/macOS:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then create the Python 3.10 environment and install dependencies:

Linux/macOS:

```bash
uv venv --python 3.10
source .venv/bin/activate
uv pip install -r requirements.txt
```

Windows PowerShell:

```powershell
uv venv --python 3.10
.\.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt
```

`uv venv --python 3.10` creates `.venv` with Python 3.10. If Python 3.10 is not
already installed locally, `uv` can download and install it automatically.

## 4. Install Hugging Face CLI

Install `hf` if you do not already have it:

Linux/macOS:

```bash
curl -LsSf https://hf.co/cli/install.sh | bash -s
hf --help
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://hf.co/cli/install.ps1 | iex"
hf --help
```

If `hf --help` says `command not found`, close and reopen the terminal, then
return to the `mvp-app` folder and activate the Python environment again.

No login is needed for the public bucket. Only login if download later fails
with an auth or permission error:

```bash
hf auth login
hf auth whoami
```

## 5. Download the Data

From inside `mvp-app`:

Linux/macOS:

```bash
mkdir -p data
hf buckets sync \
  hf://buckets/1thesudden/aiou-app-storage/releases/aic25-b1-v1 \
  ./data/aic25-b1-v1
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force data
hf buckets sync `
  hf://buckets/1thesudden/aiou-app-storage/releases/aic25-b1-v1 `
  .\data\aic25-b1-v1
```

### Faster Download for Slow Networks

The release data is large. Downloads from Hugging Face can be slow in Vietnam or
on unstable international routes because of long-distance routing, single
connection behavior in some download paths, CDN throttling during busy hours, or
VPN/proxy interference.

Use the normal command above first. If it is too slow, enable the Hugging Face
high-performance transfer mode and run the same sync again.

Linux/macOS:

```bash
mkdir -p data
HF_XET_HIGH_PERFORMANCE=1 hf buckets sync \
  hf://buckets/1thesudden/aiou-app-storage/releases/aic25-b1-v1 \
  ./data/aic25-b1-v1
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force data
$env:HF_XET_HIGH_PERFORMANCE=1
hf buckets sync `
  hf://buckets/1thesudden/aiou-app-storage/releases/aic25-b1-v1 `
  .\data\aic25-b1-v1
```

If the download stops halfway, run the same `hf buckets sync` command again. It
syncs the target folder and should continue from the missing or incomplete
files.

If you see `HTTP 429 Too Many Requests`, login to Hugging Face and retry:

```bash
hf auth login
hf auth whoami
```

If the transfer freezes or shows SSL/TLS errors while using a VPN, proxy, or
company network, turn off the VPN/proxy and retry. If it still fails, remove
`HF_XET_HIGH_PERFORMANCE=1` and use the normal sync command. It can be slower,
but it is often more tolerant on restricted networks.

Older tutorials may recommend `hf_transfer` with
`HF_HUB_ENABLE_HF_TRANSFER=1`:

```bash
uv pip install hf_transfer huggingface_hub
HF_HUB_ENABLE_HF_TRANSFER=1 hf buckets sync \
  hf://buckets/1thesudden/aiou-app-storage/releases/aic25-b1-v1 \
  ./data/aic25-b1-v1
```

That legacy flag is deprecated in current `huggingface_hub` versions. Prefer
`HF_XET_HIGH_PERFORMANCE=1` unless you are intentionally using an older
Hugging Face stack.

If you have a direct HTTPS URL for a single large file, `aria2` can also use
multiple connections:

```bash
sudo apt install aria2
aria2c -x 16 -s 16 -k 1M "https://huggingface.co/datasets/.../file"
```

This `aria2` path is only for direct file URLs. For this app's bucket release,
prefer `hf buckets sync`.

Check the download:

Linux/macOS:

```bash
test -f data/aic25-b1-v1/READY.json
test -f data/aic25-b1-v1/manifest.json
test -d data/aic25-b1-v1/keyframes
```

Windows PowerShell:

```powershell
Test-Path .\data\aic25-b1-v1\READY.json
Test-Path .\data\aic25-b1-v1\manifest.json
Test-Path .\data\aic25-b1-v1\keyframes
```

Linux/macOS prints no output when the required files exist. Windows PowerShell
prints `True` for each existing path.

## 6. Configure `.env`

Create local config:

Linux/macOS:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Set `DATA_ROOT` to the full path of your data folder:

Linux/macOS:

```env
DATA_ROOT=/home/your-user/Multimodal-Agentic-Retrieval-Engine/mvp-app/data/aic25-b1-v1
CACHE_ROOT=/tmp/aiou-cache
```

Windows:

```env
DATA_ROOT=C:\Users\your-user\Multimodal-Agentic-Retrieval-Engine\mvp-app\data\aic25-b1-v1
CACHE_ROOT=C:\Users\your-user\AppData\Local\Temp\aiou-cache
```

Use a full path. Do not use `~` in `.env`.

Keep these model values unchanged unless you rebuild the index:

```env
MODEL_ID=openai/clip-vit-base-patch32
MODEL_REVISION=3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268
TRANSLATION_MODEL_ID=Helsinki-NLP/opus-mt-vi-en
TRANSLATION_MODEL_REVISION=c8d2853e77f5fae31124d993e0b35176b1c8914e
```

## 7. Run the App

Linux/macOS:

```bash
source .venv/bin/activate
python app.py
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python app.py
```

Open:

```text
http://localhost:7860
```

Use another port if `7860` is busy:

Linux/macOS:

```bash
PORT=7861 python app.py
```

Windows PowerShell:

```powershell
$env:PORT=7861
python app.py
```

Set `PORT` in the command line. Do not put it in `.env`.

## 8. Quick Test

Install development dependencies:

Linux/macOS:

```bash
source .venv/bin/activate
uv pip install -r requirements-dev.txt
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
uv pip install -r requirements-dev.txt
```

Run tests:

```bash
pytest
```

Then run the app and search:

```text
person riding a motorbike
```

You should see keyframe results.

## Startup Behavior

At startup, the app checks the release files and copies these files to the local
cache:

- `index/keyframes.faiss`
- `index/embeddings.f16.npy`
- `metadata/runtime.sqlite`

Images stay in `DATA_ROOT/keyframes`.

Default cache path:

```text
/tmp/aiou-cache
```

You can change it with `CACHE_ROOT` in `.env`.

## API Endpoints

When the app is running, Gradio exposes:

- `/search_keyframes`
- `/get_keyframe_details`

Use the browser UI first. Use the API only if you need script access.

## Common Problems

### `uv: command not found`

Install `uv`, then close and reopen the terminal.

Linux/macOS:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Return to the app folder and rerun `uv venv --python 3.10`.

### `hf: command not found`

Close and reopen the terminal, then return to the app folder:

Linux/macOS:

```bash
cd /full/path/to/mvp-app
source .venv/bin/activate
hf --help
```

Windows PowerShell:

```powershell
cd C:\full\path\to\mvp-app
.\.venv\Scripts\Activate.ps1
hf --help
```

### `Release is not ready`

`DATA_ROOT` is wrong, or the data download is not complete. Check:

Linux/macOS:

```bash
ls /full/path/to/mvp-app/data/aic25-b1-v1
```

Windows PowerShell:

```powershell
Get-ChildItem C:\full\path\to\mvp-app\data\aic25-b1-v1
```

It must show `READY.json` and `manifest.json`.

### `Release manifest not found`

`manifest.json` is missing. Download the full release again:

Linux/macOS:

```bash
hf buckets sync \
  hf://buckets/1thesudden/aiou-app-storage/releases/aic25-b1-v1 \
  ./data/aic25-b1-v1
```

Windows PowerShell:

```powershell
hf buckets sync `
  hf://buckets/1thesudden/aiou-app-storage/releases/aic25-b1-v1 `
  .\data\aic25-b1-v1
```

### Model Download Is Slow

The first run downloads CLIP and translation model files. Later runs use the
local Hugging Face cache.

### Port Already in Use

Run on another port:

Linux/macOS:

```bash
PORT=7861 python app.py
```

Windows PowerShell:

```powershell
$env:PORT=7861
python app.py
```

### No Images in Results

Check that this folder exists:

```bash
ls /full/path/to/mvp-app/data/aic25-b1-v1/keyframes
```

If it is missing, download the full bucket release again.
