from __future__ import annotations

from pathlib import Path

from PIL import Image

from system1.phase01 import production
from system1.phase01.validation import validate_rows
from system1.vlm.client import BatchRequestError

MODEL_CONFIG = {
    "provider": "vintern_local",
    "model_id": "5CD-AI/Vintern-1B-v3_5",
    "model_revision": "revision",
    "prompt_version": "keyframe_ocr_v2",
    "response_schema_version": "keyframe_ocr_response_v1",
    "structured_output_contract_version": "json_schema_prompt_v1",
}
OCR_CONFIG = {
    "run_on_keyframe_roles": ["middle"],
    "text_presence_filter": {
        "enabled": True,
        "policy": "opencv_conservative_v1",
        "max_long_side": 960,
        "canny_low": 50,
        "canny_high": 150,
        "max_no_text_edge_density": 0.0015,
        "max_no_text_gray_std": 12,
    },
}


class RecordingClient:
    def __init__(self) -> None:
        self.requests = []

    def request_many(self, requests):
        self.requests.extend(requests)
        return [
            {
                "full_text": "UY BAN NHAN DAN",
                "ocr_blocks": [],
                "language": "vi",
                "confidence": 0.9,
                "__provider": "vintern_local",
                "__model_id": MODEL_CONFIG["model_id"],
                "__model_revision": MODEL_CONFIG["model_revision"],
            }
            for _request in requests
        ]


def _keyframe(stage_dir: Path, *, color: str = "black") -> dict:
    keyframes = stage_dir / "keyframes"
    keyframes.mkdir(parents=True)
    image_path = keyframes / "frame.jpg"
    Image.new("RGB", (320, 180), color=color).save(image_path)
    return {
        "keyframe_id": "L21_V001:0",
        "video_id": "L21_V001",
        "shot_id": "L21_V001_SH00000",
        "frame_id": 0,
        "keyframe_role": "middle",
        "keyframe_ref": "media://keyframes/L21_V001/frame.jpg",
    }


def test_high_confidence_no_text_skips_vintern_and_emits_empty_ocr_v2(
    tmp_path: Path,
) -> None:
    client = RecordingClient()
    diagnostics = {}

    rows = production._build_ocr(
        video_id="L21_V001",
        keyframes=[_keyframe(tmp_path)],
        stage_dir=tmp_path,
        client=client,
        model_config=MODEL_CONFIG,
        ocr_config=OCR_CONFIG,
        diagnostics=diagnostics,
    )

    assert client.requests == []
    assert rows[0]["status"] == "empty"
    assert rows[0]["provider"] == "opencv_text_gate"
    assert rows[0]["model_name"] == "opencv_mser_canny"
    assert diagnostics == {
        "gate_checked": 1,
        "gate_no_text": 1,
        "gate_failures": 0,
        "vintern_processed": 0,
        "vintern_failed": 0,
    }
    validate_rows("ocr", rows)


def test_uncertain_gate_runs_vintern(tmp_path: Path, monkeypatch) -> None:
    client = RecordingClient()
    monkeypatch.setattr(production, "_text_presence_gate", lambda *_args: "uncertain")

    rows = production._build_ocr(
        video_id="L21_V001",
        keyframes=[_keyframe(tmp_path, color="white")],
        stage_dir=tmp_path,
        client=client,
        model_config=MODEL_CONFIG,
        ocr_config=OCR_CONFIG,
    )

    assert len(client.requests) == 1
    assert rows[0]["status"] == "pass"
    assert rows[0]["provider"] == "vintern_local"
    validate_rows("ocr", rows)


def test_gate_failure_runs_vintern_and_counts_failure(
    tmp_path: Path, monkeypatch
) -> None:
    client = RecordingClient()
    diagnostics = {}

    def fail_gate(*_args):
        raise RuntimeError("detector error")

    monkeypatch.setattr(production, "_text_presence_gate", fail_gate)
    rows = production._build_ocr(
        video_id="L21_V001",
        keyframes=[_keyframe(tmp_path, color="white")],
        stage_dir=tmp_path,
        client=client,
        model_config=MODEL_CONFIG,
        ocr_config=OCR_CONFIG,
        diagnostics=diagnostics,
    )

    assert len(client.requests) == 1
    assert diagnostics["gate_failures"] == 1
    assert diagnostics["vintern_processed"] == 1
    validate_rows("ocr", rows)


def test_supplemental_role_runs_through_existing_ocr_gate(
    tmp_path: Path, monkeypatch
) -> None:
    client = RecordingClient()
    keyframe = _keyframe(tmp_path, color="white")
    keyframe["keyframe_role"] = "supplemental"
    ocr_config = {
        **OCR_CONFIG,
        "run_on_keyframe_roles": ["early", "middle", "late", "supplemental"],
    }
    monkeypatch.setattr(production, "_text_presence_gate", lambda *_args: "uncertain")

    rows = production._build_ocr(
        video_id="L21_V001",
        keyframes=[keyframe],
        stage_dir=tmp_path,
        client=client,
        model_config=MODEL_CONFIG,
        ocr_config=ocr_config,
    )

    assert len(client.requests) == 1
    assert client.requests[0].identity == {"keyframe_id": "L21_V001:0"}
    assert rows[0]["status"] == "pass"


def test_ocr_failures_are_counted_per_vintern_request(
    tmp_path: Path, monkeypatch
) -> None:
    class FailingClient:
        def request_many(self, requests):
            raise BatchRequestError(
                results=[None] * len(requests),
                errors={index: ValueError("invalid JSON") for index in range(len(requests))},
            )

    diagnostics = {}
    monkeypatch.setattr(production, "_text_presence_gate", lambda *_args: "uncertain")

    rows = production._build_ocr(
        video_id="L21_V001",
        keyframes=[_keyframe(tmp_path, color="white")],
        stage_dir=tmp_path,
        client=FailingClient(),
        model_config=MODEL_CONFIG,
        ocr_config=OCR_CONFIG,
        diagnostics=diagnostics,
    )

    assert rows[0]["status"] == "failed"
    assert diagnostics["vintern_processed"] == 1
    assert diagnostics["vintern_failed"] == 1


def test_ocr_stage_is_failed_when_every_vintern_request_fails() -> None:
    status = production._ocr_stage_status(
        {"failed": 3, "empty": 2},
        {"vintern_processed": 3, "vintern_failed": 3},
    )

    assert status == "failed"


def test_ocr_stage_is_partial_when_only_some_vintern_requests_fail() -> None:
    status = production._ocr_stage_status(
        {"pass": 2, "failed": 1, "empty": 2},
        {"vintern_processed": 3, "vintern_failed": 1},
    )

    assert status == "partial"


def test_ocr_stage_passes_when_gate_skips_every_image() -> None:
    status = production._ocr_stage_status(
        {"empty": 5},
        {"vintern_processed": 0, "vintern_failed": 0},
    )

    assert status == "pass"
