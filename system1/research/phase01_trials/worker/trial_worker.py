"""Run the per-video worker end to end with real models on Kaggle.

Clones the repository at a pinned commit, builds every provider, and calls
`system1.worker.video.process_video` on public Batch 1 videos. Captions use the
second T4; the other models share the first. Plan:
docs/plans/active/system1-pipeline-simplification.md, Step 5.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

REPO = "https://github.com/awun0105/Multimodal-Agentic-Retrieval-Engine.git"
COMMIT = "17a18914d2b9cdfaa3defc85a320a967fd7df9f3"
OUT = Path(os.environ.get("TRIAL_OUT", "/kaggle/working"))
WORK = Path(os.environ.get("TRIAL_WORK", "/kaggle/temp/trial"))
RAW_REPO = "1thesudden/AIOU26_raw"
VIDEO_IDS = ["L30_V030", "L25_V085"]

RESULTS: dict = {"videos": {}, "errors": {}, "env": {}, "model_load_sec": {}}


def save() -> None:
    (OUT / "results.json").write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2, default=str))


def run(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(list(args), check=True, cwd=cwd)


def timed(name: str, factory):
    start = time.time()
    value = factory()
    RESULTS["model_load_sec"][name] = round(time.time() - start, 1)
    save()
    return value


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    repo = WORK / "repo"
    run("git", "clone", "--quiet", REPO, str(repo))
    run("git", "checkout", "--quiet", COMMIT, cwd=repo)
    run(sys.executable, "-m", "pip", "install", "-q", "-e", f"{repo / 'system1'}[worker]")
    run(sys.executable, "-m", "pip", "install", "-q", "--no-deps", "vietocr==0.3.13")
    sys.path.insert(0, str(repo / "system1" / "src"))

    import pandas as pd
    import torch
    import yaml
    from huggingface_hub import hf_hub_download

    from system1.providers.asr import ChunkFormerAsr
    from system1.providers.captions import QwenCaptioner
    from system1.providers.image_embedding import SiglipEmbedder
    from system1.providers.ocr import EasyVietOcr
    from system1.providers.cuts import TransNetCuts
    from system1.providers.text_embedding import E5TextEmbedder
    from system1.worker.video import VideoInput, WorkerModels, process_video

    RESULTS["env"] = {"python": sys.version, "torch": torch.__version__, "commit": COMMIT,
                      "gpus": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]}
    config = yaml.safe_load((repo / "system1" / "configs" / "worker.yaml").read_text())
    models_config = config["models"]
    models = WorkerModels(
        cuts=timed("cuts", lambda: TransNetCuts(models_config["shot_detection"], config["model_artifacts"],
                                                   WORK / "model_artifacts")),
        image=timed("image", lambda: SiglipEmbedder(models_config["image_embedding"], device="cuda:0")),
        asr=timed("asr", lambda: ChunkFormerAsr(models_config["asr"], device="cuda:0")),
        ocr=timed("ocr", lambda: EasyVietOcr(models_config["ocr"], device="cuda:0")),
        captioner=timed("captions", lambda: QwenCaptioner(models_config["captions"], device="cuda:1")),
        text=timed("text", lambda: E5TextEmbedder(models_config["text_embedding"], device="cuda:0")),
    )

    for video_id in VIDEO_IDS:
        try:
            mp4 = hf_hub_download(RAW_REPO, f"canonical_raw_v001/raw_videos/{video_id}.mp4",
                                  repo_type="dataset", local_dir=WORK)
            timeline = hf_hub_download(RAW_REPO, f"canonical_raw_v001/frame_timeline/{video_id}.parquet",
                                       repo_type="dataset", local_dir=WORK)
            rows = pd.read_parquet(timeline).sort_values("frame_id").to_dict("records")
            video = VideoInput(video_id=video_id, video_path=Path(mp4), timeline_rows=rows)
            start = time.time()
            zip_path = process_video(video, config=config, models=models, work_root=OUT / "work",
                                     batch_id="trial", worker_id="kaggle")
            manifest = json.loads((OUT / "work" / video_id / "package" / "manifest.json").read_text())
            RESULTS["videos"][video_id] = {
                "seconds": round(time.time() - start, 1),
                "duration_sec": round(float(rows[-1]["pts_time"]), 1),
                "zip_mb": round(zip_path.stat().st_size / 1e6, 1),
                "stages": manifest["stages"],
            }
        except Exception:
            RESULTS["errors"][video_id] = traceback.format_exc()[-4000:]
            print(RESULTS["errors"][video_id], flush=True)
        save()
    print(json.dumps(RESULTS["videos"], ensure_ascii=False, default=str)[:6000])
    print("errors:", list(RESULTS["errors"]))


if __name__ == "__main__":
    main()
