from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from PIL import Image

from system1.config import resolve_phase01_config
from system1.phase01.production import _build_scene_summaries
from system1.phase01.validation import validate_rows
from system1.scenes.summary import (
    MODEL_AUDIO_VISUAL_RELATIONS,
    build_speech_summary_evidence,
    build_visual_summary_evidence,
    normalize_audio_visual_relation,
    validate_scene_summary_semantics,
)


CONFIG_DIR = Path(__file__).resolve().parents[1] / "configs"
VIDEO_ID = "L21_V001"
SHOT_ID = f"{VIDEO_ID}_SH00000"
SCENE_ID = f"{VIDEO_ID}_SC00000"


def _user_settings() -> dict[str, str]:
    return {
        "batch_id": "batch_000",
        "worker_id": "worker_000",
        "hf_release_repo": "owner/release",
        "hf_checkpoint_repo": "owner/checkpoints",
        "hf_repo_type": "dataset",
        "hf_release_revision": "main",
        "checkpoint_revision": "main",
    }


def _resolved():
    return resolve_phase01_config(
        CONFIG_DIR,
        user_settings=_user_settings(),
        phase00_release_id="canonical_release_v001",
        environment="local",
    )


def _fixtures(tmp_path: Path, *, word_text: str | None = "xin"):
    keyframes_dir = tmp_path / "keyframes"
    keyframes_dir.mkdir(exist_ok=True)
    image_name = f"{VIDEO_ID}_f0000000.jpg"
    Image.new("RGB", (32, 32), "white").save(keyframes_dir / image_name)
    scenes = [
        {
            "scene_id": SCENE_ID,
            "video_id": VIDEO_ID,
            "start_shot_id": SHOT_ID,
            "end_shot_id": SHOT_ID,
            "start_sec": 0.0,
            "end_sec": 2.0,
        }
    ]
    shots = [
        {
            "shot_id": SHOT_ID,
            "video_id": VIDEO_ID,
            "start_sec": 0.0,
            "end_sec": 2.0,
        }
    ]
    keyframes = [
        {
            "shot_id": SHOT_ID,
            "keyframe_id": f"{VIDEO_ID}:0",
            "keyframe_ref": f"media://keyframes/{VIDEO_ID}/{image_name}",
            "timestamp_sec": 0.5,
            "is_representative": True,
        }
    ]
    captions = [
        {
            "shot_id": SHOT_ID,
            "caption_vi": "Một đầu bếp cho hành vào chảo.",
            "caption_en": "A cook adds onion to a pan.",
            "objects_vi": ["đầu bếp", "chảo"],
            "objects_en": ["cook", "pan"],
            "actions_vi": ["cho hành vào chảo"],
            "actions_en": ["adding onion to a pan"],
            "visible_text_summary_vi": "Bếp",
            "visible_text_summary_en": "Kitchen",
        }
    ]
    words = []
    if word_text is not None:
        words = [
            {
                "asr_word_id": f"{VIDEO_ID}_ASR00000_W00000",
                "asr_segment_id": f"{VIDEO_ID}_ASR00000",
                "word_index": 0,
                "text": word_text,
                "start_sec": 0.3,
                "end_sec": 0.6,
            }
        ]
    links = [
        {
            "scene_id": SCENE_ID,
            "asr_segment_id": f"{VIDEO_ID}_ASR00000",
            "overlap_start_sec": 0.0,
            "overlap_end_sec": 1.0,
            "overlap_sec": 1.0,
            "segment_coverage": 1.0,
            "entity_coverage": 0.5,
            "assigned_word_count": len(words),
        }
    ]
    return scenes, shots, keyframes, captions, words, links


class RecordingClient:
    def __init__(
        self,
        *,
        relation: str = "ALIGNED",
        outputs: dict[str, str] | None = None,
    ) -> None:
        self.relation = relation
        self.outputs = outputs or {}
        self.batches = []

    def request_many(self, requests):
        self.batches.append(list(requests))
        output = []
        for request in requests:
            values = {
                "scene_visual_summary_vi": "Một đầu bếp cho hành vào chảo.",
                "scene_visual_summary_en": "A cook adds onion to a pan.",
                "scene_speech_summary_vi": "Phần lời nói hướng dẫn cho hành vào chảo.",
                "scene_speech_summary_en": "The speech instructs adding onion to the pan.",
                "scene_audio_visual_relation": self.relation,
                "scene_final_summary_vi": "Đầu bếp cho hành vào chảo theo hướng dẫn.",
                "scene_final_summary_en": "The cook adds onion to the pan as instructed.",
            }
            values.update(self.outputs)
            values["scene_audio_visual_relation"] = self.relation
            output.append(
                {
                    "text": values[request.request_kind],
                    "__provider": "qwen_local",
                    "__model_id": "Qwen/Qwen2.5-VL-7B-Instruct",
                    "__model_revision": "fixture-revision",
                }
            )
        return output


def _build(
    tmp_path: Path,
    *,
    asr_status: str,
    word_text: str | None = "xin",
    relation: str = "ALIGNED",
    outputs: dict[str, str] | None = None,
):
    scenes, shots, keyframes, captions, words, links = _fixtures(
        tmp_path,
        word_text=word_text,
    )
    resolved = _resolved()
    client = RecordingClient(relation=relation, outputs=outputs)
    rows = _build_scene_summaries(
        video_id=VIDEO_ID,
        scenes=scenes,
        shots=shots,
        keyframes=keyframes,
        ocr_rows=[
            {
                "keyframe_id": f"{VIDEO_ID}:0",
                "text": "Bếp",
                "status": "pass",
            }
        ],
        captions=captions,
        asr_words=words,
        asr_status=asr_status,
        scene_links=links,
        stage_dir=tmp_path,
        client=client,
        model_config=resolved.payload["models"]["scene_summary"],
        summary_config=resolved.payload["phase01"]["scene_summary"],
    )
    return rows, client


@pytest.mark.parametrize(
    "relation",
    ["ALIGNED", "COMPLEMENTARY", "PARTIAL", "B_ROLL", "UNRELATED", "CONTRADICTORY"],
)
def test_available_speech_runs_seven_isolated_fields(
    tmp_path: Path,
    relation: str,
) -> None:
    rows, client = _build(tmp_path, asr_status="pass", relation=relation)
    row = rows[0]
    assert row["speech_evidence_status"] == "available"
    assert row["audio_visual_relation"] == relation.lower()
    assert [batch[0].request_kind for batch in client.batches] == [
        "scene_visual_summary_vi",
        "scene_speech_summary_vi",
        "scene_audio_visual_relation",
        "scene_final_summary_vi",
        "scene_visual_summary_en",
        "scene_speech_summary_en",
        "scene_final_summary_en",
    ]
    speech_request = client.batches[1][0]
    visual_request = client.batches[0][0]
    assert "CANONICAL_TRANSCRIPT:\nxin" in speech_request.prompt
    assert "CAPTION_VI" not in speech_request.prompt
    assert "OCR:" not in speech_request.prompt
    assert speech_request.image_paths == ()
    assert set(speech_request.identity) == {
        "scene_id",
        "field",
        "speech_evidence_fingerprint",
    }
    assert visual_request.image_paths
    assert "CAPTION_VI: Một đầu bếp" in visual_request.prompt
    assert "Bếp" in visual_request.prompt
    assert "CANONICAL_TRANSCRIPT" not in visual_request.prompt
    assert "xin" not in visual_request.prompt
    assert set(visual_request.identity) == {
        "scene_id",
        "field",
        "visual_evidence_fingerprint",
    }
    assert speech_request.fallback_image_paths != visual_request.fallback_image_paths
    placeholder = speech_request.fallback_image_paths[0]
    assert placeholder.name == "text_only_fallback_placeholder.jpg"
    assert Image.open(placeholder).size == (448, 448)
    relation_request = client.batches[2][0]
    assert relation_request.allowed_text_values == tuple(
        value.upper() for value in MODEL_AUDIO_VISUAL_RELATIONS
    )
    assert relation_request.image_paths == ()
    assert {
        "speech_evidence_fingerprint",
        "visual_evidence_fingerprint",
    }.issubset(relation_request.identity)
    assert "CANONICAL_TRANSCRIPT" not in relation_request.prompt
    final_request = client.batches[3][0]
    assert f"AUDIO_VISUAL_RELATION:\n{relation}" in final_request.prompt
    assert "CANONICAL_TRANSCRIPT" not in final_request.prompt
    assert "CAPTION_VI" not in final_request.prompt


def test_b_roll_final_prompt_requires_source_separation() -> None:
    prompt = (
        Path(__file__).resolve().parents[1]
        / "prompts"
        / "scene_final_summary_vi_v1.txt"
    ).read_text(encoding="utf-8")
    relation_prompt = (
        Path(__file__).resolve().parents[1]
        / "prompts"
        / "scene_audio_visual_relation_v1.txt"
    ).read_text(encoding="utf-8")
    assert "B_ROLL: bắt buộc tách" in prompt
    assert "UNRELATED: giữ hai nội dung tách biệt" in prompt
    assert "CONTRADICTORY: nêu bất đồng trung lập" in prompt
    assert "B_ROLL is not UNRELATED" in relation_prompt
    assert "PARTIAL is not COMPLEMENTARY" in relation_prompt


@pytest.mark.parametrize(
    ("case", "speech", "visual", "relation", "final"),
    [
        (
            "football_aligned",
            "Phần lời nói mô tả cầu thủ nhận bóng và dứt điểm.",
            "Một cầu thủ nhận bóng rồi dứt điểm về phía khung thành.",
            "ALIGNED",
            "Cầu thủ nhận bóng rồi dứt điểm, phù hợp với phần bình luận trong cảnh.",
        ),
        (
            "cooking_aligned",
            "Phần lời nói hướng dẫn phi hành rồi cho thịt bò vào chảo.",
            "Người nấu cho hành rồi thịt bò vào chảo và đảo thức ăn.",
            "ALIGNED",
            "Người nấu phi hành rồi cho thịt bò vào chảo theo phần hướng dẫn.",
        ),
        (
            "documentary_b_roll",
            "Phần thuyết minh đề cập kế hoạch mở thêm ba chi nhánh.",
            "Nhân viên bế mèo và đặt mèo vào chuồng.",
            "B_ROLL",
            "Hình ảnh cho thấy nhân viên chăm sóc mèo, trong khi phần thuyết minh đề cập kế hoạch mở thêm ba chi nhánh.",
        ),
        (
            "partial",
            "Phần lời nói hướng dẫn thái rau và đề cập nguồn gốc món ăn.",
            "Người nấu thái rau rồi chuẩn bị chảo.",
            "PARTIAL",
            "Hình ảnh cho thấy người nấu thái rau và chuẩn bị chảo; phần lời nói còn đề cập nguồn gốc món ăn.",
        ),
        (
            "unrelated",
            "Phần lời nói đề cập thị trường bất động sản.",
            "Các cầu thủ đang thi đấu bóng đá.",
            "UNRELATED",
            "Hình ảnh ghi lại một trận bóng đá, trong khi phần lời nói đề cập thị trường bất động sản.",
        ),
        (
            "contradictory",
            "Phần lời nói mô tả chiếc xe đang dừng.",
            "Chiếc xe đang di chuyển trên đường.",
            "CONTRADICTORY",
            "Hình ảnh cho thấy chiếc xe đang di chuyển, trong khi phần lời nói mô tả xe đang dừng.",
        ),
    ],
)
def test_relation_golden_cases_preserve_independent_summaries_and_policy(
    tmp_path: Path,
    case: str,
    speech: str,
    visual: str,
    relation: str,
    final: str,
) -> None:
    outputs = {
        "scene_speech_summary_vi": speech,
        "scene_visual_summary_vi": visual,
        "scene_final_summary_vi": final,
    }
    rows, client = _build(
        tmp_path,
        asr_status="pass",
        relation=relation,
        outputs=outputs,
    )
    row = rows[0]
    assert row["audio_visual_relation"] == relation.lower(), case
    assert row["speech_summary_vi"] == speech, case
    assert row["visual_summary_vi"] == visual, case
    assert row["summary_vi"] == final, case
    relation_request = client.batches[2][0]
    assert f"SPEECH_SUMMARY_VI:\n{speech}" in relation_request.prompt
    assert f"VISUAL_SUMMARY_VI:\n{visual}" in relation_request.prompt
    final_request = client.batches[3][0]
    assert f"AUDIO_VISUAL_RELATION:\n{relation}" in final_request.prompt
    if relation in {"B_ROLL", "PARTIAL", "UNRELATED", "CONTRADICTORY"}:
        assert "trong khi" in final or "phần lời nói" in final
    if relation == "B_ROLL":
        assert "để chăm sóc" not in final


@pytest.mark.parametrize(
    ("asr_status", "word_text", "speech_status", "relation"),
    [
        ("no_audio", None, "no_speech", "no_speech"),
        ("no_speech", None, "no_speech", "no_speech"),
        ("low_confidence", None, "unavailable", "speech_unavailable"),
        ("pass", None, "unavailable", "speech_unavailable"),
    ],
)
def test_missing_speech_uses_two_visual_requests_and_deterministic_copy(
    tmp_path: Path,
    asr_status: str,
    word_text: str | None,
    speech_status: str,
    relation: str,
) -> None:
    rows, client = _build(
        tmp_path,
        asr_status=asr_status,
        word_text=word_text,
    )
    row = rows[0]
    assert row["speech_evidence_status"] == speech_status
    assert row["audio_visual_relation"] == relation
    assert row["speech_summary_vi"] is None
    assert row["speech_summary_en"] is None
    assert len(row["speech_evidence_fingerprint"]) == 64
    assert len(row["visual_evidence_fingerprint"]) == 64
    assert row["summary_vi"] == row["visual_summary_vi"]
    assert row["summary_en"] == row["visual_summary_en"]
    assert [batch[0].request_kind for batch in client.batches] == [
        "scene_visual_summary_vi",
        "scene_visual_summary_en",
    ]
    provenance = [
        json.loads(line)
        for line in (tmp_path / "scene_summary_field_provenance.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    derived = {row["field"]: row for row in provenance if row["source_kind"] != "model_generated"}
    assert derived["audio_visual_relation"]["provider"] is None
    assert derived["summary_vi"]["source_kind"] == "derived_copy"


def test_translation_requests_only_receive_their_vietnamese_reference(tmp_path: Path) -> None:
    _, client = _build(tmp_path, asr_status="pass")
    visual_en = client.batches[4][0]
    speech_en = client.batches[5][0]
    final_en = client.batches[6][0]
    assert "REFERENCE_VIETNAMESE_VISUAL_SUMMARY" in visual_en.prompt
    assert "CANONICAL_TRANSCRIPT" not in visual_en.prompt
    assert "REFERENCE_VIETNAMESE_SPEECH_SUMMARY" in speech_en.prompt
    assert "CAPTION_VI" not in speech_en.prompt
    assert "REFERENCE_VIETNAMESE_FINAL_SUMMARY" in final_en.prompt
    assert "AUDIO_VISUAL_RELATION" not in final_en.prompt


def test_visual_overflow_preserves_early_middle_and_late_complete_blocks(
    tmp_path: Path,
) -> None:
    policy = copy.deepcopy(_resolved().payload["phase01"]["scene_summary"])
    policy["max_visual_evidence_chars"] = 1900
    shots = []
    representatives = {}
    keyframes_by_shot = {}
    captions = {}
    for index in range(9):
        shot_id = f"{VIDEO_ID}_SH{index:05d}"
        image_name = f"{VIDEO_ID}_f{index:07d}.jpg"
        (tmp_path / "keyframes").mkdir(exist_ok=True)
        Image.new("RGB", (16, 16), (index, index, index)).save(
            tmp_path / "keyframes" / image_name
        )
        shot = {
            "shot_id": shot_id,
            "video_id": VIDEO_ID,
            "start_sec": float(index),
            "end_sec": float(index + 1),
        }
        keyframe = {
            "shot_id": shot_id,
            "keyframe_id": f"{VIDEO_ID}:{index}",
            "keyframe_ref": f"media://keyframes/{VIDEO_ID}/{image_name}",
            "timestamp_sec": index + 0.5,
            "is_representative": True,
        }
        shots.append(shot)
        representatives[shot_id] = keyframe
        keyframes_by_shot[shot_id] = [keyframe]
        captions[shot_id] = {
            "caption_vi": f"Cảnh {index} " + "x" * 140,
            "caption_en": f"Shot {index} " + "y" * 140,
            "objects_vi": ["vật"],
            "objects_en": ["object"],
            "actions_vi": ["di chuyển"],
            "actions_en": ["moving"],
            "visible_text_summary_vi": "",
            "visible_text_summary_en": "",
        }
    scene = {
        "scene_id": SCENE_ID,
        "start_sec": 0.0,
        "end_sec": 9.0,
    }
    evidence = build_visual_summary_evidence(
        scene=scene,
        scene_shots=shots,
        representative=representatives,
        keyframes_by_shot=keyframes_by_shot,
        captions_by_shot=captions,
        ocr_by_keyframe={},
        stage_dir=tmp_path,
        policy=policy,
    )
    selected = [row["shot_id"] for row in evidence.evidence_shots]
    assert selected[0] == shots[0]["shot_id"]
    assert shots[4]["shot_id"] in selected
    assert selected[-1] == shots[-1]["shot_id"]
    assert len(evidence.body) <= policy["max_visual_evidence_chars"]
    assert evidence.body.count("--- SHOT ---") == len(selected)


def test_modality_budgets_and_fingerprints_are_independent(tmp_path: Path) -> None:
    scenes, shots, keyframes, captions, words, links = _fixtures(tmp_path)
    policy = copy.deepcopy(_resolved().payload["phase01"]["scene_summary"])
    representative = {SHOT_ID: keyframes[0]}
    kwargs = {
        "scene": scenes[0],
        "scene_shots": shots,
        "representative": representative,
        "keyframes_by_shot": {SHOT_ID: keyframes},
        "captions_by_shot": {SHOT_ID: captions[0]},
        "ocr_by_keyframe": {f"{VIDEO_ID}:0": "Bếp"},
        "stage_dir": tmp_path,
    }
    visual_a = build_visual_summary_evidence(policy=policy, **kwargs)
    speech_a = build_speech_summary_evidence(
        scene=scenes[0],
        assigned_words=words,
        asr_status="pass",
        scene_links=links,
        policy=policy,
    )
    visual_policy = {**policy, "max_visual_evidence_chars": 500}
    visual_b = build_visual_summary_evidence(policy=visual_policy, **kwargs)
    speech_b = build_speech_summary_evidence(
        scene=scenes[0],
        assigned_words=words,
        asr_status="pass",
        scene_links=links,
        policy=visual_policy,
    )
    assert speech_a.body == speech_b.body
    assert speech_a.fingerprint == speech_b.fingerprint
    assert visual_a.fingerprint != visual_b.fingerprint

    speech_policy = {**policy, "max_transcript_chars": 1}
    visual_c = build_visual_summary_evidence(policy=speech_policy, **kwargs)
    assert visual_c.body == visual_a.body
    assert visual_c.fingerprint == visual_a.fingerprint


def test_speech_fingerprint_is_stable_and_tracks_bounded_words(tmp_path: Path) -> None:
    scenes, _, _, _, words, links = _fixtures(tmp_path)
    words.append(
        {
            "asr_word_id": f"{VIDEO_ID}_ASR00000_W00001",
            "asr_segment_id": f"{VIDEO_ID}_ASR00000",
            "word_index": 1,
            "text": "chào",
            "start_sec": 0.7,
            "end_sec": 1.0,
        }
    )
    policy = copy.deepcopy(_resolved().payload["phase01"]["scene_summary"])
    first = build_speech_summary_evidence(
        scene=scenes[0],
        assigned_words=words,
        asr_status="pass",
        scene_links=links,
        policy=policy,
    )
    second = build_speech_summary_evidence(
        scene=scenes[0],
        assigned_words=words,
        asr_status="pass",
        scene_links=links,
        policy=policy,
    )
    bounded = build_speech_summary_evidence(
        scene=scenes[0],
        assigned_words=words,
        asr_status="pass",
        scene_links=links,
        policy={**policy, "max_transcript_chars": 3},
    )
    assert first.fingerprint == second.fingerprint
    assert first.transcript == "xin chào"
    assert bounded.transcript == "xin"
    assert bounded.fingerprint != first.fingerprint


@pytest.mark.parametrize("value", ["SAME_SCENE", "YES", "MAYBE", "broll explanation", "0.8"])
def test_relation_parser_rejects_non_contract_values(value: str) -> None:
    with pytest.raises(ValueError, match="Invalid model-generated"):
        normalize_audio_visual_relation(value)


def test_scene_summary_v4_schema_and_cross_field_rules() -> None:
    base = {
        "scene_id": SCENE_ID,
        "video_id": VIDEO_ID,
        "speech_evidence_status": "available",
        "speech_evidence_fingerprint": "a" * 64,
        "visual_evidence_fingerprint": "b" * 64,
        "speech_summary_vi": "Lời nói",
        "speech_summary_en": "Speech",
        "visual_summary_vi": "Hình ảnh",
        "visual_summary_en": "Visuals",
        "audio_visual_relation": "aligned",
        "summary_vi": "Tóm tắt",
        "summary_en": "Summary",
        "provider": "qwen_local",
        "model_name": "model",
        "model_version": "revision",
        "prompt_version": "scene_summary_adaptive_plain_text_v1",
        "schema_version": "scene_summary_response_v2",
        "confidence": None,
        "status": "pass",
    }
    validate_rows("scene_summaries", [base])
    validate_scene_summary_semantics(base)
    invalid = {**base, "speech_evidence_status": "unavailable"}
    with pytest.raises(ValueError):
        validate_rows("scene_summaries", [invalid])
