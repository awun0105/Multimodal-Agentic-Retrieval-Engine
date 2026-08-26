"""Shared rendering helpers for selected keyframe details."""

from __future__ import annotations

import html
from typing import Any


def timestamp(seconds: float) -> str:
    total_milliseconds = max(0, round(float(seconds) * 1000))
    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{milliseconds:03d}"


def watch_at(url: str, seconds: float) -> str:
    if not url:
        return ""
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}t={max(0, int(seconds))}s"


def detail_markdown(details: Any) -> str:
    keyframe = details.keyframe
    video = details.video
    watch_url = watch_at(str(video.get("watch_url") or ""), keyframe["pts_time_sec"])
    watch_link = (
        f'<a href="{html.escape(watch_url, quote=True)}" target="_blank" '
        'rel="noopener noreferrer">Open video</a>'
        if watch_url
        else "N/A"
    )
    width = keyframe.get("width")
    height = keyframe.get("height")
    resolution = f"{width} x {height}" if width is not None and height is not None else "N/A"
    values = {
        "Keyframe ID": keyframe["keyframe_id"],
        "Video ID": keyframe["video_id"],
        "Collection": keyframe["collection_id"],
        "Keyframe no.": keyframe["keyframe_no"],
        "Frame index": keyframe["frame_idx"],
        "Timestamp": timestamp(keyframe["pts_time_sec"]),
        "FPS": f"{float(keyframe['fps']):.4g}",
        "Resolution": resolution,
        "Title": video.get("title") or "N/A",
        "Author": video.get("author") or "N/A",
        "Channel": video.get("channel_id") or "N/A",
        "Published": video.get("publish_date_iso") or video.get("publish_date_raw") or "N/A",
    }
    rows = [f"| {label} | {html.escape(str(value))} |" for label, value in values.items()]
    return "\n".join(["| Field | Value |", "|---|---|", *rows, f"| Source | {watch_link} |"])


def detection_rows(details: Any) -> list[list]:
    return [
        [
            row["entity"],
            round(float(row["score"]), 4),
            row["class_mid"],
            row["class_label"],
            round(float(row["ymin"]), 4),
            round(float(row["xmin"]), 4),
            round(float(row["ymax"]), 4),
            round(float(row["xmax"]), 4),
        ]
        for row in details.detections
    ]
