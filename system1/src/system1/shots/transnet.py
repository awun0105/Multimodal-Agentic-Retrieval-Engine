from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from system1.artifacts.checkpoint import sha256_file


@dataclass(frozen=True)
class TransNetArtifact:
    root: Path
    source_path: Path
    weights_path: Path
    manifest: dict[str, Any]


def load_transnet_artifact(
    root: Path | str,
    *,
    expected_commit: str,
    expected_source_sha256: str,
    expected_weights_sha256: str,
) -> TransNetArtifact:
    root_path = Path(root).resolve()
    manifest_path = root_path / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "transnetv2_model_artifact_v1":
        raise ValueError("Unsupported TransNet model artifact manifest")
    if manifest.get("upstream_commit") != expected_commit:
        raise ValueError("TransNet upstream commit does not match resolved config")
    if manifest.get("conversion_verified") is not True:
        raise ValueError("TransNet conversion parity was not verified")
    source_name = str(manifest.get("source_file", ""))
    weights_name = str(manifest.get("weights_file", ""))
    if not source_name or Path(source_name).name != source_name:
        raise ValueError("Unsafe or missing TransNet source filename")
    if not weights_name or Path(weights_name).name != weights_name:
        raise ValueError("Unsafe or missing TransNet weights filename")
    source_path = root_path / source_name
    weights_path = root_path / weights_name
    if not source_path.is_file() or not weights_path.is_file():
        raise FileNotFoundError("TransNet artifact source or weights are missing")
    source_checksum = sha256_file(source_path)
    weights_checksum = sha256_file(weights_path)
    if source_checksum != manifest.get("source_sha256"):
        raise ValueError("TransNet source checksum mismatch")
    if source_checksum != expected_source_sha256:
        raise ValueError("TransNet source checksum does not match resolved config")
    if weights_checksum != manifest.get("weights_sha256"):
        raise ValueError("TransNet weights checksum does not match its manifest")
    if weights_checksum != expected_weights_sha256:
        raise ValueError("TransNet weights checksum does not match resolved config")
    return TransNetArtifact(root_path, source_path, weights_path, manifest)


def detect_shot_scenes(
    video_path: Path | str,
    *,
    artifact: TransNetArtifact,
    output_path: Path | str,
    threshold: float = 0.5,
    transition_run_boundary: str = "midpoint",
    expected_frame_count: int | None = None,
    total_attempts: int = 2,
) -> dict[str, Any]:
    """Run official PyTorch TransNet inference in an isolated subprocess."""

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.partial")
    last_error = ""
    for attempt in range(1, total_attempts + 1):
        device = "auto" if attempt == 1 else "cpu"
        command = [
            sys.executable,
            "-m",
            "system1.shots.transnet_worker",
            "--video",
            str(Path(video_path).resolve()),
            "--source",
            str(artifact.source_path),
            "--weights",
            str(artifact.weights_path),
            "--output",
            str(temporary),
            "--threshold",
            str(threshold),
            "--transition-run-boundary",
            transition_run_boundary,
            "--device",
            device,
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode == 0 and temporary.is_file():
            payload = json.loads(temporary.read_text(encoding="utf-8"))
            _validate_prediction_payload(payload, expected_frame_count=expected_frame_count)
            temporary.replace(output)
            return payload
        last_error = (result.stderr or result.stdout or "TransNet subprocess failed").strip()
        temporary.unlink(missing_ok=True)
        deterministic = any(
            marker in last_error.lower()
            for marker in ("checksum", "state_dict", "source module", "no such file", "not found")
        )
        if deterministic:
            break
    raise RuntimeError(f"TransNet V2 failed after {attempt} attempt(s): {last_error}")


def scenes_to_shot_rows(
    *,
    video_id: str,
    scenes_inclusive: list[list[int]],
    frame_timeline: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not frame_timeline:
        raise ValueError("Decoded frame timeline is required for shot construction")
    by_frame = {int(row["frame_id"]): row for row in frame_timeline}
    rows: list[dict[str, Any]] = []
    for shot_index, scene in enumerate(scenes_inclusive):
        if len(scene) != 2:
            raise ValueError(f"Invalid TransNet scene range: {scene}")
        start_frame, inclusive_end = map(int, scene)
        end_frame = inclusive_end + 1
        if start_frame not in by_frame or inclusive_end not in by_frame:
            raise ValueError(f"TransNet scene is outside decoded frame timeline: {scene}")
        start_time = float(by_frame[start_frame]["pts_time"])
        end_row = by_frame[inclusive_end]
        duration = end_row.get("duration_time")
        if duration is None:
            if end_frame in by_frame:
                end_time = float(by_frame[end_frame]["pts_time"])
            else:
                raise ValueError("Final decoded frame has no duration_time")
        else:
            end_time = float(end_row["pts_time"]) + float(duration)
        rows.append(
            {
                "shot_id": f"{video_id}_SH{shot_index:05d}",
                "video_id": video_id,
                "scene_id": None,
                "shot_index": shot_index,
                "start_frame": start_frame,
                "end_frame": end_frame,
                "start_sec": start_time,
                "end_sec": end_time,
                "duration_sec": max(0.0, end_time - start_time),
                "frame_count": end_frame - start_frame,
                "boundary_convention": "[start_frame, end_frame)",
                "detection_method": "transnet_v2",
                "status": "transnet_v2_no_cut" if len(scenes_inclusive) == 1 else "pass",
            }
        )
    _validate_shot_partition(rows, frame_count=len(frame_timeline))
    return rows


def _validate_prediction_payload(
    payload: dict[str, Any], *, expected_frame_count: int | None
) -> None:
    frame_count = payload.get("frame_count")
    scenes = payload.get("scenes_inclusive")
    if not isinstance(frame_count, int) or frame_count < 1:
        raise ValueError("TransNet returned invalid frame_count")
    if expected_frame_count is not None and frame_count != expected_frame_count:
        raise ValueError(
            f"TransNet decoded frame count differs from Phase00 timeline: "
            f"{frame_count} != {expected_frame_count}"
        )
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("TransNet returned no scene partition")
    expected_start = 0
    for scene in scenes:
        if not isinstance(scene, list) or len(scene) != 2:
            raise ValueError("TransNet returned an invalid scene range")
        start, end = scene
        if not isinstance(start, int) or not isinstance(end, int) or start != expected_start or end < start:
            raise ValueError("TransNet scene ranges are not a contiguous partition")
        expected_start = end + 1
    if expected_start != frame_count:
        raise ValueError("TransNet scene ranges do not cover all decoded frames")


def _validate_shot_partition(rows: list[dict[str, Any]], *, frame_count: int) -> None:
    expected_start = 0
    for row in rows:
        if row["start_frame"] != expected_start or row["end_frame"] <= row["start_frame"]:
            raise ValueError("Shot rows do not form a contiguous decoded-frame partition")
        expected_start = int(row["end_frame"])
    if expected_start != frame_count:
        raise ValueError("Shot rows do not cover the Phase00 decoded frame timeline")
