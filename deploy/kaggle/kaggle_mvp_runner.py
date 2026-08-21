# %% [markdown]
# # Chay ung dung MVP tren Kaggle
#
# Notebook nay dung de trien khai ung dung `mvp-app` truc tiep tren Kaggle.
#
# **Yeu cau truoc khi chay (Add Input):**
# 1. Dataset DATA: `aic2025-mvp-app-data` -> mount vao `/kaggle/input/<DATASET_DATA_SLUG>/`
# 2. Dataset CODE: `mvp-app-code` -> mount vao `/kaggle/input/<DATASET_CODE_SLUG>/`

# %% [code]
# ==============================================================================
# CAU HINH
# ==============================================================================
import os
import shutil

# Thu thap HF_TOKEN tu Kaggle Secrets
try:
    from kaggle_secrets import UserSecretsClient
    os.environ["HF_TOKEN"] = UserSecretsClient().get_secret("HF_TOKEN")
    print("[INIT] Da nhan HuggingFace Token tu Kaggle Secrets!")
except Exception:
    print("[WARNING] Chua lay duoc HF_TOKEN. Co the bi treo o buoc tai model.")

DATASET_DATA_SLUG = "aic2025-mvp-app-data"
DATASET_CODE_SLUG = "mvp-app-code"
RELEASE_NAME      = "aic25-b1-v1"

APP_WORK_DIR = "/kaggle/working/mvp-app"
CACHE_ROOT   = "/kaggle/working/cache"

import torch
NUM_GPUS = torch.cuda.device_count()
print(f"[CAU HINH] GPU kha dung: {NUM_GPUS}x ({[torch.cuda.get_device_name(i) for i in range(NUM_GPUS)]})")

# %% [code]
# ==============================================================================
# BUOC 1: LAY CODE TU KAGGLE INPUT
# ==============================================================================
print("[TIEN TRINH] Tim kiem va copy code tu /kaggle/input...")

# Tim app.py hoac file .zip trong toan bo /kaggle/input
src_dir = None
zip_file_path = None
for root, dirs, files in os.walk("/kaggle/input"):
    if "app.py" in files:
        src_dir = root
        break
    for f in files:
        if f.endswith(".zip") and "mvp" in f.lower():
            zip_file_path = os.path.join(root, f)

print(f"  -> Cac thu muc trong /kaggle/input: {os.listdir('/kaggle/input')}")

# Xoa working dir cu neu co
if os.path.exists(APP_WORK_DIR):
    shutil.rmtree(APP_WORK_DIR)

if src_dir:
    shutil.copytree(src_dir, APP_WORK_DIR)
    print(f"  -> Da copy code tu {src_dir} sang {APP_WORK_DIR}")
elif zip_file_path:
    import zipfile
    os.makedirs(APP_WORK_DIR, exist_ok=True)
    with zipfile.ZipFile(zip_file_path, "r") as zf:
        zf.extractall(APP_WORK_DIR)
    # Xu ly truong hop zip co thu muc con "mvp-app"
    inner = os.path.join(APP_WORK_DIR, "mvp-app")
    if not os.path.exists(os.path.join(APP_WORK_DIR, "app.py")) and os.path.exists(os.path.join(inner, "app.py")):
        for item in os.listdir(inner):
            shutil.move(os.path.join(inner, item), APP_WORK_DIR)
        shutil.rmtree(inner)
    print(f"  -> Da giai nen code vao {APP_WORK_DIR}")
else:
    raise FileNotFoundError(
        "Khong tim thay 'app.py' hay file '.zip' nao trong /kaggle/input. "
        "Hay Add Dataset code vao Notebook truoc khi chay."
    )

os.chdir(APP_WORK_DIR)
print(f"  -> CWD hien tai: {os.getcwd()}")

# %% [code]
# ==============================================================================
# BUOC 2: CAI DAT THU VIEN
# ==============================================================================
print("[TIEN TRINH] Cai dat dependencies...")
os.system("curl -LsSf https://astral.sh/uv/install.sh | sh")
os.environ["PATH"] = f"/root/.local/bin:{os.environ.get('PATH', '')}"
os.system("uv pip install --system torch torchvision --upgrade")
os.system("uv pip install --system gradio==5.35.0 faiss-gpu python-dotenv langid sentencepiece sacremoses transformers")
print("  -> Cai dat hoan tat.")

# %% [code]
# ==============================================================================
# BUOC 3: TIM FILE DU LIEU (.blob, .sqlite, .faiss) TU KAGGLE DATASET
# ==============================================================================
import glob

print("[TIEN TRINH] Tim kiem file du lieu trong /kaggle/input...")

BLOB_PATH = None
for root, dirs, files in os.walk("/kaggle/input"):
    for f in files:
        if f.endswith(".blob"):
            BLOB_PATH = os.path.join(root, f)
            break
    if BLOB_PATH:
        break

if not BLOB_PATH or not os.path.exists(BLOB_PATH):
    raise FileNotFoundError(
        "Khong tim thay file '.blob' trong /kaggle/input. "
        "Hay Add Dataset du lieu vao Notebook truoc khi chay."
    )

print(f"  -> Tim thay blob: {BLOB_PATH}")

os.makedirs(CACHE_ROOT, exist_ok=True)
DATA_ROOT_CACHE = os.path.join(CACHE_ROOT, "data")
os.makedirs(DATA_ROOT_CACHE, exist_ok=True)

# Trich xuat .sqlite, .faiss, .json tu blob (blob la zipfile)
import zipfile as _zipfile
print("[TIEN TRINH] Trich xuat metadata tu .blob...")
extracted_files = set()
try:
    with _zipfile.ZipFile(BLOB_PATH, "r") as zf:
        for name in zf.namelist():
            base = os.path.basename(name)
            if base and (name.endswith(".sqlite") or name.endswith(".faiss") or name.endswith(".json")):
                dst = os.path.join(DATA_ROOT_CACHE, base)
                if not os.path.exists(dst):
                    print(f"  -> Giai nen: {name}")
                    with zf.open(name) as src, open(dst, "wb") as dest:
                        shutil.copyfileobj(src, dest)
                extracted_files.add(base)
except Exception as e:
    print(f"  [WARNING] Blob khong phai zip hoac loi khi giai nen: {e}")

# Copy cac file metadata nam NGOAI blob (truc tiep tren dataset)
dataset_dir = os.path.dirname(BLOB_PATH)
for root, dirs, files in os.walk(dataset_dir):
    for f in files:
        if f.endswith((".sqlite", ".faiss", ".json")) and f not in extracted_files:
            src_f = os.path.join(root, f)
            dst_f = os.path.join(DATA_ROOT_CACHE, f)
            if not os.path.exists(dst_f):
                print(f"  -> Copy metadata tu ngoai blob: {f}")
                shutil.copy2(src_f, dst_f)
            extracted_files.add(f)

# Xac dinh ten file sqlite va faiss chinh xac
sqlite_files = glob.glob(os.path.join(DATA_ROOT_CACHE, "*.sqlite"))
faiss_files  = glob.glob(os.path.join(DATA_ROOT_CACHE, "*.faiss"))

if not sqlite_files or not faiss_files:
    print(f"[WARNING] Khong tim thay .sqlite hoac .faiss trong {DATA_ROOT_CACHE}.")
    print("Chi tiet cac file da giai nen:")
    for f in os.listdir(DATA_ROOT_CACHE):
        print(f"  - {f}")
    SQLITE_NAME = "metadata.sqlite"
    FAISS_NAME  = "siglip.faiss"
else:
    SQLITE_NAME = os.path.basename(sqlite_files[0])
    FAISS_NAME  = os.path.basename(faiss_files[0])

FAISS_FILE_PATH  = os.path.join(DATA_ROOT_CACHE, FAISS_NAME)
SQLITE_FILE_PATH = os.path.join(DATA_ROOT_CACHE, SQLITE_NAME)
print(f"  -> SQLite : {SQLITE_FILE_PATH}")
print(f"  -> FAISS  : {FAISS_FILE_PATH}")

# %% [code]
# ==============================================================================
# BUOC 4: DOWNLOAD MODELS BANG GIT LFS
# ==============================================================================
print("[TIEN TRINH] Tai mo hinh bang Git LFS...")
os.system("git lfs install")

CLIP_MODEL_PATH        = os.path.join(CACHE_ROOT, "clip-vit-base-patch32")
TRANSLATION_MODEL_PATH = os.path.join(CACHE_ROOT, "opus-mt-vi-en")

if not os.path.exists(CLIP_MODEL_PATH):
    print("  -> Dang clone CLIP model...")
    os.system(f"git clone https://huggingface.co/openai/clip-vit-base-patch32 {CLIP_MODEL_PATH}")
else:
    print("  -> CLIP model da co san trong cache.")

if not os.path.exists(TRANSLATION_MODEL_PATH):
    print("  -> Dang clone Translation model...")
    os.system(f"git clone https://huggingface.co/Helsinki-NLP/opus-mt-vi-en {TRANSLATION_MODEL_PATH}")
else:
    print("  -> Translation model da co san trong cache.")

print(f"  -> CLIP path        : {CLIP_MODEL_PATH}")
print(f"  -> Translation path : {TRANSLATION_MODEL_PATH}")

# %% [code]
# ==============================================================================
# BUOC 5: TRICH XUAT FAISS -> NPY (tranh OOM khi load ca 2 cung luc)
# ==============================================================================
NPY_FILE_PATH = os.path.join(DATA_ROOT_CACHE, "embeddings.f16.npy")
if not os.path.exists(NPY_FILE_PATH) and os.path.exists(FAISS_FILE_PATH):
    print("[TIEN TRINH] Trich xuat vector tu FAISS sang Numpy...")
    import faiss
    import numpy as np
    try:
        index = faiss.read_index(FAISS_FILE_PATH)
        if hasattr(index, "reconstruct_n"):
            vectors = index.reconstruct_n(0, index.ntotal)
        elif hasattr(index, "index") and hasattr(index.index, "reconstruct_n"):
            vectors = index.index.reconstruct_n(0, index.ntotal)
        else:
            vectors = np.zeros((index.ntotal, index.d), dtype=np.float16)
        np.save(NPY_FILE_PATH, vectors.astype(np.float16))
        print(f"  -> Da tao xong file .npy: {NPY_FILE_PATH}")
    except Exception as e:
        print(f"  [WARNING] Loi trich xuat FAISS: {e}. Tao file rong!")
        import numpy as np
        np.save(NPY_FILE_PATH, np.zeros((1, 1), dtype=np.float16))
elif os.path.exists(NPY_FILE_PATH):
    print(f"  -> File .npy da co san: {NPY_FILE_PATH}")
else:
    print(f"  [WARNING] Khong tim thay file FAISS tai: {FAISS_FILE_PATH}")

# %% [code]
# ==============================================================================
# BUOC 6: GHI FILE .env CHO APP
# ==============================================================================
env_content = f"""DATA_ROOT={DATA_ROOT_CACHE}
CACHE_ROOT={DATA_ROOT_CACHE}
DATA_BLOB_PATH={BLOB_PATH}
BLOB_FILE_PATH={BLOB_PATH}
KAGGLE_MODE=1
KAGGLE_MVP=1
MODEL_ID={CLIP_MODEL_PATH}
MODEL_REVISION=main
TRANSLATION_MODEL_ID={TRANSLATION_MODEL_PATH}
TRANSLATION_MODEL_REVISION=main
FAISS_INDEX_PATH={FAISS_FILE_PATH}
SQLITE_DB_PATH={SQLITE_FILE_PATH}
FAISS_NPROBE=32
RESULTS_PER_PAGE=20
FAISS_USE_GPU=1
"""
dot_env_path = os.path.join(APP_WORK_DIR, ".env")
with open(dot_env_path, "w", encoding="utf-8") as f:
    f.write(env_content)
print(f"[TIEN TRINH] Da ghi .env vao: {dot_env_path}")
print(env_content)

# %% [code]
# ==============================================================================
# BUOC 7: PATCH CLIP.PY - THEM MultiGPUCLIPSearcher
# ==============================================================================
print("[TIEN TRINH] Patch clip.py de ho tro multi-GPU round-robin...")

MULTI_GPU_PATCH = '''

# ==============================================================================
# [KAGGLE PATCH] Multi-GPU Round-Robin CLIPSearcher
# ==============================================================================
import threading as _threading

class MultiGPUCLIPSearcher:
    """Round-robin wrapper: phan phoi concurrent requests qua nhieu GPU."""

    def __init__(self, model_id=DEFAULT_MODEL_ID, revision=DEFAULT_MODEL_REVISION):
        import torch
        num_gpus = torch.cuda.device_count()
        devices = [f"cuda:{i}" for i in range(num_gpus)] if num_gpus > 0 else ["cpu"]
        self._searchers = []
        for dev in devices:
            s = CLIPSearcher(model_id=model_id, revision=revision, device=dev)
            self._searchers.append(s)
        self._num = len(self._searchers)
        self._counter = 0
        self._lock = _threading.Lock()
        print(f"[MultiGPUCLIPSearcher] Khoi tao {self._num} GPU worker(s): {devices}")

    def _pick(self):
        with self._lock:
            idx = self._counter % self._num
            self._counter += 1
        return self._searchers[idx]

    def load(self):
        import torch
        for s in self._searchers:
            s.load()
            if s._model is not None and s.device.startswith("cuda"):
                s._model = s._model.half()
                print(f"  -> [FP16] Model tren {s.device}")

    @property
    def is_loaded(self):
        return all(s.is_loaded for s in self._searchers)

    def get_text_features(self, text):
        return self._pick().get_text_features(text)

    def get_image_features(self, image):
        return self._pick().get_image_features(image)

    def get_image_batch_features(self, images):
        return self._pick().get_image_batch_features(images)
'''

clip_py_path = os.path.join(APP_WORK_DIR, "clip.py")

# Doc noi dung hien tai de kiem tra da patch chua
with open(clip_py_path, "r", encoding="utf-8") as f:
    clip_content = f.read()

if "MultiGPUCLIPSearcher" not in clip_content:
    with open(clip_py_path, "a", encoding="utf-8") as f:
        f.write(MULTI_GPU_PATCH)
    print(f"  -> Da inject MultiGPUCLIPSearcher vao clip.py")
else:
    print(f"  -> clip.py da duoc patch truoc do, bo qua.")

# %% [code]
# ==============================================================================
# BUOC 8: PATCH APP.PY - DUNG MultiGPUCLIPSearcher VA PRE-LOAD MODELS
# ==============================================================================
print("[TIEN TRINH] Patch app.py de dung MultiGPUCLIPSearcher...")

app_py_path = os.path.join(APP_WORK_DIR, "app.py")
with open(app_py_path, "r", encoding="utf-8") as f:
    app_src = f.read()

# Chi patch neu chua patch
if "MultiGPUCLIPSearcher" not in app_src:
    app_src = app_src.replace(
        "from clip import CLIPSearcher",
        "from clip import CLIPSearcher, MultiGPUCLIPSearcher"
    )
    app_src = app_src.replace(
        "clip_searcher = CLIPSearcher(",
        "clip_searcher = MultiGPUCLIPSearcher("
    )
    app_src = app_src.replace(
        "clip_searcher = CLIPSearcher()",
        "clip_searcher = MultiGPUCLIPSearcher()"
    )

# Xoa preload patch neu da ton tai (tranh load chong startup)
if "search_mechanism.clip_searcher.load()" in app_src:
    app_src = app_src.replace(
        """search_mechanism = create_search_mechanism(runtime)
    print("[INIT] Dang tai cac models CLIP vao bo nho...")
    search_mechanism.clip_searcher.load()
    print("[INIT] Da tai xong CLIP tren cac GPU!")""",
        "search_mechanism = create_search_mechanism(runtime)"
    )

with open(app_py_path, "w", encoding="utf-8") as f:
    f.write(app_src)

print(f"  -> Da patch app.py thanh cong (lazy load mode - khoi dong nhanh).")

# %% [code]
# ==============================================================================
# BUOC 8.5: KIEM TRA FILE DU LIEU TRUOC KHI KHOI CHAY
# ==============================================================================
import os as _os

_npy   = _os.path.join(DATA_ROOT_CACHE, "embeddings.f16.npy")
_faiss = FAISS_FILE_PATH
_sql   = SQLITE_FILE_PATH

print("\n[KIEM TRA] Kich thuoc cac file du lieu:")
for _p in [_npy, _faiss, _sql]:
    if _os.path.exists(_p):
        _sz = _os.path.getsize(_p) / (1024**2)
        print(f"  {_p}: {_sz:.1f} MB")
    else:
        print(f"  [CANH BAO] Khong tim thay: {_p}")

# Kiem tra file .npy co hop le khong
import numpy as np
if _os.path.exists(_npy):
    try:
        _test = np.load(_npy, mmap_mode="r", allow_pickle=False)
        print(f"  -> embeddings.f16.npy: shape={_test.shape}, dtype={_test.dtype}")
        if _test.shape == (1, 1):
            print("  [CANH BAO] File .npy la dummy! Can trich xuat lai tu FAISS.")
    except Exception as _e:
        print(f"  [LOI] Khong the load .npy: {_e}")

# %% [code]
# ==============================================================================
# BUOC 9: KHOI CHAY GRADIO APP (TU DONG DUNG SAU 10 PHUT)
# ==============================================================================
import subprocess
import threading
import time

SESSION_TIMEOUT_MINUTES = 10
SESSION_TIMEOUT_SECONDS = SESSION_TIMEOUT_MINUTES * 60

print(f"\n[TIEN TRINH] Khoi chay ung dung MVP App (se tu dong dung sau {SESSION_TIMEOUT_MINUTES} phut)...")
print("[THONG TIN] Link public dang https://xxxx.gradio.live se xuat hien sau khi khoi dong.")

env_launch = os.environ.copy()
env_launch["GRADIO_SHARE"] = "True"
env_launch["GRADIO_DEFAULT_CONCURRENCY_LIMIT"] = str(max(NUM_GPUS, 2))
env_launch["TRANSFORMERS_OFFLINE"] = "1"
env_launch["HF_DATASETS_OFFLINE"] = "1"
env_launch["HF_HUB_OFFLINE"] = "1"

proc = subprocess.Popen(
    ["python", "-u", f"{APP_WORK_DIR}/app.py"],
    env=env_launch
)

def _shutdown_timer():
    time.sleep(SESSION_TIMEOUT_SECONDS)
    print(f"\n[AUTO-SHUTDOWN] Da het {SESSION_TIMEOUT_MINUTES} phut. Dung Gradio app...")
    proc.terminate()
    time.sleep(5)
    if proc.poll() is None:
        proc.kill()
    print("[AUTO-SHUTDOWN] Session da ket thuc.")

timer = threading.Thread(target=_shutdown_timer, daemon=True)
timer.start()

proc.wait()
print("[TIEN TRINH] App da dung.")
