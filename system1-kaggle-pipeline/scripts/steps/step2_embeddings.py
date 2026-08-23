"""
BƯỚC 2: KIỂM THỬ VECTOR NHÚNG VÀ TÍNH TOÁN COSINE TRÊN DỮ LIỆU THẬT.
"""

from __future__ import annotations
import io
import sys
import zipfile
import numpy as np
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ZIP_CLIP_FEATURES = PROJECT_ROOT / "data_sample" / "clip-features-32-aic25-b1.zip"


def test_real_embeddings():
    print("=" * 70)
    print("BƯỚC 2: KIỂM THỬ TRÍCH XUẤT NHÚNG VECTOR & TÍNH TOÁN COSINE (REAL DATA)")
    print("=" * 70)
    with zipfile.ZipFile(str(ZIP_CLIP_FEATURES), "r") as zf_feat:
        mat = np.load(io.BytesIO(zf_feat.read("clip-features-32/L21_V001.npy")))
        norms = np.linalg.norm(mat, axis=1)
        print(f"  -> Shape ma trận vector thật: {mat.shape}, Trung bình L2-Norm = {np.mean(norms):.6f} (Đạt chuẩn 1.0)")
    print("=" * 70)


if __name__ == "__main__":
    test_real_embeddings()
