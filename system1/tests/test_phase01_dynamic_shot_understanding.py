from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from system1.artifacts.checkpoint import sha256_file
from system1.config import (
    load_configs,
    require_phase01_production_ready,
    resolve_phase01_config,
)
from system1.phase01.checkpoint import STAGE_DEPENDENCIES, downstream_stages
from system1.phase01.production import SHOT_CAPTION_FIELDS, _build_captions
from system1.shots.understanding import (
    build_shot_caption_evidence,
    normalized_ocr_token_jaccard_distance,
)

CONFIG_DIR = Path(__file__).resolve().parents[1] / "configs"
VIDEO_ID = "L21_V001"
SHOT_ID = f"{VIDEO_ID}_SH00000"


def _policy() -> dict:
    return copy.deepcopy(
        load_configs(CONFIG_DIR)["phase01"]["shot_caption"][
            "temporal_understanding"
        ]
    )


def _resolved():
    return resolve_phase01_config(
        CONFIG_DIR,
        user_settings={
            "batch_id": "batch_000",
            "worker_id": "worker_000",
            "hf_release_repo": "owner/release",
            "hf_checkpoint_repo": "owner/checkpoints",
            "hf_repo_type": "dataset",
            "hf_release_revision": "main",
            "checkpoint_revision": "main",
        },
        phase00_release_id="canonical_release_v001",
        environment="local",
    )


def _shot(*, duration: float = 6.0) -> dict:
    return {
        "shot_id": SHOT_ID,
        "video_id": VIDEO_ID,
        "start_sec": 0.0,
        "end_sec": duration,
    }


def _write_image(path: Path, *, reverse: bool = False) -> None:
    image = Image.new("L", (96, 64))
    draw = ImageDraw.Draw(image)
    for x in range(96):
        value = round(255 * x / 95)
        if reverse:
            value = 255 - value
        draw.line((x, 0, x, 63), fill=value)
    image.convert("RGB").save(path, format="JPEG", quality=95, subsampling=0)


def _write_solid_image(path: Path, color: tuple[int, int, int]) -> None:
    Image.new("RGB", (96, 64), color=color).save(
        path,
        format="JPEG",
        quality=95,
        subsampling=0,
    )


def _keyframe(
    frame_id: int,
    *,
    timestamp: float,
    role: str,
    representative: bool = False,
    reason: str = "role_anchor",
) -> dict:
    name = f"{VIDEO_ID}_f{frame_id:07d}.jpg"
    return {
        "keyframe_id": f"{VIDEO_ID}:{frame_id}",
        "video_id": VIDEO_ID,
        "frame_id": frame_id,
        "timestamp_sec": timestamp,
        "shot_id": SHOT_ID,
        "scene_id": None,
        "keyframe_role": role,
        "quality_score": 1.0,
        "is_representative": representative,
        "selection_reason": reason,
        "keyframe_ref": f"media://keyframes/{VIDEO_ID}/{name}",
        "thumbnail_ref": f"media://thumbnails/{VIDEO_ID}/{name}.webp",
        "status": "pass",
    }


def _ocr(keyframe: dict, *, status: str = "empty", text: str = "") -> dict:
    return {
        "keyframe_id": keyframe["keyframe_id"],
        "shot_id": SHOT_ID,
        "status": status,
        "text": text,
        "raw_text": text,
    }


def _stage(tmp_path: Path, keyframes: list[dict], *, reverse_ids=()) -> Path:
    keyframe_dir = tmp_path / "keyframes"
    keyframe_dir.mkdir()
    for row in keyframes:
        _write_image(
            keyframe_dir / Path(row["keyframe_ref"]).name,
            reverse=int(row["frame_id"]) in set(reverse_ids),
        )
    return tmp_path


@pytest.mark.parametrize("duration", [1.0, 10.0])
def test_short_or_long_static_shot_uses_representative_only(
    tmp_path: Path,
    duration: float,
) -> None:
    frames = [
        _keyframe(0, timestamp=0.2, role="early"),
        _keyframe(1, timestamp=5.0, role="middle", representative=True),
        _keyframe(2, timestamp=9.7, role="late"),
    ]
    stage = _stage(tmp_path, frames)
    evidence = build_shot_caption_evidence(
        shot=_shot(duration=duration),
        keyframes=frames,
        ocr_rows=[_ocr(frame) for frame in frames],
        stage_dir=stage,
        policy=_policy(),
    )
    assert evidence.mode == "representative_only"
    assert [row["keyframe_id"] for row in evidence.source_keyframes] == [
        f"{VIDEO_ID}:1"
    ]
    assert not (stage / "diagnostics" / "shot_caption_requests").exists()


def test_meaningful_supplemental_triggers_ordered_storyboard(tmp_path: Path) -> None:
    frames = [
        _keyframe(0, timestamp=0.2, role="early"),
        _keyframe(2, timestamp=2.0, role="middle", representative=True),
        _keyframe(
            1,
            timestamp=1.0,
            role="supplemental",
            reason="visual_novelty",
        ),
    ]
    stage = _stage(tmp_path, frames, reverse_ids={1})
    evidence = build_shot_caption_evidence(
        shot=_shot(),
        keyframes=frames,
        ocr_rows=[_ocr(frame) for frame in frames],
        stage_dir=stage,
        policy=_policy(),
    )
    assert evidence.mode == "temporal_storyboard"
    assert "meaningful_supplemental" in evidence.trigger_reasons
    assert [row["frame_id"] for row in evidence.source_keyframes] == [1, 2]
    assert evidence.image_path.is_file()
    first_hash = sha256_file(evidence.image_path)
    rebuilt = build_shot_caption_evidence(
        shot=_shot(),
        keyframes=frames,
        ocr_rows=[_ocr(frame) for frame in frames],
        stage_dir=stage,
        policy=_policy(),
    )
    assert sha256_file(rebuilt.image_path) == first_hash
    assert rebuilt.evidence_fingerprint == evidence.evidence_fingerprint


def test_long_visual_or_reliable_ocr_change_triggers_but_failed_ocr_does_not(
    tmp_path: Path,
) -> None:
    frames = [
        _keyframe(0, timestamp=0.2, role="early", representative=True),
        _keyframe(1, timestamp=5.8, role="late"),
    ]
    stage = _stage(tmp_path, frames, reverse_ids={1})
    visual = build_shot_caption_evidence(
        shot=_shot(),
        keyframes=frames,
        ocr_rows=[_ocr(frame, status="failed") for frame in frames],
        stage_dir=stage,
        policy=_policy(),
    )
    assert visual.mode == "temporal_storyboard"
    assert visual.trigger_reasons == ("visual_change",)
    assert visual.max_ocr_change_score is None

    _write_image(stage / "keyframes" / Path(frames[1]["keyframe_ref"]).name)
    ocr_changed = build_shot_caption_evidence(
        shot=_shot(),
        keyframes=frames,
        ocr_rows=[
            _ocr(frames[0], status="pass", text="Bếp"),
            _ocr(frames[1], status="pass", text="Trứng"),
        ],
        stage_dir=stage,
        policy=_policy(),
    )
    assert ocr_changed.mode == "temporal_storyboard"
    assert ocr_changed.trigger_reasons == ("ocr_change",)

    unavailable = build_shot_caption_evidence(
        shot=_shot(),
        keyframes=frames,
        ocr_rows=[_ocr(frames[0], status="failed"), _ocr(frames[1], status="empty")],
        stage_dir=stage,
        policy=_policy(),
    )
    assert unavailable.mode == "representative_only"
    assert "OCR_TEXT: <UNAVAILABLE>" in unavailable.evidence_body


def test_ocr_jaccard_contract() -> None:
    assert normalized_ocr_token_jaccard_distance("empty", "", "empty", "") == 0.0
    assert normalized_ocr_token_jaccard_distance("empty", "", "pass", "TRỨNG") == 1.0
    assert normalized_ocr_token_jaccard_distance("failed", "", "pass", "TRỨNG") is None
    assert normalized_ocr_token_jaccard_distance("pass", "BẾP Trứng", "pass", "bếp trứng") == 0.0


def test_exact_duplicate_supplemental_collapses_to_representative(
    tmp_path: Path,
) -> None:
    frames = [
        _keyframe(0, timestamp=0.2, role="middle", representative=True),
        _keyframe(
            1,
            timestamp=2.0,
            role="supplemental",
            reason="visual_novelty",
        ),
    ]
    stage = _stage(tmp_path, frames)
    evidence = build_shot_caption_evidence(
        shot=_shot(),
        keyframes=frames,
        ocr_rows=[_ocr(frame) for frame in frames],
        stage_dir=stage,
        policy=_policy(),
    )
    assert evidence.mode == "representative_only"
    assert len(evidence.source_keyframes) == 1


def test_source_budget_keeps_representative_and_is_deterministic(
    tmp_path: Path,
) -> None:
    frames = [
        _keyframe(0, timestamp=0.2, role="middle", representative=True),
        _keyframe(
            1,
            timestamp=1.0,
            role="supplemental",
            reason="text_change",
        ),
        _keyframe(
            2,
            timestamp=2.0,
            role="supplemental",
            reason="visual_novelty",
        ),
    ]
    stage = _stage(tmp_path, frames, reverse_ids={2})
    policy = _policy()
    policy["max_source_keyframes"] = 2
    evidence = build_shot_caption_evidence(
        shot=_shot(),
        keyframes=frames,
        ocr_rows=[_ocr(frame) for frame in frames],
        stage_dir=stage,
        policy=policy,
    )
    assert evidence.mode == "temporal_storyboard"
    assert [row["frame_id"] for row in evidence.source_keyframes] == [0, 2]


def test_storyboard_tiles_follow_chronological_source_order(tmp_path: Path) -> None:
    frames = [
        _keyframe(
            30,
            timestamp=3.0,
            role="supplemental",
            reason="text_change",
        ),
        _keyframe(10, timestamp=1.0, role="early", representative=True),
        _keyframe(
            20,
            timestamp=2.0,
            role="supplemental",
            reason="visual_novelty",
        ),
    ]
    stage = _stage(tmp_path, frames)
    colors = {
        10: (220, 20, 20),
        20: (20, 220, 20),
        30: (20, 20, 220),
    }
    for frame in frames:
        _write_solid_image(
            stage / "keyframes" / Path(frame["keyframe_ref"]).name,
            colors[int(frame["frame_id"])],
        )

    evidence = build_shot_caption_evidence(
        shot=_shot(),
        keyframes=frames,
        ocr_rows=[_ocr(frame) for frame in frames],
        stage_dir=stage,
        policy=_policy(),
    )

    assert [row["frame_id"] for row in evidence.source_keyframes] == [10, 20, 30]
    with Image.open(evidence.image_path) as storyboard:
        sampled = (
            storyboard.getpixel((224, 192)),
            storyboard.getpixel((672, 192)),
            storyboard.getpixel((224, 544)),
        )
    for actual, expected in zip(sampled, colors.values(), strict=True):
        assert all(abs(channel - target) <= 5 for channel, target in zip(actual, expected, strict=True))


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("enabled",), False, "enabled"),
        (("contract_version",), "unknown", "contract_version"),
        (("mode_policy",), "unknown", "mode_policy"),
        (("min_duration_sec",), 0, "min_duration_sec"),
        (("max_source_keyframes",), 1, "max_source_keyframes"),
        (("max_source_keyframes",), True, "max_source_keyframes"),
        (("min_duration_sec",), True, "min_duration_sec"),
        (("visual_change", "policy"), "unknown", "visual_change.policy"),
        (("visual_change", "hash_size"), 0, "hash_size"),
        (("visual_change", "hash_size"), True, "hash_size"),
        (("visual_change", "min_hamming_ratio"), 1.1, "min_hamming_ratio"),
        (("visual_change", "min_hamming_ratio"), False, "min_hamming_ratio"),
        (("ocr_change", "policy"), "unknown", "ocr_change.policy"),
        (("ocr_change", "min_jaccard_distance"), -0.1, "min_jaccard_distance"),
        (("source_selection_policy",), "unknown", "source_selection_policy"),
        (("storyboard_policy",), "unknown", "storyboard_policy"),
    ],
)
def test_temporal_understanding_config_is_validated(
    path: tuple[str, ...], value: object, message: str
) -> None:
    resolved = _resolved()
    target = resolved.payload["phase01"]["shot_caption"]["temporal_understanding"]
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value
    with pytest.raises((TypeError, ValueError), match=message):
        require_phase01_production_ready(resolved)


class _CaptionClient:
    def __init__(
        self,
        *,
        caption_vi: str = "Các khung hình lần lượt cho thấy một người chuẩn bị món ăn.",
    ) -> None:
        self.requests = []
        self.caption_vi = caption_vi

    def request_many(self, requests):
        self.requests = list(requests)
        responses = []
        for request in requests:
            field = request.identity["field"]
            if field == "caption_vi":
                text = self.caption_vi
            elif field == "caption_en":
                text = "The frames sequentially show a person preparing food."
            elif field.startswith("objects"):
                text = "chảo" if field.endswith("_vi") else "pan"
            elif field.startswith("actions"):
                text = "chuẩn bị món ăn" if field.endswith("_vi") else "preparing food"
            else:
                text = "<NONE>"
            responses.append(
                {
                    "text": text,
                    "__provider": "qwen_local",
                    "__model_id": "Qwen/Qwen2.5-VL-7B-Instruct",
                    "__model_revision": "revision",
                }
            )
        return responses


def test_build_captions_uses_one_storyboard_for_all_eight_fields(
    tmp_path: Path,
) -> None:
    frames = [
        _keyframe(0, timestamp=0.2, role="early", representative=True),
        _keyframe(
            1,
            timestamp=2.0,
            role="supplemental",
            reason="visual_novelty",
        ),
    ]
    stage = _stage(tmp_path, frames, reverse_ids={1})
    client = _CaptionClient()
    config = load_configs(CONFIG_DIR)
    rows = _build_captions(
        video_id=VIDEO_ID,
        shots=[_shot()],
        keyframes=frames,
        ocr_rows=[_ocr(frame) for frame in frames],
        stage_dir=stage,
        client=client,
        model_config=config["models"]["phase01"]["shot_caption"],
        temporal_policy=_policy(),
    )
    assert len(rows) == 1
    assert len(client.requests) == 8
    assert {request.identity["field"] for request in client.requests} == set(
        SHOT_CAPTION_FIELDS
    )
    image_paths = {request.image_paths for request in client.requests}
    assert len(image_paths) == 1
    assert next(iter(image_paths))[0].name.endswith("_temporal_storyboard.jpg")
    for request in client.requests:
        assert request.fallback_image_paths == request.image_paths
        assert request.identity["caption_mode"] == "temporal_storyboard"
        assert "CAPTION_MODE: temporal_storyboard" in request.prompt
        assert "ASR" not in request.prompt
        assert "TRANSCRIPT" not in request.prompt
    provenance = [
        json.loads(line)
        for line in (stage / "shot_caption_field_provenance.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(provenance) == 8
    assert {row["schema_version"] for row in provenance} == {
        "shot_caption_field_provenance_v2"
    }
    assert {row["caption_mode"] for row in provenance} == {"temporal_storyboard"}
    assert len({row["caption_evidence_fingerprint"] for row in provenance}) == 1
    assert all(row["source_keyframe_ids"] == [f"{VIDEO_ID}:0", f"{VIDEO_ID}:1"] for row in provenance)


def test_golden_cooking_progression_keeps_all_ordered_evidence(
    tmp_path: Path,
) -> None:
    frames = [
        _keyframe(0, timestamp=0.2, role="early"),
        _keyframe(
            1,
            timestamp=1.5,
            role="supplemental",
            reason="visual_novelty",
        ),
        _keyframe(2, timestamp=3.0, role="middle", representative=True),
        _keyframe(3, timestamp=5.8, role="late"),
    ]
    ocr_rows = [
        _ocr(frames[0], status="pass", text="cầm trứng"),
        _ocr(frames[1], status="pass", text="đập trứng"),
        _ocr(frames[2], status="pass", text="trứng trong chảo"),
        _ocr(frames[3], status="pass", text="khuấy"),
    ]
    stage = _stage(tmp_path, frames)
    expected_caption = (
        "Người nấu lần lượt cầm quả trứng, đập trứng vào chảo rồi khuấy "
        "phần trứng trong chảo."
    )
    client = _CaptionClient(caption_vi=expected_caption)
    config = load_configs(CONFIG_DIR)

    rows = _build_captions(
        video_id=VIDEO_ID,
        shots=[_shot()],
        keyframes=frames,
        ocr_rows=ocr_rows,
        stage_dir=stage,
        client=client,
        model_config=config["models"]["phase01"]["shot_caption"],
        temporal_policy=_policy(),
    )

    assert rows[0]["caption_vi"] == expected_caption
    assert all(
        request.identity["caption_mode"] == "temporal_storyboard"
        for request in client.requests
    )
    caption_request = next(
        request
        for request in client.requests
        if request.identity["field"] == "caption_vi"
    )
    assert [
        caption_request.prompt.index(text)
        for text in ("cầm trứng", "đập trứng", "trứng trong chảo", "khuấy")
    ] == sorted(
        caption_request.prompt.index(text)
        for text in ("cầm trứng", "đập trứng", "trứng trong chảo", "khuấy")
    )
    provenance = [
        json.loads(line)
        for line in (stage / "shot_caption_field_provenance.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert all(
        row["source_frame_ids"] == [0, 1, 2, 3]
        for row in provenance
    )


def test_build_captions_uses_representative_image_for_static_shot(
    tmp_path: Path,
) -> None:
    frames = [
        _keyframe(0, timestamp=0.2, role="early"),
        _keyframe(1, timestamp=2.0, role="middle", representative=True),
        _keyframe(2, timestamp=5.8, role="late"),
    ]
    stage = _stage(tmp_path, frames)
    client = _CaptionClient()
    config = load_configs(CONFIG_DIR)

    _build_captions(
        video_id=VIDEO_ID,
        shots=[_shot()],
        keyframes=frames,
        ocr_rows=[_ocr(frame) for frame in frames],
        stage_dir=stage,
        client=client,
        model_config=config["models"]["phase01"]["shot_caption"],
        temporal_policy=_policy(),
    )

    representative_path = stage / "keyframes" / Path(frames[1]["keyframe_ref"]).name
    assert len(client.requests) == 8
    for request in client.requests:
        assert request.image_paths == (representative_path,)
        assert request.fallback_image_paths == (representative_path,)
        assert request.identity["caption_mode"] == "representative_only"
        assert "CAPTION_MODE: representative_only" in request.prompt


def test_v2_prompts_define_sparse_same_shot_evidence_and_reject_speech() -> None:
    prompt_dir = Path(__file__).resolve().parents[1] / "prompts"
    prompt_names = (
        "shot_caption_vi_v2.txt",
        "shot_caption_en_v2.txt",
        "shot_objects_vi_v2.txt",
        "shot_objects_en_v2.txt",
        "shot_actions_vi_v2.txt",
        "shot_actions_en_v2.txt",
        "shot_visible_text_summary_vi_v2.txt",
        "shot_visible_text_summary_en_v2.txt",
    )
    for name in prompt_names:
        path = prompt_dir / name
        text = path.read_text(encoding="utf-8").lower()
        assert "continuous video shot" in text
        assert "storyboard" in text
        assert "untrusted" in text
        assert "speech" in text or "spoken" in text
        assert "intention" in text
        assert "sample" in text


def test_task5_config_and_checkpoint_scope() -> None:
    configs = load_configs(CONFIG_DIR)
    phase01 = configs["phase01"]
    models = configs["models"]
    artifacts = configs["artifact"]
    caption_model = models["phase01"]["shot_caption"]
    assert phase01["schema_version"] == "phase01_pipeline_v1_11"
    assert phase01["pipeline_id"] == "phase01_production_v1_11"
    assert models["schema_version"] == "phase01_models_v1_8"
    assert caption_model["prompt_bundle_version"] == (
        "shot_caption_temporal_plain_text_fields_v2"
    )
    assert caption_model["generation_contract_version"] == (
        "shot_caption_temporal_plain_text_fields_v2"
    )
    assert STAGE_DEPENDENCIES["shot_captions"] == ("shots", "keyframes", "ocr")
    assert set(downstream_stages("shot_captions")) == {
        "scenes",
        "scene_transcript_links",
        "scene_summaries",
        "package",
        "sync",
    }
    assert artifacts["checkpoint"]["stage_outputs"]["shot_captions"] == [
        "shot_captions.parquet",
        "shot_caption_field_provenance.jsonl",
    ]
