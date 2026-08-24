"""
====================================================================================================
SERVICES - CONFIGURATION & RESOURCE PATHS (config.py)
====================================================================================================

1. MỤC TIÊU VÀ VAI TRÒ:
   - Module này tập trung toàn bộ cấu hình môi trường, hằng số hệ thống, đường dẫn tệp tài nguyên,
     dataset, zip cache, SQLite DB, FAISS Index và danh sách 10 video mục tiêu (5 video đầu + 5 video cuối).
   - Đảm bảo toàn bộ các tầng Services, Components và Tests sử dụng chung một Single Source of Truth (SSOT).

2. CÁC TÀI NGUYÊN QUẢN LÝ:
   - `PROJECT_ROOT`: Thư mục gốc của repository.
   - `SRC_DIR`: Thư mục mã nguồn `system1-kaggle-pipeline/src` phục vụ nạp các engine xử lý.
   - `MODELS_DIR`: Thư mục mô hình AI tập trung (`models/`).
   - `TARGET_BENCHMARK_VIDEOS`: Danh sách 10 video đối soát chuẩn cuộc thi AIC 2026.
   - Các đường dẫn xuất bản: `RAW_VIDEO_DIR`, `KEYFRAMES_OUT_DIR`, `THUMBS_OUT_DIR`, `BENCHMARK_DIR`.
====================================================================================================
"""

from __future__ import annotations
import sys
from pathlib import Path

# --------------------------------------------------------------------------------------------------
# KHỐI 1: CẤU HÌNH UTF-8 CONSOLE
# --------------------------------------------------------------------------------------------------
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# --------------------------------------------------------------------------------------------------
# KHỐI 2: ĐỊNH VỊ THƯ MỤC GỐC VÀ SYS.PATH
# --------------------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SRC_DIR = PROJECT_ROOT / "system1-kaggle-pipeline" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

MODELS_DIR = PROJECT_ROOT / "models"
if str(MODELS_DIR) not in sys.path:
    sys.path.insert(0, str(MODELS_DIR))

# --------------------------------------------------------------------------------------------------
# KHỐI 3: ĐƯỜNG DẪN DỮ LIỆU DATASET & TỆP NÉN ZIP
# --------------------------------------------------------------------------------------------------
DATASET_DIR = PROJECT_ROOT / "monolith-mvp-app" / "mvp-app" / "data" / "aic25-b1-v1"
SQLITE_DB_PATH = DATASET_DIR / "metadata" / "runtime.sqlite"
FAISS_INDEX_PATH = DATASET_DIR / "index" / "keyframes.faiss"

ZIP_KEYFRAMES_L21 = PROJECT_ROOT / "data_sample" / "Keyframes_L21.zip"
ZIP_VIDEOS = PROJECT_ROOT / "data_sample" / "Videos_L21_a.zip"
ZIP_MAP_KEYFRAMES = PROJECT_ROOT / "data_sample" / "map-keyframes-aic25-b1.zip"
ZIP_MEDIA_INFO = PROJECT_ROOT / "data_sample" / "media-info-aic25-b1.zip"
ZIP_OBJECTS = PROJECT_ROOT / "data_sample" / "objects-aic25-b1.zip"

# --------------------------------------------------------------------------------------------------
# KHỐI 4: ĐƯỜNG DẪN XUẤT BẢN THỬ NGHIỆM & BENCHMARK
# --------------------------------------------------------------------------------------------------
BENCHMARK_DIR = PROJECT_ROOT / "system1-kaggle-pipeline" / "test_output" / "side_by_side_benchmark"
BENCHMARK_JSON = BENCHMARK_DIR / "comparison_data.json"
BENCHMARK_CSV = BENCHMARK_DIR / "benchmark_summary.csv"

OUTPUT_DIR = PROJECT_ROOT / "system1-kaggle-pipeline" / "test_output"
RAW_VIDEO_DIR = OUTPUT_DIR / "raw_video"
KEYFRAMES_OUT_DIR = OUTPUT_DIR / "extracted_keyframes"
THUMBS_OUT_DIR = OUTPUT_DIR / "extracted_thumbnails"

RAW_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
KEYFRAMES_OUT_DIR.mkdir(parents=True, exist_ok=True)
THUMBS_OUT_DIR.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------------------------------
# KHỐI 5: DANH SÁCH 10 VIDEO ĐỐI SOÁT MỤC TIÊU (5 ĐẦU + 5 CUỐI)
# --------------------------------------------------------------------------------------------------
TARGET_BENCHMARK_VIDEOS = [
    "L21_V001", "L21_V002", "L21_V003", "L21_V005", "L21_V006",
    "L21_V027", "L21_V028", "L21_V029", "L21_V030", "L21_V031"
]
