"""
BƯỚC 3: KIỂM THỬ BÓC TÁCH VẬT THỂ & QUÉT CHÂN TRANG TIN TỨC.
"""

from __future__ import annotations
import io
import sys
import json
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ZIP_OBJECTS = PROJECT_ROOT / "data_sample" / "objects-aic25-b1.zip"


def test_real_objects():
    print("=" * 70)
    print("BƯỚC 3: KIỂM THỬ BÓC TÁCH VẬT THỂ & QUÉT VÙNG CHÂN TRANG (REAL DATA)")
    print("=" * 70)
    with zipfile.ZipFile(str(ZIP_OBJECTS), "r") as zf_obj:
        data = json.loads(zf_obj.read("objects/L21_V001/001.json").decode("utf-8"))
        labels = data.get("detection_class_entities", [])[:4]
        scores = data.get("detection_scores", [])[:4]
        print(f"  -> Keyframe #001: Phát hiện {len(labels)} vật thể chính:")
        for l, s in zip(labels, scores):
            print(f"     • {l} (Confidence: {float(s):.2f})")
    print("=" * 70)


if __name__ == "__main__":
    test_real_objects()
