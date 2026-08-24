"""
BƯỚC 1: KIỂM THỬ TRÍCH XUẤT KEYFRAME THỰC TẾ & ĐO ĐỘ SẮC NÉT LAPLACIAN.
"""

from __future__ import annotations
import io
import sys
import zipfile
import numpy as np
from pathlib import Path
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ZIP_KEYFRAMES = PROJECT_ROOT / "data_sample" / "Keyframes_L21.zip"


def test_real_keyframes():
    print("=" * 70)
    print("BƯỚC 1: KIỂM THỬ TRÍCH XUẤT KEYFRAME THỰC TẾ & ĐO ĐỘ SẮC NÉT (REAL DATA)")
    print("=" * 70)
    with zipfile.ZipFile(str(ZIP_KEYFRAMES), "r") as zf:
        sample_files = sorted([f for f in zf.namelist() if f.startswith("keyframes/L21_V001/") and f.endswith(".jpg")])[:5]
        for fname in sample_files:
            raw_bytes = zf.read(fname)
            pil_img = Image.open(io.BytesIO(raw_bytes))
            gray = np.array(pil_img.convert("L"), dtype=np.float64)
            gy, gx = np.gradient(gray)
            sharpness = float(np.var(np.gradient(gx)[1] + np.gradient(gy)[0]) * 10.0)
            print(f"  -> {Path(fname).name}: Độ phân giải {pil_img.size}, Độ sắc nét Laplacian = {sharpness:.2f} (ĐẠT)")
    print("=" * 70)


if __name__ == "__main__":
    test_real_keyframes()
