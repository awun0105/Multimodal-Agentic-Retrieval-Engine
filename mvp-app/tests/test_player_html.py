"""Regression guard for the native seek fragment and boot plumbing."""

from player import build_player, player_head_html


def test_local_player_starts_at_keyframe_without_javascript(tmp_path):
    """The #t= media fragment seeks natively even if boot JS never runs."""
    video = tmp_path / "L26_V306.mp4"
    video.write_bytes(b"mp4")
    html = build_player(
        "L26_V306",
        local_path=str(video),
        watch_url=None,
        pts_time_sec=11.7333,
        fps=30.0,
        player_id="probe-player",
        pin_button_id="probe-pin",
    )
    assert "#t=11.7333" in html
    assert 'data-aiou' not in html  # config travels via data-player only
    assert 'data-player=' in html


def test_head_ships_mutation_observer_boot():
    head = player_head_html()
    assert "__aiouScanPlayers" in head
    assert "MutationObserver" in head
    assert "dataset.booted" in head


def test_youtube_loads_media_before_publishing_current_frame():
    head = player_head_html()

    assert "loadVideoById" in head
    assert "cueVideoById" not in head
    assert "finishInitialLoad" in head
    assert "getVideoLoadedFraction" in head
    assert "(ps === -1 || ps === 5) ? cfg.start : raw" not in head
