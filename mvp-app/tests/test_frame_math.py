import pytest

from frame_math import calculated_frame, normalize_time, validate_frame


@pytest.mark.parametrize(
    ("pts", "fps", "expected"),
    [
        # round() would give 352 here — the regression the plan calls out.
        (11.7333, 30, 351),
        (0.0333333, 30, 0),
        (33.667, 29.97, 1008),
    ],
)
def test_calculated_frame_matches_organizer_floor_rule(pts, fps, expected):
    assert calculated_frame(pts, fps) == expected


def test_normalize_time_mirrors_js_toprecision6():
    assert normalize_time(11.733333333) == 11.7333
    assert normalize_time(0.033333333) == 0.0333333
    assert normalize_time(5.0) == 5.0


@pytest.mark.parametrize("value", [None, "abc", "", float("nan"), float("inf")])
def test_calculated_frame_rejects_unusable_input(value):
    assert calculated_frame(value, 30) is None


@pytest.mark.parametrize("fps", [0, -30, None, "abc"])
def test_calculated_frame_rejects_non_positive_fps(fps):
    assert calculated_frame(10.0, fps) is None


def test_calculated_frame_clamps_negative_time_to_zero():
    assert calculated_frame(-0.5, 30) == 0


def test_validate_frame_prefers_valid_player_value():
    assert validate_frame("351", 90) == 351
    assert validate_frame(351, 90) == 351


@pytest.mark.parametrize("bad", [None, "abc", "-2", -2, 12.9])
def test_validate_frame_falls_back_when_malformed(bad):
    assert validate_frame(bad, 90) == 90
