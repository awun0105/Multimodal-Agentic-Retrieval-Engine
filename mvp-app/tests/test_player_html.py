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


def test_player_renders_direct_frame_seek_controls():
    html = build_player(
        "L26_V306",
        local_path="/tmp/L26_V306.mp4",
        watch_url=None,
        pts_time_sec=11.7333,
        fps=30.0,
        player_id="probe-player",
    )

    assert 'id="probe-player-jump-frame"' in html
    assert 'type="number" min="0" step="1"' in html
    assert 'id="probe-player-jump-btn"' in html
    assert 'placeholder="Nhập frame"' in html
    assert 'aria-label="Nhảy tới frame"' in html
    assert "Đi tới Frame" in html
    assert html.index("<video") < html.index('id="probe-player-jump-frame"')


def test_player_disables_direct_seek_without_playable_source():
    html = build_player(
        "L26_V306",
        local_path=None,
        watch_url=None,
        pts_time_sec=11.7333,
        fps=30.0,
        player_id="probe-player",
    )

    assert 'id="probe-player-jump-frame"' in html
    assert html.count(" disabled") == 2


def test_head_ships_paused_direct_frame_seek_for_local_and_youtube():
    head = player_head_html()

    assert "__aiouSeekFrame" in head
    assert "seekTimeForFrame" in head
    assert "(frame + 0.5) / fps" in head
    assert "v.pause()" in head
    assert "p.pauseVideo()" in head
    assert "pauseAfterSeek" in head
    assert ".aiou-media" in head
    assert "aspect-ratio:16/9" in head
    assert "var(--input-background-fill,#374151)" in head
    assert "var(--button-primary-background-fill,#f97316)" in head


def test_youtube_loads_media_before_publishing_current_frame():
    head = player_head_html()

    assert "loadVideoById" in head
    assert "cueVideoById" not in head
    assert "finishInitialLoad" in head
    assert "getVideoLoadedFraction" in head
    assert "(ps === -1 || ps === 5) ? cfg.start : raw" not in head


def test_youtube_player_uses_responsive_media_frame():
    html = build_player(
        "L26_V306",
        local_path=None,
        watch_url="https://youtu.be/dQw4w9WgXcQ",
        pts_time_sec=11.7333,
        fps=30.0,
        player_id="probe-player",
    )

    assert '<div class="aiou-media"><div id="probe-player-yt"></div></div>' in html
