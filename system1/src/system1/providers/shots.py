"""Shot boundaries with TransNetV2, reusing the pinned project artifact."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from system1.phase01.model_artifacts import materialize_transnet_artifact
from system1.shots.transnet import detect_shot_scenes, scenes_to_shot_rows


class TransNetShots:
    def __init__(self, model_config: Mapping[str, Any], storage_config: Mapping[str, Any],
                 cache_root: Path) -> None:
        self.config = model_config
        self.artifact = materialize_transnet_artifact(
            model_config=model_config, storage_config=storage_config, cache_root=cache_root)

    def __call__(self, video_path: Path, timeline_rows: list[dict[str, Any]],
                 work_dir: Path) -> list[dict[str, Any]]:
        payload = detect_shot_scenes(
            video_path,
            artifact=self.artifact,
            output_path=work_dir / "transnet_predictions.json",
            threshold=float(self.config["threshold"]),
            transition_run_boundary=str(self.config["transition_run_boundary"]),
            expected_frame_count=len(timeline_rows),
        )
        video_id = str(timeline_rows[0]["video_id"])
        return scenes_to_shot_rows(video_id=video_id, scenes_inclusive=payload["scenes_inclusive"],
                                   frame_timeline=timeline_rows)
