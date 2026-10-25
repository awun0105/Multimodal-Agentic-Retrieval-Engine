"""Phase01 provider check: run each worker provider from the repository on real data.

Runs as a Kaggle script kernel (GPU T4). Clones the repository at a pinned
commit, installs `system1[worker]`, and calls `system1.providers.*` on
keyframes and audio of public Batch 1 videos. Plan:
docs/plans/active/system1-pipeline-simplification.md, Step 5.
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

REPO = "https://github.com/awun0105/Multimodal-Agentic-Retrieval-Engine.git"
COMMIT = "007882b4c3a3b438ad8e9c99cae80bd8486127bc"
OUT = Path(os.environ.get("TRIAL_OUT", "/kaggle/working"))
WORK = Path(os.environ.get("TRIAL_WORK", "/kaggle/temp/trial"))
OUT.mkdir(parents=True, exist_ok=True)
WORK.mkdir(parents=True, exist_ok=True)

RAW_REPO = "1thesudden/AIOU26_raw"
RELEASE_REPO = "1thesudden/AIOU26_release"
VIDEOS = {
    "L30_V030": "canonical_release_v001/phase01_structure/artifacts/batch_002_gpu1/L30_V030_structure.zip",
    "L25_V085": "canonical_release_v001/phase01_structure/artifacts/batch_002_gpu0/L25_V085_structure.zip",
}
SAMPLE_KEYFRAMES = 16

RESULTS: dict = {"timings_sec": {}, "errors": {}, "checks": {}, "env": {}}


def save() -> None:
    (OUT / "results.json").write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2, default=str))


def run(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(list(args), check=True, cwd=cwd)


def guarded(name: str, fn) -> None:
    print("===", name, flush=True)
    start = time.time()
    try:
        RESULTS["checks"][name] = fn()
    except Exception:
        RESULTS["errors"][name] = traceback.format_exc()[-4000:]
        print(RESULTS["errors"][name], flush=True)
    RESULTS["timings_sec"][name] = round(time.time() - start, 1)
    save()
    gc.collect()
    import torch
    torch.cuda.empty_cache()


def main() -> None:
    repo = WORK / "repo"
    run("git", "clone", "--quiet", REPO, str(repo))
    run("git", "checkout", "--quiet", COMMIT, cwd=repo)
    run(sys.executable, "-m", "pip", "install", "-q", "-e", f"{repo / 'system1'}[worker]")
    run(sys.executable, "-m", "pip", "install", "-q", "--no-deps", "vietocr==0.3.13")
    # An editable install is not visible to the already running interpreter.
    sys.path.insert(0, str(repo / "system1" / "src"))

    import pandas as pd
    import torch
    import yaml
    from huggingface_hub import hf_hub_download
    from PIL import Image

    RESULTS["env"] = {"python": sys.version, "torch": torch.__version__, "commit": COMMIT,
                      "gpus": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]}
    config = yaml.safe_load((repo / "system1" / "configs" / "worker.yaml").read_text())
    models = config["models"]

    data = {}
    for video_id, zip_path in VIDEOS.items():
        mp4 = hf_hub_download(RAW_REPO, f"canonical_raw_v001/raw_videos/{video_id}.mp4",
                              repo_type="dataset", local_dir=WORK)
        bundle = hf_hub_download(RELEASE_REPO, zip_path, repo_type="dataset", local_dir=WORK)
        with zipfile.ZipFile(bundle) as archive:
            archive.extractall(WORK / "structure")
        root = WORK / "structure" / video_id
        keyframes = pd.read_parquet(root / "keyframes.parquet").sort_values("timestamp_sec")
        paths = [root / "keyframes" / Path(ref).name for ref in keyframes["keyframe_ref"]]
        step = max(1, len(paths) // SAMPLE_KEYFRAMES)
        data[video_id] = {"mp4": Path(mp4), "sample": paths[::step][:SAMPLE_KEYFRAMES]}
    images = [Image.open(p).convert("RGB") for item in data.values() for p in item["sample"]]

    def image_embedding():
        import numpy as np
        from system1.providers.image_embedding import SiglipEmbedder

        embedder = SiglipEmbedder(models["image_embedding"])
        start = time.time()
        vectors = embedder.embed_images(images)
        seconds = (time.time() - start) / len(images)
        queries = embedder.embed_texts(["thầy giáo đứng trước bảng xanh", "tòa nhà trường đại học"])
        assert vectors.shape[0] == len(images) and vectors.shape[1] == queries.shape[1]
        assert np.isfinite(vectors).all()
        return {"shape": list(vectors.shape), "seconds_per_image": round(seconds, 4)}

    def text_embedding():
        from system1.providers.text_embedding import E5TextEmbedder

        embedder = E5TextEmbedder(models["text_embedding"])
        passages = embedder.embed_passages(["thầy giáo dạy toán cho học sinh tiểu học"] * 4)
        queries = embedder.embed_queries(["lớp học tình thương"])
        assert passages.shape[1] == queries.shape[1]
        return {"dim": int(passages.shape[1])}

    def asr():
        from system1.providers.asr import ChunkFormerAsr

        model = ChunkFormerAsr(models["asr"])
        report = {}
        for video_id, item in data.items():
            start = time.time()
            segments = model.transcribe(item["mp4"], WORK / f"{video_id}.wav")
            report[video_id] = {"seconds": round(time.time() - start, 1), "segments": len(segments),
                                "first": [s.text for s in segments[:3]]}
            assert segments, video_id
        return report

    def ocr():
        from system1.providers.ocr import EasyVietOcr, clean_ocr_lines

        reader = EasyVietOcr(models["ocr"])
        start = time.time()
        lines = [clean_ocr_lines(reader.read(image), min_chars=config["text"]["ocr_min_line_chars"])
                 for image in images]
        return {"seconds_per_image": round((time.time() - start) / len(images), 3),
                "with_text": sum(bool(x) for x in lines), "samples": [x for x in lines if x][:6]}

    def captions():
        from system1.providers.captions import QwenCaptioner

        captioner = QwenCaptioner(models["captions"])
        start = time.time()
        results = captioner.caption(images)
        seconds = (time.time() - start) / len(images)
        valid = [r.payload for r in results if r.payload]
        captioner.close()
        return {"seconds_per_image": round(seconds, 2), "valid": len(valid), "total": len(results),
                "problems": [list(r.problems) for r in results if r.problems],
                "samples": [v["caption"] for v in valid[:4]]}

    for name, fn in (("image_embedding", image_embedding), ("text_embedding", text_embedding),
                     ("asr", asr), ("ocr", ocr), ("captions", captions)):
        guarded(name, fn)
    print(json.dumps(RESULTS["checks"], ensure_ascii=False, default=str)[:6000])
    print("errors:", list(RESULTS["errors"]))


if __name__ == "__main__":
    main()
