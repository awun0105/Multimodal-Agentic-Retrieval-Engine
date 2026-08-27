"""Parse and validate YouTube URLs into embeddable video ids.

Accepted forms: youtube.com/watch?v=ID, youtu.be/ID, /embed/ID, /shorts/ID.
Anything else returns None so callers degrade to the keyframe-only player.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

_VIDEO_ID = r"[\w-]{11}"


def extract_youtube_id(url: str | None) -> str | None:
    """Return the 11-character video id, or None for invalid/non-YouTube URLs."""
    if not url:
        return None
    try:
        parsed = urlparse(str(url).strip())
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host.removeprefix("www.")

    if host == "youtu.be":
        match = re.fullmatch(rf"/({_VIDEO_ID})(?:[/?].*)?", parsed.path)
        return match.group(1) if match else None

    if host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
        if parsed.path == "/watch":
            values = parse_qs(parsed.query).get("v", [])
            if values and re.fullmatch(_VIDEO_ID, values[0]):
                return values[0]
            return None
        match = re.fullmatch(rf"/(?:embed|shorts)/({_VIDEO_ID})(?:/.*)?", parsed.path)
        if match:
            return match.group(1)
    return None


def is_youtube_url(url: str | None) -> bool:
    return extract_youtube_id(url) is not None
