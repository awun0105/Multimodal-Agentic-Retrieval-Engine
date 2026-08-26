# AIoU MVP Retrieval App

Local keyframe retrieval app for the AIoU MVP. The app runs on your machine with
Gradio, CLIP text search, metadata filters, object filters, and Vietnamese to
English query translation.

## What the App Does

You type a text query. The app embeds Vietnamese or English text with the
multilingual CLIP-aligned encoder, searches the prepared image index, and
returns the best keyframes.

You can filter results by:

- collection
- video ID
- author or channel
- object label
- publish date

The checked `Translate Vietnamese query to English` option enables deep search:
NLLB translates Vietnamese to English, then multilingual CLIP embeds the English
query. Clear it for the faster path, where multilingual CLIP embeds the original
Vietnamese or English query directly without loading NLLB.

### Inline Metadata Shortcuts

The Query box also accepts metadata tokens (comma-separated, order-free):

| Input | Meaning |
|---|---|
| `L26` | every keyframe in collection L26, in canonical order |
| `L26_V306` | every keyframe of that video, in canonical order |
| `L26_V306_049` or `L26_V306, 49` | exactly that keyframe |
| `con cá, L26_V306` | semantic search scoped to that video |
| `con cá, L26` | semantic search scoped to that collection |

Pure metadata input never loads CLIP. The Status line always echoes how the
input was interpreted.

At startup, only `sentence-transformers/clip-ViT-B-32-multilingual-v1` is
loaded. With `CLIP_DEVICE=auto`, it uses CUDA FP16 when available and falls back
to CPU FP32 if CUDA runs out of memory. `facebook/nllb-200-distilled-600M` is
loaded lazily on the first search with translation enabled. With
`TRANSLATION_DEVICE=auto`, NLLB tries CUDA FP16 first and automatically reloads
on CPU FP32 if the GPU does not have enough memory. NLLB is released under
CC-BY-NC-4.0 and its model card describes it as a research model rather than a
production-deployment model.

Search returns 100 keyframes by default and supports up to 200. Results are
shown ten at a time in a fixed five-column by two-row gallery. `Search within
results` is grouped with the other controls under `Refine current Top K
results`. These controls filter only the current semantic Top K results; they
do not search the full dataset or call CLIP again.

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

Keep these pinned model values unchanged. The multilingual text model is aligned
with the original CLIP ViT-B/32 image encoder recorded in the release manifest,
so the existing image index remains in use:

```env
MODEL_ID=sentence-transformers/clip-ViT-B-32-multilingual-v1
MODEL_REVISION=58edf8cada9e398793dca955574a48cbb7f18be2
CLIP_DEVICE=auto
TRANSLATION_MODEL_ID=facebook/nllb-200-distilled-600M
TRANSLATION_MODEL_REVISION=f8d333a098d19b4fd9a8b18f94170487ad3f821d
TRANSLATION_DEVICE=auto
RESULTS_PER_PAGE=10
```

`CLIP_DEVICE` and `TRANSLATION_DEVICE` accept `auto`, `cpu`, or `cuda`. `auto`
uses CUDA when available and falls back to CPU after a CUDA out-of-memory error.
Set either value to `cpu` to skip the CUDA attempt, or to `cuda` to require CUDA
and surface an error instead of falling back.

`make dev` keeps the loaded runtime models when Gradio rebuilds the UI after a
source change, so hot reload does not allocate another CLIP/NLLB copy. Restart
`make dev` after changing release paths or model/device settings in `.env`.

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

## TRAKE Mode

The second tab, **TRAKE**, answers a different question type. Where the first tab
finds *one* keyframe for *one* description, TRAKE takes a **sequence of events in
time order** and finds the single video that contains all of them — plus one
keyframe per event.

Example: `athlete runs up` -> `athlete takes off` -> `athlete clears the bar` ->
`athlete lands`.

### How to use it

1. Open the **TRAKE** tab.
2. Fill in the event boxes top to bottom, in the order the events happen.
   One box shows by default; **Add event** / **Remove event** adjust between
   1 and 6.
3. Press **Search event chain**.
4. Results are ranked by video. Each row of the gallery is one video's event
   chain, left to right. The text below lists keyframe number, frame index,
   timestamp, fps, and per-event score.
5. Press **Export submission file** to download the answer file.

The picked keyframes are always in strictly increasing time order — that is
enforced by the search itself, not by filtering afterwards.

### Two things that look like bugs but are not

**Scores of 0.30-0.35 are normal.** That is the usual cosine range for
`clip-ViT-B-32-multilingual-v1`. A good match and a mediocre one differ by a few
hundredths, not by whole points. Use the "best single score" lines in the status
box to compare: if one event scores clearly lower than the others, that event's
content is probably not in the archive at all.

**Long videos ranking near the top is correct.** A 40-minute news roundup really
does contain more kinds of scenes than a 30-second clip, so it genuinely matches
a 3-event chain more often. This was tested: normalising the score by video
length (log, sqrt, or per-video z-score) made results *worse*, not better. The
ranking uses the raw sum on purpose.

### How the submission file is built

A keyframe is only sampled every ~2 seconds, but the organisers accept an answer
only if the submitted frame lands inside a window under 10 frames wide. Submitting
the keyframe's own frame index hits that window about 18% of the time.

So each answer row jitters the frames instead: for every event, a random offset
within +/-40 frames of the chosen keyframe. The first row of each video is always
the unshifted chain. Offsets are seeded from the video id, so re-running gives the
same file. Measured against the real keyframe-gap distribution and the official
R@{1,5,20,50,100} rule, this scores ~0.35 versus ~0.24 for shifting every event by
the same amount.

The 100-row budget goes to the top-ranked videos first, `SPREAD_ROWS_PER_VIDEO`
rows each — roughly the top three videos.

### Submission format is not confirmed yet

The exact format the organisers expect (separator, header row, whether frames are
numbered from 0 or 1) has **not** been confirmed. Everything format-related lives
in one block at the top of `trake.py`:

```python
SUBMISSION_DELIMITER = ", "
SUBMISSION_INCLUDE_HEADER = False
SUBMISSION_MAX_ROWS = 100
FRAME_INDEX_BASE = 0        # set to 1 if the organisers count frames from 1
```

If the rules turn out different, change these constants — no other code needs to
move.

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

- `/search_keyframes` for the legacy `auto`/`english`/`vietnamese` language
  contract
- `/search_keyframes_v2` for the boolean `translate_vietnamese` contract used
  by the current UI
- `/get_keyframe_details`
- `/search_trake` for the TRAKE tab: `(translate_vietnamese, event_1 … event_6)`,
  where unused event slots are empty strings

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

The first app start downloads multilingual CLIP. NLLB is downloaded only when
translation is used for the first time. Later runs use the local Hugging Face
cache. NLLB-600M remains a large model even with lazy loading, especially on a
CPU-only machine where the architecture intentionally retains FP32.

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
