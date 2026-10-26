"""Default release-time scene builder (ADR 0026, amended 2026-10-26).

Builds `ShotEvidence` for one video from the tables `build_release` holds in
memory and groups the shots with `group_scenes`. No model runs here: the
scene summary is the scene's distinct shot captions joined in time order, or
null when the scene has no caption.

Evidence per shot:

- image vector: mean SigLIP vector of the shot's keyframes;
- caption vector: E5 vector of the shot's `caption` document, if any;
- OCR lines: non-empty lines of the shot's `ocr` documents;
- ASR spans: `start_sec`/`end_sec` of the video's `asr` documents.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from system1.scenes.deterministic import SceneParams, ShotEvidence, group_scenes, scene_ids_for_shots

SCENE_COLUMNS = ["scene_id", "video_id", "start_shot_id", "end_shot_id", "start_frame", "end_frame",
                 "start_sec", "end_sec", "shot_count", "summary"]


def _shot_ids(value: Any) -> list[str]:
    return [part for part in str(value).split(",") if part]


def make_scene_builder(scene_config: Mapping[str, object]):
    """Return a `SceneBuilder` for `build_release` using `worker.yaml` section `scenes`."""

    params = SceneParams.from_config(scene_config)

    def build(video_id: str, evidence: Mapping[str, Any]) -> tuple[pd.DataFrame, dict[str, str]]:
        shots = evidence["shots"].sort_values("start_frame", kind="stable")
        keyframes = evidence["keyframes"].reset_index(drop=True)
        image_vectors = np.asarray(evidence["image_vectors"])
        documents = evidence["text_documents"].reset_index(drop=True)
        text_vectors = evidence.get("text_vectors")

        image_by_shot = {shot_id: image_vectors[group.index].mean(axis=0)
                         for shot_id, group in keyframes.groupby("shot_id", sort=False)}
        caption_vector: dict[str, np.ndarray] = {}
        caption_text: dict[str, str] = {}
        ocr_lines: dict[str, set[str]] = {}
        asr: list[tuple[float, float]] = []
        for index, row in documents.iterrows():
            kind = row["evidence_type"]
            if kind == "asr":
                asr.append((float(row["start_sec"]), float(row["end_sec"])))
                continue
            for shot_id in _shot_ids(row["shot_ids"]):
                if kind == "caption":
                    caption_text.setdefault(shot_id, str(row["text"]).strip())
                    if text_vectors is not None and len(text_vectors) == len(documents):
                        caption_vector.setdefault(shot_id, np.asarray(text_vectors[index]))
                elif kind == "ocr":
                    lines = {line.strip().lower() for line in str(row["text"]).splitlines()}
                    ocr_lines.setdefault(shot_id, set()).update(line for line in lines if line)

        shot_evidence = []
        for shot in shots.itertuples(index=False):
            if shot.shot_id not in image_by_shot:
                raise ValueError(f"shot {shot.shot_id} has no keyframe vector")
            shot_evidence.append(ShotEvidence(
                shot_id=shot.shot_id, start_frame=int(shot.start_frame), end_frame=int(shot.end_frame),
                start_sec=float(shot.start_sec), end_sec=float(shot.end_sec),
                image_vector=image_by_shot[shot.shot_id], caption_vector=caption_vector.get(shot.shot_id),
                ocr_lines=frozenset(ocr_lines.get(shot.shot_id, ()))))

        scenes = group_scenes(video_id, shot_evidence, asr, params)
        mapping = scene_ids_for_shots(scenes, shot_evidence)
        rows = []
        position = 0
        for scene in scenes:
            members = shot_evidence[position:position + scene.shot_count]
            position += scene.shot_count
            texts = list(dict.fromkeys(t for s in members if (t := caption_text.get(s.shot_id))))
            rows.append({**scene.__dict__, "summary": " ".join(texts) if texts else None})
        table = pd.DataFrame(rows, columns=SCENE_COLUMNS).astype({"summary": "object"})
        return table, mapping

    return build
