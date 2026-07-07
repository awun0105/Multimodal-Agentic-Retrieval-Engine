from __future__ import annotations

import json
import subprocess

from system1.media.probe import probe_video


class _Completed:
    def __init__(self, payload: dict[str, object]) -> None:
        self.stdout = json.dumps(payload)


def test_probe_video_prefers_packet_count_over_header_frames(monkeypatch, tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"placeholder")
    commands: list[list[str]] = []

    def fake_run(command, *, check, capture_output, text):  # noqa: ANN001
        commands.append(command)
        return _Completed(
            {
                "streams": [
                    {
                        "avg_frame_rate": "25/1",
                        "r_frame_rate": "25/1",
                        "nb_frames": "999",
                        "nb_read_packets": "1001",
                        "width": "1920",
                        "height": "1080",
                        "duration": "40.04",
                    }
                ]
            }
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    probe = probe_video(video_path)

    assert commands
    assert "-count_packets" in commands[0]
    assert any("nb_read_packets" in part for part in commands[0])
    assert probe.frame_count == 1001
    assert probe.frame_count_estimated is False
    assert probe.frame_count_method == "ffprobe_nb_read_packets"
    assert probe.fps_detected == 25.0
    assert probe.duration_seconds == 40.04
    assert probe.width == 1920
    assert probe.height == 1080


def test_probe_video_falls_back_to_header_frames(monkeypatch, tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"placeholder")

    def fake_run(command, *, check, capture_output, text):  # noqa: ANN001, ARG001
        return _Completed(
            {
                "streams": [
                    {
                        "avg_frame_rate": "30/1",
                        "r_frame_rate": "30/1",
                        "nb_frames": "300",
                        "width": "1280",
                        "height": "720",
                        "duration": "10",
                    }
                ]
            }
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    probe = probe_video(video_path)

    assert probe.frame_count == 300
    assert probe.frame_count_estimated is False
    assert probe.frame_count_method == "ffprobe_nb_frames"


def test_probe_video_estimates_frame_count_with_warning(monkeypatch, tmp_path, caplog):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"placeholder")

    def fake_run(command, *, check, capture_output, text):  # noqa: ANN001, ARG001
        return _Completed(
            {
                "streams": [
                    {
                        "avg_frame_rate": "30000/1001",
                        "r_frame_rate": "30000/1001",
                        "width": "640",
                        "height": "360",
                        "duration": "10.0",
                    }
                ]
            }
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    probe = probe_video(video_path)

    assert probe.frame_count == 300
    assert probe.frame_count_estimated is True
    assert probe.frame_count_method == "estimated_from_duration_and_fps"
    assert "potential Frame ID drift" in caplog.text
