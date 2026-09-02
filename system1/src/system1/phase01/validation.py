from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from itertools import pairwise
from pathlib import Path
from typing import Any

import pandas as pd
from jsonschema import validate

from system1.asr.links import assign_words_to_intervals
from system1.asr.quality import normalize_for_comparison

PHASE01_TABLES = (
    "shots",
    "keyframes",
    "asr_segments",
    "asr_words",
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
    asr_words = tables["asr_words"]
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
    _validate_asr_words(asr, asr_words, video_id=video_id)
    _validate_links(
        shot_links,
        "shot_id",
        shot_ids,
        asr,
        shots,
        asr_words,
    )
    _validate_links(
        scene_links,
        "scene_id",
        scene_ids,
        asr,
        scenes,
        asr_words,
    )
    _validate_global_word_attribution(shots, asr_words, entity_column="shot_id")
    _validate_global_word_attribution(scenes, asr_words, entity_column="scene_id")


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
    segments: pd.DataFrame,
    entities: pd.DataFrame,
    words: pd.DataFrame,
) -> None:
    segment_ids = set(segments["asr_segment_id"].astype(str))
    if frame.empty:
        if not segments.empty:
            raise ValueError(f"{entity_column} links are empty for non-empty ASR")
        return
    if not set(frame[entity_column].astype(str)).issubset(entity_ids):
        raise ValueError(f"{entity_column} link contains an unknown entity")
    if not set(frame["asr_segment_id"].astype(str)).issubset(segment_ids):
        raise ValueError("Transcript link contains an unknown ASR segment")
    for column in ("segment_coverage", "entity_coverage", "coverage"):
        if ((frame[column] <= 0) | (frame[column] > 1)).any():
            raise ValueError(f"Transcript link {column} must be in (0, 1]")
    if (frame["assigned_word_count"] < 0).any():
        raise ValueError("Transcript link assigned_word_count must be non-negative")

    segment_by_id = {
        str(row["asr_segment_id"]): row for row in segments.to_dict("records")
    }
    entity_by_id = {
        str(row[entity_column]): row for row in entities.to_dict("records")
    }
    assignments = assign_words_to_intervals(
        entities.to_dict("records"),
        words.to_dict("records"),
        entity_id_field=entity_column,
    )
    assigned_counts: dict[tuple[str, str], int] = {}
    for entity_id, assigned_words in assignments.items():
        for word in assigned_words:
            key = (entity_id, str(word["asr_segment_id"]))
            assigned_counts[key] = assigned_counts.get(key, 0) + 1

    expected_pairs: set[tuple[str, str]] = set()
    seen_pairs: set[tuple[str, str]] = set()
    for entity_id, entity in entity_by_id.items():
        for segment_id, segment in segment_by_id.items():
            if min(float(entity["end_sec"]), float(segment["end_sec"])) > max(
                float(entity["start_sec"]), float(segment["start_sec"])
            ):
                expected_pairs.add((entity_id, segment_id))

    for row in frame.to_dict("records"):
        entity_id = str(row[entity_column])
        segment_id = str(row["asr_segment_id"])
        pair = (entity_id, segment_id)
        if pair in seen_pairs:
            raise ValueError("Transcript link entity/segment pair must be unique")
        seen_pairs.add(pair)
        entity = entity_by_id[entity_id]
        segment = segment_by_id[segment_id]
        overlap_start = max(float(entity["start_sec"]), float(segment["start_sec"]))
        overlap_end = min(float(entity["end_sec"]), float(segment["end_sec"]))
        overlap = overlap_end - overlap_start
        if overlap <= 0:
            raise ValueError("Transcript link must have positive temporal overlap")
        segment_duration = float(segment["end_sec"]) - float(segment["start_sec"])
        entity_duration = float(entity["end_sec"]) - float(entity["start_sec"])
        expected_values = {
            "overlap_start_sec": overlap_start,
            "overlap_end_sec": overlap_end,
            "overlap_sec": overlap,
            "segment_coverage": overlap / segment_duration,
            "entity_coverage": overlap / entity_duration,
            "coverage": overlap / segment_duration,
        }
        for column, expected in expected_values.items():
            if not math.isclose(float(row[column]), expected, abs_tol=1e-6):
                raise ValueError(f"Transcript link {column} is inconsistent")
        if int(row["assigned_word_count"]) != assigned_counts.get(pair, 0):
            raise ValueError("Transcript link assigned_word_count is inconsistent")
    if seen_pairs != expected_pairs:
        raise ValueError("Transcript links do not represent every temporal overlap")


def _validate_asr_words(
    segments: pd.DataFrame,
    words: pd.DataFrame,
    *,
    video_id: str,
) -> None:
    if words["asr_word_id"].astype(str).duplicated().any():
        raise ValueError("asr_word_id must be unique")
    segment_by_id = {
        str(row["asr_segment_id"]): row for row in segments.to_dict("records")
    }
    if set(words["asr_segment_id"].astype(str)) - set(segment_by_id):
        raise ValueError("ASR word references an unknown segment")
    words_by_segment: dict[str, list[dict[str, Any]]] = {}
    for row in words.to_dict("records"):
        segment_id = str(row["asr_segment_id"])
        segment = segment_by_id[segment_id]
        if str(row["video_id"]) != video_id:
            raise ValueError("ASR word video_id mismatch")
        if any(
            str(row[field]) != str(segment[field])
            for field in ("video_id", "provider", "model_name", "model_version")
        ):
            raise ValueError("ASR word provider/model identity mismatch")
        if row["start_frame"] is None or row["end_frame"] is None:
            raise ValueError("Production ASR words require resolved frame ranges")
        start_frame = int(row["start_frame"])
        end_frame = int(row["end_frame"])
        if not (
            int(segment["start_frame"])
            <= start_frame
            < end_frame
            <= int(segment["end_frame"])
        ):
            raise ValueError("ASR word frame range lies outside its parent segment")
        start = float(row["start_sec"])
        end = float(row["end_sec"])
        if not float(segment["start_sec"]) - 1e-6 <= start < end <= float(
            segment["end_sec"]
        ) + 1e-6:
            raise ValueError("ASR word lies outside its parent segment")
        words_by_segment.setdefault(segment_id, []).append(row)

    for segment_id, segment in segment_by_id.items():
        segment_words = sorted(
            words_by_segment.get(segment_id, []), key=lambda row: int(row["word_index"])
        )
        if not segment_words:
            raise ValueError("Accepted ASR segment has no canonical word alignment")
        if [int(row["word_index"]) for row in segment_words] != list(
            range(len(segment_words))
        ):
            raise ValueError("ASR word_index must be contiguous within each segment")
        expected_ids = [
            f"{segment_id}_W{index:05d}" for index in range(len(segment_words))
        ]
        if [str(row["asr_word_id"]) for row in segment_words] != expected_ids:
            raise ValueError("asr_word_id does not match canonical word order")
        ordered_by_time = sorted(
            segment_words,
            key=lambda row: (
                float(row["start_sec"]),
                float(row["end_sec"]),
                int(row["word_index"]),
            ),
        )
        if [str(row["asr_word_id"]) for row in ordered_by_time] != expected_ids:
            raise ValueError("ASR words are not timeline ordered")
        for previous, current in pairwise(ordered_by_time):
            if float(current["start_sec"]) < float(previous["end_sec"]) - 1e-3:
                raise ValueError("ASR words have a significant temporal overlap")
        reconstructed = " ".join(str(row["text"]) for row in segment_words)
        if normalize_for_comparison(reconstructed) != normalize_for_comparison(
            str(segment["text"])
        ):
            raise ValueError("ASR words do not reconstruct their parent segment")


def _validate_global_word_attribution(
    entities: pd.DataFrame,
    words: pd.DataFrame,
    *,
    entity_column: str,
) -> None:
    assignments = assign_words_to_intervals(
        entities.to_dict("records"),
        words.to_dict("records"),
        entity_id_field=entity_column,
    )
    assigned_ids = [
        str(word["asr_word_id"])
        for assigned in assignments.values()
        for word in assigned
    ]
    if len(assigned_ids) != len(set(assigned_ids)):
        raise ValueError(f"An ASR word is assigned to multiple {entity_column} intervals")
    expected_ids = set(words["asr_word_id"].astype(str))
    if set(assigned_ids) != expected_ids:
        raise ValueError(f"ASR words are unassigned from the {entity_column} partition")


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
