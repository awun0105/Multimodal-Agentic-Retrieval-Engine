"""Pin (chốt frame) wiring: string keys, video-optional pinning, submission integration."""

import inspect
import json
import warnings

import pytest

from schemas import TrakeEventMatch, TrakeOutcome, TrakeVideoMatch
from trake_submission import parse_pin_key, pin_key


def _event(index: int, frame_idx: int) -> TrakeEventMatch:
    return TrakeEventMatch(
        keyframe_id=f"kf{index}",
        video_id="L21_V001",
        keyframe_no=index + 1,
        frame_idx=frame_idx,
        pts_time_sec=frame_idx / 25.0,
        fps=25.0,
        image_path="x.jpg",
        image_relpath="x.jpg",
        score=0.33,
        event_index=index,
    )


def _outcome(video_id: str = "L21_V001", frames=(1000, 2000, 3000)) -> TrakeOutcome:
    events = tuple(_event(i, f) for i, f in enumerate(frames))
    events = tuple(
        TrakeEventMatch(**{**e.__dict__, "video_id": video_id}) for e in events
    )
    video = TrakeVideoMatch(
        video_id=video_id,
        collection_id=video_id.split("_")[0],
        title="t",
        author="a",
        total_score=1.0,
        events=events,
        max_frame_idx=max(frames) + 5000,
    )
    return TrakeOutcome(videos=(video,), queries=())


# --- Key format ---


def test_pin_key_builds_string_key():
    assert pin_key("L21_V001", 0) == "L21_V001|0"


def test_pin_key_survives_json_round_trip():
    """Tuple keys die at the browser boundary; this is why keys are strings."""
    with pytest.raises(TypeError):
        json.dumps({("L21_V001", 0): 393})

    wire = json.dumps({pin_key("L21_V001", 0): 393})
    assert json.loads(wire) == {"L21_V001|0": 393}


def test_parse_pin_key_round_trips():
    assert parse_pin_key(pin_key("L30_V011", 3)) == ("L30_V011", 3)


def test_pin_key_splits_on_last_separator():
    assert parse_pin_key("odd|name|2") == ("odd|name", 2)


@pytest.mark.parametrize("bad", ["L21_V001", "|0", "L21_V001|x", ""])
def test_parse_pin_key_returns_none_for_malformed_keys(bad):
    """State lives in the browser; a junk key must not crash the preview."""
    assert parse_pin_key(bad) is None


# --- process_pin ---


def _pin(calc_frame, accuracy, pins=None, accs=None, v_id="L21_V001", e_idx=0, kf=290):
    from trake_ui import process_pin

    # Runtime argument order follows the click handler's inputs list:
    # (v_id, e_idx, kf_frame, pinned_frames, accuracies, calc_frame, accuracy)
    return process_pin(v_id, e_idx, kf, pins or {}, accs or {}, calc_frame, accuracy)


def test_process_pin_uses_browser_reported_frame():
    pinned, accs, status = _pin(300, "calculated")
    assert pinned == {pin_key("L21_V001", 0): 300}
    assert accs == {pin_key("L21_V001", 0): "calculated"}
    assert "Calculated" in status["value"]


def test_process_pin_falls_back_to_keyframe_when_player_silent():
    pinned, accs, status = _pin(None, "none")
    assert pinned == {pin_key("L21_V001", 0): 290}
    assert accs == {pin_key("L21_V001", 0): "keyframe"}
    assert "(Keyframe 290)" in status["value"]


def test_process_pin_overwrites_same_event():
    pinned, accs, _s = _pin(300, "calculated")
    pinned, accs, _s = _pin(500, "estimated", pinned, accs)
    assert pinned == {pin_key("L21_V001", 0): 500}
    assert accs == {pin_key("L21_V001", 0): "estimated"}


def test_process_pin_keeps_different_events_separate():
    pinned, accs, _s = _pin(300, "calculated")
    pinned, accs, _s = _pin(500, "calculated", pinned, accs, e_idx=1, kf=400)
    key_a, key_b = pin_key("L21_V001", 0), pin_key("L21_V001", 1)
    assert pinned == {key_a: 300, key_b: 500}
    assert accs == {key_a: "calculated", key_b: "calculated"}


def test_process_pin_ignores_empty_video_id():
    pinned, _accs, status = _pin(300, "calculated", v_id="")
    assert pinned == {}
    assert "Chưa chốt được" in status["value"]


def test_process_pin_malformed_browser_value_falls_back():
    pinned, accs, _status = _pin("not-a-number", "estimated", kf=290)
    assert pinned == {pin_key("L21_V001", 0): 290}
    # The accuracy label must not claim a calculated value we could not parse.
    assert accs == {pin_key("L21_V001", 0): "keyframe"}


def test_process_pin_copies_input_dictionaries():
    """Mutating the Gradio State object in place would skip .change handlers."""
    pins = {"existing": 1}
    accs = {"existing": "estimated"}
    out_pins, out_accs, _s = _pin(300, "calculated", pins, accs)
    assert out_pins is not pins and out_accs is not accs
    assert pins == {"existing": 1} and accs == {"existing": "estimated"}
    assert out_pins["existing"] == 1


# --- Submission integration ---


def test_build_submission_uses_pinned_frame_over_algorithm_frame():
    import trake

    rows = trake.build_submission(
        _outcome(), max_rows=1, pinned_frames={"L21_V001|1": 2500}
    )
    assert rows[0][1] == (1000, 2500, 3000)


def test_build_submission_promotes_pinned_video_to_top():
    """A pin must lift its whole video above the untouched ranking — this
    regressed when the video id was split on ':' instead of the pin separator."""
    import trake

    ranked_first, ranked_second = _outcome("L21_V001"), _outcome("L21_V002")
    outcome = TrakeOutcome(
        videos=(ranked_first.videos[0], ranked_second.videos[0]), queries=()
    )

    rows = trake.build_submission(
        outcome,
        max_rows=trake.SUBMISSION_MAX_ROWS,
        pinned_frames={pin_key("L21_V002", 2): 4321},
    )
    assert rows[0] == ("L21_V002", (1000, 2000, 4321))


def test_build_submission_ignores_malformed_pin_keys_for_promotion(monkeypatch):
    import trake

    ranked_first, ranked_second = _outcome("L21_V001"), _outcome("L21_V002")
    outcome = TrakeOutcome(
        videos=(ranked_first.videos[0], ranked_second.videos[0]), queries=()
    )

    # One row per video so both videos fit under max_rows.
    monkeypatch.setattr(trake, "SPREAD_ROWS_PER_VIDEO", 1)
    rows = trake.build_submission(
        outcome,
        max_rows=2,
        pinned_frames={"junk-without-separator": 1},
    )
    assert [row[0] for row in rows] == ["L21_V001", "L21_V002"]


def test_build_submission_ignores_pins_for_other_videos():
    import trake

    rows = trake.build_submission(
        _outcome(), max_rows=1, pinned_frames={"L30_V011|1": 2500}
    )
    assert rows[0][1] == (1000, 2000, 3000)


def test_build_submission_without_pins_unchanged():
    import trake

    with_empty = trake.build_submission(_outcome(), max_rows=5, pinned_frames={})
    with_none = trake.build_submission(_outcome(), max_rows=5, pinned_frames=None)
    assert with_empty == with_none


# --- Wiring guards (these are what let the original bug ship) ---


def _pin_event(demo):
    for config in demo.get_config_file()["dependencies"]:
        for target in config.get("targets", []):
            if config.get("js") and "pin" in str(config.get("js", "")).lower():
                return config
    return None


def test_pin_button_input_count_matches_handler_signature():
    import gradio as gr

    import trake_ui

    with gr.Blocks() as demo:
        trake_ui.build_trake_tab(trake_searcher=None)

    config = _pin_event(demo)
    assert config is not None, "pin button event not found"
    expected = len(inspect.signature(trake_ui.process_pin).parameters)
    assert len(config["inputs"]) == expected


def test_building_trake_tab_emits_no_gradio_argument_warning():
    import gradio as gr

    import trake_ui

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with gr.Blocks():
            trake_ui.build_trake_tab(trake_searcher=None)

    offenders = [
        str(w.message) for w in caught if "arguments for function" in str(w.message)
    ]
    assert offenders == []


def test_trake_tab_omits_duplicate_log_and_pinned_list():
    import gradio as gr

    import trake_ui

    with gr.Blocks() as demo:
        trake_ui.build_trake_tab(trake_searcher=None)

    config = demo.get_config_file()
    accordion_labels = {
        component["props"].get("label")
        for component in config["components"]
        if component["type"] == "accordion"
    }
    visible_text = "\n".join(
        str(component["props"].get("value", ""))
        for component in config["components"]
        if component["type"] != "state"
    )

    assert "Log thông tin kết quả (Chi tiết)" not in accordion_labels
    assert "Danh sách các Frame đã chốt" not in visible_text


def test_pinned_frames_stay_strictly_increasing():
    """A pin can name any frame; the submitted row still has to move forward in time."""
    import trake

    rows = trake.build_submission(
        _outcome(), max_rows=1, pinned_frames={pin_key("L21_V001", 2): 500}
    )
    frames = rows[0][1]
    assert list(frames) == sorted(frames)
    assert len(set(frames)) == len(frames)


def test_pinned_frame_beyond_video_is_clamped():
    import trake

    outcome = _outcome()
    rows = trake.build_submission(
        outcome, max_rows=1, pinned_frames={pin_key("L21_V001", 0): 99999}
    )
    assert max(rows[0][1]) <= outcome.videos[0].max_frame_idx
