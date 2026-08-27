"""Parse raw search-box input into semantic text plus metadata scope.

Accepted inline grammar (comma-separated tokens, order-free):

    L26                  -> the whole collection
    L26_V306             -> every keyframe of that video, in canonical order
    L26_V306_049         -> exactly that keyframe
    L26_V306, 49         -> exactly that keyframe (video id + keyframe number)
    con ca, L26_V306     -> semantic query scoped to a video
    con ca, L26          -> semantic query scoped to a collection

Tokens matching none of the ID shapes are joined back into the semantic text,
so plain queries behave exactly as before. ID shapes were verified against the
released data: 100% of video_id match ^L\\d+_V\\d+$ and 100% of keyframe_id
match ^L\\d+_V\\d+_\\d{3}$ with the suffix equal to keyframe_no zero-padded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

COLLECTION_RE = re.compile(r"^L\d+$")
VIDEO_RE = re.compile(r"^L\d+_V\d+$")
KEYFRAME_ID_RE = re.compile(r"^(L\d+_V\d+)_(\d{1,3})$")
NUMBER_RE = re.compile(r"^\d{1,4}$")

USAGE_HINT = (
    "Cú pháp hợp lệ: 'L26' (collection) · 'L26_V306' (video) · "
    "'L26_V306_049' hoặc 'L26_V306, 49' (đúng 1 keyframe) · "
    "nhập nhiều keyframe/video ID cách nhau bằng dấu phẩy · "
    "'con cá, L26_V306' (search trong video)"
)


@dataclass(frozen=True)
class ParsedSearchQuery:
    """Result of parsing one search-box input."""

    semantic_text: str
    collections: tuple[str, ...] = ()
    video_ids: tuple[str, ...] = ()
    exact_keyframes: tuple[tuple[str, int], ...] = ()

    @property
    def has_scope(self) -> bool:
        return bool(self.collections or self.video_ids)

    @property
    def is_exact_keyframe(self) -> bool:
        return bool(self.exact_keyframes)

    @property
    def scope_label(self) -> str:
        parts = []
        if self.video_ids:
            parts.append(f"video {', '.join(self.video_ids)}")
        if self.collections:
            parts.append(f"collection {', '.join(self.collections)}")
        return " + ".join(parts)

    def describe(self) -> str:
        """Human-readable interpretation shown in the Status line."""
        if self.is_exact_keyframe:
            names = ", ".join(
                f"{video_id}_{keyframe_no:03d}"
                for video_id, keyframe_no in self.exact_keyframes
            )
            return f"đúng keyframe {names}"
        if self.has_scope:
            return self.scope_label
        return self.semantic_text


def parse_search_query(raw: str) -> ParsedSearchQuery:
    """Classify comma-separated tokens; raises ValueError on ambiguous input."""
    tokens = [token.strip() for token in str(raw or "").split(",")]
    tokens = [token for token in tokens if token]
    if not tokens:
        return ParsedSearchQuery("")

    texts: list[str] = []
    collections: list[str] = []
    videos: list[str] = []
    numbers: list[int] = []
    explicit_keyframes: list[tuple[str, int]] = []

    for token in tokens:
        keyframe_match = KEYFRAME_ID_RE.match(token)
        if keyframe_match:
            explicit_keyframes.append(
                (keyframe_match.group(1), int(keyframe_match.group(2)))
            )
        elif VIDEO_RE.match(token):
            videos.append(token)
        elif COLLECTION_RE.match(token):
            collections.append(token)
        elif NUMBER_RE.match(token):
            numbers.append(int(token))
        else:
            texts.append(token)

    # Exact-keyframe forms: many full IDs may be typed together, but they must
    # stand alone — mixing them with scopes or free text is ambiguous, so
    # refuse rather than guess.
    if explicit_keyframes or numbers:
        if explicit_keyframes and (videos or collections or texts or numbers):
            raise ValueError(
                "Keyframe chính xác không được kết hợp với scope/text khác. "
                f"{USAGE_HINT}"
            )
        if numbers:
            if len(numbers) > 1:
                raise ValueError(
                    f"Chỉ nhận MỘT 'video, số thứ tự' mỗi truy vấn. {USAGE_HINT}"
                )
            if len(videos) != 1 or collections or texts:
                raise ValueError(
                    f"'số thứ tự keyframe' chỉ dùng kèm đúng MỘT video ID. {USAGE_HINT}"
                )
            entries = [(videos[0], numbers[0])]
        else:
            entries = explicit_keyframes

        entries = tuple(dict.fromkeys(entries))
        return ParsedSearchQuery(
            semantic_text="",
            video_ids=tuple(dict.fromkeys(video for video, _no in entries)),
            exact_keyframes=entries,
        )

    return ParsedSearchQuery(
        semantic_text=" ".join(texts).strip(),
        collections=tuple(dict.fromkeys(collections)),
        video_ids=tuple(dict.fromkeys(videos)),
    )
