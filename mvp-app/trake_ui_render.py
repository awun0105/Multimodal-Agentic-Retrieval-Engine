"""Result rendering helpers for the TRAKE tab (kept out of trake_ui.py for LOC budget)."""

from __future__ import annotations

import html
from pathlib import Path

from schemas import TrakeOutcome


def _timestamp(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


def build_gallery_items_slice(videos: list, start_rank: int) -> list[tuple[str, str]]:
    """Flat (image_path, caption) list. Gradio serves these paths; markdown links do not."""
    items: list[tuple[str, str]] = []
    for rank, video in enumerate(videos, start=start_rank):
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


def build_video_blocks_slice(videos: list, start_rank: int) -> str:
    if not videos:
        return "No matching video sequences found on this page."

    blocks = []
    for rank, video in enumerate(videos, start=start_rank):
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
