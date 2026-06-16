from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from system1.release.types import write_json
from system1.release.writer import copy_if_exists


def write_worker_artifacts(release_dir: Path | str, *, batch_id: str, phase: str, worker_id: str = "worker_000") -> Path:
    release_path = Path(release_dir).resolve()
    manifests_dir = release_path / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    keyframes = pd.read_parquet(release_path / "tables" / "keyframes.parquet")
    videos = sorted(set(str(video_id) for video_id in keyframes["video_id"].tolist()))
    artifact_paths: list[str] = []
    for video_id in videos:
        stage_dir = release_path / "artifacts" / phase / video_id
        stage_dir.mkdir(parents=True, exist_ok=True)
        copy_if_exists(release_path / "tables" / "asr_segments.parquet", stage_dir / "asr_segments.parquet")
        copy_if_exists(release_path / "tables" / "shots.parquet", stage_dir / "shots.parquet")
        copy_if_exists(release_path / "tables" / "scenes.parquet", stage_dir / "scenes.parquet")
        copy_if_exists(release_path / "tables" / "keyframes.parquet", stage_dir / "keyframes.parquet")
        copy_if_exists(release_path / "tables" / "shot_transcript_links.parquet", stage_dir / "shot_transcript_links.parquet")
        copy_if_exists(release_path / "tables" / "scene_transcript_links.parquet", stage_dir / "scene_transcript_links.parquet")
        copy_if_exists(release_path / "tables" / "scene_summaries_initial.parquet", stage_dir / "scene_summaries_initial.parquet")
        copy_if_exists(release_path / "tables" / "embeddings_meta.parquet", stage_dir / "embeddings_meta.parquet")
        copy_if_exists(release_path / "tables" / "ocr.parquet", stage_dir / "ocr.parquet")
        copy_if_exists(release_path / "tables" / "objects.parquet", stage_dir / "objects.parquet")
        copy_if_exists(release_path / "tables" / "image_captions.parquet", stage_dir / "image_captions.parquet")
        copy_if_exists(release_path / "tables" / "shot_captions.parquet", stage_dir / "shot_captions.parquet")
        copy_if_exists(release_path / "tables" / "scene_summaries_enriched.parquet", stage_dir / "scene_summaries_enriched.parquet")
        copy_if_exists(release_path / "tables" / "text_sources.parquet", stage_dir / "text_sources.parquet")
        copy_if_exists(release_path / "media" / "keyframes" / video_id, stage_dir / "keyframes")
        copy_if_exists(release_path / "media" / "thumbnails" / video_id, stage_dir / "thumbnails")
        write_json(stage_dir / "manifest.json", {"video_id": video_id, "phase": phase, "batch_id": batch_id})
        (stage_dir / "errors.jsonl").write_text("", encoding="utf-8")
        suffix = "structure" if phase == "structure" else "features"
        archive_path = shutil.make_archive(str((release_path / "artifacts" / phase / f"{video_id}_{suffix}")), "zip", stage_dir)
        artifact_paths.append(str(Path(archive_path).relative_to(release_path)))
    report = {"worker_id": worker_id, "batch_id": batch_id, "phase": phase, "artifact_paths": artifact_paths, "status": "pass"}
    report_path = manifests_dir / f"worker_runtime_report_{phase}.json"
    write_json(report_path, report)
    return report_path
