from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd
from jsonschema import validate

PHASE01_TABLES = (
    "shots",
    "keyframes",
    "asr_segments",
    "ocr",
    "shot_captions",
    "shot_transcript_links",
    "scenes",
    "scene_transcript_links",
    "scene_summaries",
)


def validate_rows(table_name: str, rows: Iterable[Mapping[str, Any]]) -> None:
    schema = _load_schema(table_name)
    for index, row in enumerate(rows):
        try:
            validate(_json_value(dict(row)), schema)
        except Exception as exc:
            raise ValueError(f"{table_name} row {index} violates canonical schema: {exc}") from exc


def validate_phase01_package(artifact_dir: Path) -> None:
    tables = {
        name: pd.read_parquet(artifact_dir / f"{name}.parquet")
        for name in PHASE01_TABLES
    }
    for name, frame in tables.items():
        validate_rows(name, frame.to_dict("records"))

    shots = tables["shots"].sort_values("shot_index")
    keyframes = tables["keyframes"]
    ocr = tables["ocr"]
    captions = tables["shot_captions"]
    scenes = tables["scenes"].sort_values("scene_index")
    summaries = tables["scene_summaries"]
    asr = tables["asr_segments"]
    shot_links = tables["shot_transcript_links"]
    scene_links = tables["scene_transcript_links"]

    video_ids = {
        str(value)
        for frame in tables.values()
        if "video_id" in frame.columns
        for value in frame["video_id"].dropna().tolist()
    }
    if len(video_ids) != 1 or next(iter(video_ids)) != artifact_dir.name:
        raise ValueError("Every Phase01 table must match the artifact video_id")
    video_id = next(iter(video_ids))
    _validate_scene_partition_quality_report(
        artifact_dir,
        video_id=video_id,
        shot_count=len(shots),
        scene_count=len(scenes),
    )
    _validate_contiguous_ranges(shots, "shot")
    _validate_contiguous_ranges(scenes, "scene")
    if list(shots["shot_index"].astype(int)) != list(range(len(shots))):
        raise ValueError("shot_index must be contiguous and zero-based")
    if list(scenes["scene_index"].astype(int)) != list(range(len(scenes))):
        raise ValueError("scene_index must be contiguous and zero-based")
    if list(shots["shot_id"].astype(str)) != [
        f"{video_id}_SH{index:05d}" for index in range(len(shots))
    ]:
        raise ValueError("shot_id does not match canonical shot order")
    if list(scenes["scene_id"].astype(str)) != [
        f"{video_id}_SC{index:05d}" for index in range(len(scenes))
    ]:
        raise ValueError("scene_id does not match canonical scene order")
    expected_representatives = {str(value): 1 for value in shots["shot_id"]}
    actual_representatives = (
        keyframes[keyframes["is_representative"]]
        .groupby("shot_id")
        .size()
        .to_dict()
    )
    if actual_representatives != expected_representatives:
        raise ValueError("Every shot must have exactly one representative keyframe")
    supplemental_representatives = keyframes[
        (keyframes["keyframe_role"] == "supplemental")
        & keyframes["is_representative"]
    ]
    if not supplemental_representatives.empty:
        raise ValueError("Supplemental keyframes cannot be representative")
    expected_keyframe_ids = {
        f"{row.video_id}:{int(row.frame_id)}" for row in keyframes.itertuples(index=False)
    }
    if set(keyframes["keyframe_id"].astype(str)) != expected_keyframe_ids:
        raise ValueError("keyframe_id must equal {video_id}:{frame_id}")
    if keyframes["keyframe_id"].astype(str).duplicated().any():
        raise ValueError("keyframe_id must be unique")
    if not set(ocr["keyframe_id"].astype(str)).issubset(expected_keyframe_ids):
        raise ValueError("ocr.keyframe_id must reference canonical keyframes")
    shot_ids = set(shots["shot_id"].astype(str))
    scene_ids = set(scenes["scene_id"].astype(str))
    if set(captions["shot_id"].astype(str)) != shot_ids or len(captions) != len(shots):
        raise ValueError("Every shot must have exactly one caption")
    if set(summaries["scene_id"].astype(str)) != scene_ids or len(summaries) != len(scenes):
        raise ValueError("Every scene must have exactly one summary")
    if shots["scene_id"].isna().any() or keyframes["scene_id"].isna().any():
        raise ValueError("Scene mappings are incomplete")
    _validate_scene_membership(shots, scenes, keyframes)
    _validate_caption_representatives(captions, keyframes)
    _validate_keyframe_media(artifact_dir, keyframes, video_id)
    asr_ids = set(asr["asr_segment_id"].astype(str))
    _validate_links(shot_links, "shot_id", shot_ids, asr_ids)
    _validate_links(scene_links, "scene_id", scene_ids, asr_ids)


def _validate_contiguous_ranges(frame: pd.DataFrame, label: str) -> None:
    previous_end: int | None = 0
    for row in frame.to_dict("records"):
        start = int(row["start_frame"])
        end = int(row["end_frame"])
        if end <= start:
            raise ValueError(f"{label} range must be non-empty")
        if previous_end is not None and start != previous_end:
            raise ValueError(f"{label} ranges are not contiguous")
        previous_end = end


def _validate_scene_membership(
    shots: pd.DataFrame, scenes: pd.DataFrame, keyframes: pd.DataFrame
) -> None:
    ordered_shots = shots.sort_values("shot_index").to_dict("records")
    shot_positions = {
        str(row["shot_id"]): index for index, row in enumerate(ordered_shots)
    }
    expected_scene_by_shot: dict[str, str] = {}
    for scene in scenes.sort_values("scene_index").to_dict("records"):
        start_id = str(scene["start_shot_id"])
        end_id = str(scene["end_shot_id"])
        if start_id not in shot_positions or end_id not in shot_positions:
            raise ValueError("Scene references an unknown shot boundary")
        start = shot_positions[start_id]
        end = shot_positions[end_id]
        if end < start:
            raise ValueError("Scene shot range is reversed")
        members = ordered_shots[start : end + 1]
        if int(scene["shot_count"]) != len(members):
            raise ValueError("Scene shot_count does not match its shot range")
        if (
            int(scene["start_frame"]) != int(members[0]["start_frame"])
            or int(scene["end_frame"]) != int(members[-1]["end_frame"])
        ):
            raise ValueError("Scene frame range does not match its shots")
        for shot in members:
            shot_id = str(shot["shot_id"])
            if shot_id in expected_scene_by_shot:
                raise ValueError("A shot belongs to more than one scene")
            expected_scene_by_shot[shot_id] = str(scene["scene_id"])
    if set(expected_scene_by_shot) != set(shot_positions):
        raise ValueError("Scene partition does not cover every shot")
    actual_scene_by_shot = {
        str(row["shot_id"]): str(row["scene_id"])
        for row in shots.to_dict("records")
    }
    if actual_scene_by_shot != expected_scene_by_shot:
        raise ValueError("shots.scene_id disagrees with the scene partition")
    shot_rows = {str(row["shot_id"]): row for row in ordered_shots}
    for row in keyframes.to_dict("records"):
        shot_id = str(row["shot_id"])
        if shot_id not in shot_rows:
            raise ValueError("Keyframe references an unknown shot")
        if str(row["scene_id"]) != expected_scene_by_shot[shot_id]:
            raise ValueError("keyframes.scene_id disagrees with its shot")
        shot = shot_rows[shot_id]
        if not int(shot["start_frame"]) <= int(row["frame_id"]) < int(shot["end_frame"]):
            raise ValueError("Keyframe frame_id lies outside its shot")
    actual_keyframe_counts = keyframes.groupby("scene_id").size().to_dict()
    for scene in scenes.to_dict("records"):
        if int(scene["keyframe_count"]) != int(
            actual_keyframe_counts.get(scene["scene_id"], 0)
        ):
            raise ValueError("Scene keyframe_count does not match keyframes")


def _validate_caption_representatives(
    captions: pd.DataFrame, keyframes: pd.DataFrame
) -> None:
    representatives = {
        str(row["shot_id"]): row
        for row in keyframes[keyframes["is_representative"]].to_dict("records")
    }
    for caption in captions.to_dict("records"):
        representative = representatives[str(caption["shot_id"])]
        if str(caption["representative_keyframe_id"]) != str(
            representative["keyframe_id"]
        ):
            raise ValueError("Shot caption references the wrong representative keyframe")
        if not math.isclose(
            float(caption["representative_timestamp_sec"]),
            float(representative["timestamp_sec"]),
            abs_tol=1e-6,
        ):
            raise ValueError("Shot caption representative timestamp is inconsistent")


def _validate_keyframe_media(
    artifact_dir: Path, keyframes: pd.DataFrame, video_id: str
) -> None:
    for row in keyframes.to_dict("records"):
        keyframe_name = Path(str(row["keyframe_ref"])).name
        thumbnail_name = Path(str(row["thumbnail_ref"])).name
        if str(row["keyframe_ref"]) != f"media://keyframes/{video_id}/{keyframe_name}":
            raise ValueError("keyframe_ref does not match canonical media identity")
        if str(row["thumbnail_ref"]) != f"media://thumbnails/{video_id}/{thumbnail_name}":
            raise ValueError("thumbnail_ref does not match canonical media identity")
        if not (artifact_dir / "keyframes" / keyframe_name).is_file():
            raise FileNotFoundError(f"Missing packaged keyframe: {keyframe_name}")
        if not (artifact_dir / "thumbnails" / thumbnail_name).is_file():
            raise FileNotFoundError(f"Missing packaged thumbnail: {thumbnail_name}")


def _validate_links(
    frame: pd.DataFrame,
    entity_column: str,
    entity_ids: set[Any],
    segment_ids: set[Any],
) -> None:
    if frame.empty:
        return
    if not set(frame[entity_column]).issubset(entity_ids):
        raise ValueError(f"{entity_column} link contains an unknown entity")
    if not set(frame["asr_segment_id"]).issubset(segment_ids):
        raise ValueError("Transcript link contains an unknown ASR segment")
    if ((frame["coverage"] < 0) | (frame["coverage"] > 1)).any():
        raise ValueError("Transcript link coverage must be in [0, 1]")


def _validate_scene_partition_quality_report(
    artifact_dir: Path,
    *,
    video_id: str,
    shot_count: int,
    scene_count: int,
) -> None:
    path = artifact_dir / "diagnostics" / "scene_partition_quality.json"
    if not path.is_file():
        raise FileNotFoundError("Missing scene partition quality report")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "scene_partition_quality_v1":
        raise ValueError("Unsupported scene partition quality report schema")
    if str(payload.get("video_id")) != video_id:
        raise ValueError("Scene partition quality report video_id mismatch")
    if payload.get("status") not in {"pass", "pass_after_review"}:
        raise ValueError("Scene partition quality report is not passing")
    final = payload.get("final")
    if not isinstance(final, Mapping):
        raise TypeError("Scene partition quality report has no final metrics")
    if bool(final.get("suspicious", True)):
        raise ValueError("Scene partition quality report remains suspicious")
    if int(final.get("shot_count", -1)) != shot_count:
        raise ValueError("Scene partition quality shot_count mismatch")
    if int(final.get("scene_count", -1)) != scene_count:
        raise ValueError("Scene partition quality scene_count mismatch")


def _load_schema(table_name: str) -> dict[str, Any]:
    path = Path(__file__).resolve().parents[3] / "schemas" / f"{table_name}.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes)):
        converted = value.tolist()
        if isinstance(converted, list):
            return [_json_value(item) for item in converted]
        value = converted
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    item = getattr(value, "item", None)
    if callable(item):
        value = item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value
