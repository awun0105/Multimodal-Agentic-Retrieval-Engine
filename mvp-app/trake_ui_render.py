"""Result rendering helpers for the TRAKE tab (kept out of trake_ui.py for LOC budget)."""

from __future__ import annotations

import html
from pathlib import Path

from schemas import TrakeOutcome


def _timestamp(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


def build_gallery_items(outcome: TrakeOutcome) -> list[tuple[str, str]]:
    """Flat (image_path, caption) list. Gradio serves these paths; markdown links do not."""
    items: list[tuple[str, str]] = []
    for rank, video in enumerate(outcome.videos, start=1):
        for event in video.events:
            if not Path(event.image_path).is_file():
                continue
            caption = (
                f"#{rank} {video.video_id} | event {event.event_index + 1} | "
                f"kf {event.keyframe_no} | {_timestamp(event.pts_time_sec)} | "
                f"frame {event.frame_idx} | {event.score:.4f}"
            )
            items.append((event.image_path, caption))
    return items


def build_video_blocks(outcome: TrakeOutcome) -> str:
    if not outcome.videos:
        return "No matching video sequences found."

    blocks = []
    for rank, video in enumerate(outcome.videos, start=1):
        header = (
            f"**#{rank} — {html.escape(video.video_id)}** "
            f"(score {video.total_score:.4f}) — {html.escape(video.title or 'N/A')}"
        )
        rows = [
            f"- event {event.event_index + 1}: keyframe {event.keyframe_no}, "
            f"frame {event.frame_idx}, {_timestamp(event.pts_time_sec)}, "
            f"fps {event.fps:g}, score {event.score:.4f}"
            for event in video.events
        ]
        blocks.append("\n".join([header, *rows]))
    return "\n\n".join(blocks)


def build_status_markdown(outcome: TrakeOutcome, elapsed_seconds: float) -> str:
    video_count = len(outcome.videos)
    lines = [f"Videos considered: {video_count} | Elapsed: {elapsed_seconds:.2f}s"]

    max_events = max((len(v.events) for v in outcome.videos), default=0)
    for event_index in range(max_events):
        best = max(
            (
                v.events[event_index].score
                for v in outcome.videos
                if event_index < len(v.events)
            ),
            default=None,
        )
        if best is not None:
            lines.append(f"Event {event_index + 1} best single score: {best:.4f}")
    return "\n\n".join(lines)

def render_video_player(video_id: str, video_path: str, pts_time_sec: float, fps: float = 25.0, player_id: str = "trake-player") -> str:
    """Render an HTML5 video player auto-seeked to the given timestamp without autoplay, and a live frame indicator."""
    return f"""
    <div style="text-align: center; margin-top: 1rem; border: 1px solid #ddd; padding: 10px; border-radius: 8px;">
        <h3>Video Player: {html.escape(video_id)}</h3>
        <p style="font-size: 1.1em; font-weight: bold; color: #d00;">
            Current Timestamp: <span id="{player_id}-time-display">{pts_time_sec:.3f}</span>s
            | Approx Frame: <span id="{player_id}-frame-display">{round(pts_time_sec * fps)}</span>
        </p>
        <video id="{player_id}" src="/gradio_api/file={video_path}#t={pts_time_sec}" controls style="width: 100%; max-height: 60vh;"
        ontimeupdate="document.getElementById('{player_id}-time-display').innerText = this.currentTime.toFixed(3); document.getElementById('{player_id}-frame-display').innerText = Math.round(this.currentTime * {fps});"
        ></video>
    </div>
    """


PREVIEW_SPREAD_SAMPLE = 8


def _frames_text(frames: tuple[int, ...], frame_index_base: int = 0) -> str:
    return ", ".join(str(frame + frame_index_base) for frame in frames)


def build_submission_preview_markdown(
    rows: list[tuple[str, tuple[int, ...]]],
    primary_count: int,
    pinned_counts: dict[str, int],
    frame_index_base: int = 0,
) -> str:
    """Rows 0..primary_count-1 are the real answers, one per video, best first.
    Everything after is jitter around them — labelled so nobody mistakes it for a result."""
    if not rows:
        return "Chưa có kết quả để xem trước."

    remainder = rows[primary_count:]
    lines = [
        "### Xem trước file nộp bài",
        "",
        f"Tổng **{len(rows)}** dòng — **{primary_count}** đáp án, "
        f"{len(remainder)} dòng rải tham khảo.",
        "",
        f"**Đáp án sẽ nộp** (dòng 1 là kết quả tốt nhất, {primary_count} video khác nhau):",
        "",
        "| # | Video | Frame | |",
        "|---|---|---|---|",
    ]
    for position, (video_id, frames) in enumerate(rows[:primary_count], start=1):
        pinned = pinned_counts.get(video_id, 0)
        marker = f"{pinned}/{len(frames)} chốt tay" if pinned else ""
        lines.append(
            f"| {position} | {html.escape(video_id)} | {_frames_text(frames, frame_index_base)} | {marker} |"
        )

    if remainder:
        lines += [
            "",
            f"**Dòng rải tham khảo** ({len(remainder)} dòng, lệch vài frame quanh đáp án trên):",
            "",
            "```csv",
        ]
        shown = remainder[:PREVIEW_SPREAD_SAMPLE]
        lines += [f"{video_id}, {_frames_text(frames, frame_index_base)}" for video_id, frames in shown]
        if len(remainder) > len(shown):
            lines.append(f"... còn {len(remainder) - len(shown)} dòng")
        lines.append("```")
    return "\n".join(lines)
