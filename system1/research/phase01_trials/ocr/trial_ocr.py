"""Phase01 model trial: Vietnamese OCR with separate text detection and recognition.

Runs as a Kaggle script kernel (GPU T4). Variants:
  A  PaddleOCR PP-OCRv5 detection (CPU) + VietOCR recognition (GPU)
  B  EasyOCR detection (GPU) + VietOCR recognition (GPU)
  C  EasyOCR detection + EasyOCR Vietnamese recognition (GPU)
Reads public Hugging Face data only. Plan:
docs/plans/active/system1-pipeline-simplification.md, Step 3.
"""

from __future__ import annotations

import gc
import json
import os
import subprocess
import sys
import time
import traceback
import zipfile
from pathlib import Path

OUT = Path(os.environ.get("TRIAL_OUT", "/kaggle/working"))
WORK = Path(os.environ.get("TRIAL_WORK", "/kaggle/temp/trial"))
OUT.mkdir(parents=True, exist_ok=True)
WORK.mkdir(parents=True, exist_ok=True)

RELEASE_REPO = "1thesudden/AIOU26_release"
VIDEOS = {
    "L30_V030": "canonical_release_v001/phase01_structure/artifacts/batch_002_gpu1/L30_V030_structure.zip",
    "L25_V085": "canonical_release_v001/phase01_structure/artifacts/batch_002_gpu0/L25_V085_structure.zip",
}
PAD = 4

RESULTS: dict = {"timings_sec": {}, "errors": {}, "metrics": {}, "env": {}}


def save() -> None:
    (OUT / "results.json").write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2))


def pip(*packages: str) -> None:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *packages], check=True)


def keyframe_paths() -> list[Path]:
    import pandas as pd
    from huggingface_hub import hf_hub_download

    paths = []
    for video_id, zip_path in VIDEOS.items():
        bundle = hf_hub_download(RELEASE_REPO, zip_path, repo_type="dataset", local_dir=WORK)
        with zipfile.ZipFile(bundle) as archive:
            archive.extractall(WORK / "structure")
        root = WORK / "structure" / video_id
        keyframes = pd.read_parquet(root / "keyframes.parquet").sort_values("timestamp_sec")
        paths += [root / "keyframes" / Path(ref).name for ref in keyframes["keyframe_ref"]]
    return paths


def crops(image, boxes):
    """Axis-aligned crops in reading order (top to bottom, then left to right)."""

    width, height = image.size
    rects = []
    for box in boxes:
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
        rects.append((max(0, min(xs) - PAD), max(0, min(ys) - PAD),
                      min(width, max(xs) + PAD), min(height, max(ys) + PAD)))
    rects = [r for r in rects if r[2] - r[0] >= 8 and r[3] - r[1] >= 8]
    rects.sort(key=lambda r: (round(r[1] / 12), r[0]))
    return [image.crop(tuple(int(v) for v in rect)) for rect in rects]


def vietocr_predictor():
    from vietocr.tool.config import Cfg
    from vietocr.tool.predictor import Predictor

    config = Cfg.load_config_from_name("vgg_transformer")
    config["device"] = "cuda:0"
    config["predictor"]["beamsearch"] = False
    return Predictor(config)


def recognize(predictor, images) -> list[str]:
    if not images:
        return []
    return [text.strip() for text in predictor.predict_batch(images)]


def run_variant(name: str, detect, recognizer, paths: list[Path]) -> None:
    from PIL import Image

    print("===", name, flush=True)
    rows, det_seconds, rec_seconds = [], 0.0, 0.0
    for path in paths:
        image = Image.open(path).convert("RGB")
        start = time.time()
        boxes = detect(path, image)
        det_seconds += time.time() - start
        start = time.time()
        lines = recognizer(path, image, boxes)
        rec_seconds += time.time() - start
        rows.append({"keyframe": path.name, "lines": [line for line in lines if line]})
    RESULTS["metrics"][name] = {
        "detect_seconds_per_keyframe": round(det_seconds / len(paths), 3),
        "recognize_seconds_per_keyframe": round(rec_seconds / len(paths), 3),
        "keyframes_with_text": sum(bool(r["lines"]) for r in rows),
        "keyframes": len(rows),
    }
    (OUT / f"ocr_{name}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    print(name, RESULTS["metrics"][name], flush=True)


def guarded(name: str, fn) -> None:
    start = time.time()
    try:
        fn()
    except Exception:
        RESULTS["errors"][name] = traceback.format_exc()[-4000:]
        print(RESULTS["errors"][name], flush=True)
    RESULTS["timings_sec"][name] = round(time.time() - start, 1)
    save()
    gc.collect()


def main() -> None:
    # vietocr pins an old Pillow that does not build on Python 3.13; its
    # predictor only needs torch, einops, gdown, and prefetch_generator.
    pip("--no-deps", "vietocr")
    for package in ("einops", "gdown", "prefetch_generator", "easyocr", "paddlepaddle", "paddleocr",
                    "huggingface_hub"):
        try:
            pip(package)
        except subprocess.CalledProcessError:
            RESULTS["errors"][f"pip:{package}"] = "install failed"
    import torch
    RESULTS["env"] = {"python": sys.version, "torch": torch.__version__,
                      "gpus": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]}
    paths = keyframe_paths()
    predictor = vietocr_predictor()

    def variant_a() -> None:
        from paddleocr import TextDetection

        try:
            detector = TextDetection(model_name="PP-OCRv5_mobile_det", enable_mkldnn=False)
        except TypeError:
            detector = TextDetection(model_name="PP-OCRv5_mobile_det")

        def detect(path, _image):
            return [poly.tolist() for result in detector.predict(str(path)) for poly in result["dt_polys"]]

        run_variant("A_paddle_det_vietocr", detect,
                    lambda _p, image, boxes: recognize(predictor, crops(image, boxes)), paths)

    import easyocr
    reader = easyocr.Reader(["vi"], gpu=True)

    def easy_detect(_path, image):
        import numpy as np

        horizontal, free = reader.detect(np.asarray(image))
        boxes = [[[x0, y0], [x1, y0], [x1, y1], [x0, y1]] for x0, x1, y0, y1 in horizontal[0]]
        return boxes + [list(polygon) for polygon in free[0]]

    def variant_b() -> None:
        run_variant("B_easyocr_det_vietocr", easy_detect,
                    lambda _p, image, boxes: recognize(predictor, crops(image, boxes)), paths)

    def variant_c() -> None:
        run_variant("C_easyocr", lambda _p, _i: [],
                    lambda path, _i, _b: [t for t in reader.readtext(str(path), detail=0)], paths)

    for name, fn in (("B", variant_b), ("C", variant_c), ("A", variant_a)):
        guarded(name, fn)
    print(json.dumps(RESULTS["metrics"], ensure_ascii=False))
    print("errors:", list(RESULTS["errors"]))


if __name__ == "__main__":
    main()
