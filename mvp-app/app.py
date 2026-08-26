"""Standalone Gradio application for filtered keyframe retrieval."""

from __future__ import annotations

import html
import logging
import os
from dataclasses import replace
from pathlib import Path

try:
    import spaces
except ImportError:

    class _LocalSpaces:
        @staticmethod
        def GPU(function=None, **_kwargs):
            if function is not None:
                return function

            def decorator(callback):
                return callback

            return decorator

    spaces = _LocalSpaces()  # type: ignore[assignment]

import gradio as gr

from clip import CLIPSearcher
from clusterer import ImageIndexer
from database_utils import RuntimePaths, prepare_runtime
from db import SearchMechanism
from query_parser import parse_search_query
from schemas import SearchFilters
from trake import SUBMISSION_MAX_ROWS, TrakeSearcher, format_submission
from trake_submission import export_csv_file
from trake_ui import build_trake_tab
from trake_ui_render import render_video_player
from translation import QueryTranslator
from video_locator import get_video_path

logger = logging.getLogger(__name__)

APP_CSS = """
body {
    overflow-y: auto !important;
}

/* Gallery phải tự giãn theo nội dung */
#keyframe-gallery {
    margin-top: 0.25rem;
    height: auto !important;
    max-height: none !important;
    overflow: visible !important;
}

/* Gradio đặt scroll ở wrapper bên trong */
#keyframe-gallery .grid-wrap {
    height: auto !important;
    max-height: none !important;
    overflow-y: visible !important;
    overflow-x: visible !important;
}

/* Grid tự lấy chiều cao của 2 hàng */
#keyframe-gallery .grid-container {
    height: auto !important;
    max-height: none !important;
    overflow: visible !important;
    align-content: start !important;
}

#selected-keyframe {
    min-height: 400px;
}

#selected-keyframe img {
    object-fit: contain !important;
}

@media (max-width: 600px) {
    #app-title {
        margin-top: 3.5rem;
    }

    #selected-keyframe {
        min-height: 260px;
    }
}
"""

RESULT_FIELD_CHOICES = [
    ("All fields", "all"),
    ("Keyframe ID", "keyframe_id"),
    ("Video ID", "video_id"),
    ("Collection", "collection_id"),
    ("Title", "title"),
    ("Author", "author"),
    ("Keyframe No.", "keyframe_no"),
    ("Frame Index", "frame_idx"),
]


def _timestamp(seconds: float) -> str:
    total_milliseconds = max(0, round(float(seconds) * 1000))
    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{milliseconds:03d}"


def _watch_at(url: str, seconds: float) -> str:
    if not url:
        return ""
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}t={max(0, int(seconds))}s"


def _keyframe_directory(data_root: Path) -> Path:
    return (data_root / "keyframes").resolve()



def _generate_preview_text(rows: list[dict], pinned: dict = None):
    pinned = pinned or {}
    if not rows:
        return "Chưa có kết quả để xem trước."

    submission_rows = []

    # 1. Promote pinned frames to the top
    for vid_id, frame_idx in pinned.items():
        submission_rows.append((vid_id, (frame_idx,)))

    # 2. Append remaining AI predictions
    for r in rows:
        video_id = r["video_id"]
        frame_idx = r["frame_idx"]

        # If this EXACT frame was pinned, skip it (we already put it at the top)
        if pinned.get(video_id) == frame_idx:
            continue

        submission_rows.append((video_id, (frame_idx,)))

    # The contest accepts at most SUBMISSION_MAX_ROWS lines per file.
    submission_rows = submission_rows[:SUBMISSION_MAX_ROWS]

    return format_submission(submission_rows)


def _detail_markdown(details) -> str:
    keyframe = details.keyframe
    video = details.video
    watch_url = _watch_at(str(video.get("watch_url") or ""), keyframe["pts_time_sec"])
    watch_link = (
        f'<a href="{html.escape(watch_url, quote=True)}" target="_blank" '
        'rel="noopener noreferrer">Open video</a>'
        if watch_url
        else "N/A"
    )
    values = {
        "Keyframe ID": keyframe["keyframe_id"],
        "Video ID": keyframe["video_id"],
        "Collection": keyframe["collection_id"],
        "Keyframe no.": keyframe["keyframe_no"],
        "Frame index": keyframe["frame_idx"],
        "Timestamp": _timestamp(keyframe["pts_time_sec"]),
        "FPS": f"{float(keyframe['fps']):.4g}",
        "Resolution": f"{keyframe['width']} x {keyframe['height']}",
        "Title": video.get("title") or "N/A",
        "Author": video.get("author") or "N/A",
        "Channel": video.get("channel_id") or "N/A",
        "Published": video.get("publish_date_iso") or video.get("publish_date_raw") or "N/A",
    }
    rows = [f"| {label} | {html.escape(str(value))} |" for label, value in values.items()]
    return "\n".join(["| Field | Value |", "|---|---|", *rows, f"| Source | {watch_link} |"])


def _detection_rows(details) -> list[list]:
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


class SearchController:
    """UI callbacks bound to one immutable runtime release."""

    def __init__(self, search_mechanism: SearchMechanism, page_size: int) -> None:
        self.search_mechanism = search_mechanism
        self.page_size = page_size

    def page_payload(
        self,
        rows: list[dict],
        page: int,
        original_count: int | None = None,
    ):
        rows = rows or []
        total_pages = max(1, (len(rows) + self.page_size - 1) // self.page_size)
        page = max(0, min(int(page), total_pages - 1))
        start = page * self.page_size
        page_rows = rows[start : start + self.page_size]
        rendered_rows = [row for row in page_rows if Path(row["image_path"]).is_file()]
        gallery = [
            (
                row["image_path"],
                f"{row['keyframe_id']} | {_timestamp(row['pts_time_sec'])} | {row['score']:.4f}",
            )
            for row in rendered_rows
        ]
        if original_count is not None and original_count != len(rows):
            count_label = f"{len(rows)} of {original_count} results"
        else:
            count_label = f"{len(rows)} results"
        label = f"Page {page + 1} / {total_pages} | {count_label}"
        return (
            gallery,
            rendered_rows,
            page,
            label,
            gr.update(interactive=page > 0),
            gr.update(interactive=page + 1 < total_pages),
        )

    @staticmethod
    def _search_filters(
        collections,
        video_id,
        object_entities,
        object_match_mode,
        minimum_object_confidence,
        author,
        publish_date_from,
        publish_date_to,
    ) -> SearchFilters:
        return SearchFilters(
            collections=tuple(collections or ()),
            video_id=video_id or None,
            object_entities=tuple(object_entities or ()),
            object_match_mode=str(object_match_mode).lower(),
            minimum_object_confidence=float(minimum_object_confidence),
            author=author or None,
            publish_date_from=publish_date_from or None,
            publish_date_to=publish_date_to or None,
        )

    def _run_search(
        self,
        query,
        top_k,
        query_language,
        collections,
        video_id,
        object_entities,
        object_match_mode,
        minimum_object_confidence,
        author,
        publish_date_from,
        publish_date_to,
        *,
        translate_vietnamese: bool | None = None,
    ) -> tuple[list[dict], str]:
        parsed = parse_search_query(query)
        mechanism = self.search_mechanism

        # Fast paths: pure metadata input never touches CLIP or translation.
        if parsed.is_exact_keyframe:
            rows = []
            missing = []
            for exact_video, exact_no in parsed.exact_keyframes:
                row = mechanism.find_exact_keyframe(exact_video, exact_no)
                if row is None:
                    missing.append(f"{exact_video}_{exact_no:03d}")
                else:
                    rows.append(row.to_dict())
            parts = []
            if rows:
                parts.append(
                    "đúng keyframe " + ", ".join(row["keyframe_id"] for row in rows)
                )
            if missing:
                parts.append("Không tìm thấy: " + ", ".join(missing))
            return rows, "Metadata: " + " | ".join(parts)

        scope_collections = tuple(
            dict.fromkeys([*(collections or ()), *parsed.collections])
        )
        dropdown_video = video_id or None
        scope_videos = tuple(
            dict.fromkeys([*parsed.video_ids, *([dropdown_video] if dropdown_video else [])])
        )

        if parsed.has_scope and not parsed.semantic_text:
            # A typed video may also sit inside a typed collection — keep the
            # first occurrence so nothing shows up twice in the gallery.
            rows = []
            seen_vector_ids: set[int] = set()

            def _extend(results):
                for result in results:
                    if result.vector_id not in seen_vector_ids:
                        seen_vector_ids.add(result.vector_id)
                        rows.append(result)

            for video_id_item in parsed.video_ids:
                _extend(mechanism.get_video_keyframes(video_id_item))
            for collection_id in parsed.collections:
                _extend(mechanism.get_collection_keyframes(collection_id))
            return (
                [result.to_dict() for result in rows],
                f"Metadata: {parsed.scope_label} — {len(rows)} keyframes",
            )

        filters = self._search_filters(
            scope_collections,
            None,
            object_entities,
            object_match_mode,
            minimum_object_confidence,
            author,
            publish_date_from,
            publish_date_to,
        )
        filters = replace(filters, video_ids=scope_videos)
        outcome = self.search_mechanism.search_by_text(
            parsed.semantic_text or query,
            int(top_k),
            str(query_language).lower(),
            filters,
            translate_vietnamese=translate_vietnamese,
        )
        rows = [result.to_dict() for result in outcome.results]
        if not outcome.query.translation_enabled:
            translation_status = "Off"
        elif outcome.query.warning:
            translation_status = "Failed"
        else:
            translation_status = "On"
        status = (
            f"Found {len(rows)} results | Translation: {translation_status} | "
            f"Original query: {outcome.query.original_query} | "
            f"CLIP query: {outcome.query.clip_query}"
        )
        if parsed.has_scope:
            status = f"{status} | Scope: {parsed.scope_label}"
        if outcome.query.warning:
            status = f"{status} | {outcome.query.warning}"
        return rows, status

    @staticmethod
    def _refinement_updates(rows: list[dict]):
        collections = sorted({str(row["collection_id"]) for row in rows})
        videos = sorted({str(row["video_id"]) for row in rows})
        authors = sorted({str(row.get("author") or "") for row in rows} - {""})
        return (
            gr.update(choices=collections, value=[]),
            gr.update(choices=videos, value=[]),
            gr.update(choices=authors, value=[]),
        )

    @staticmethod
    def _matches_within_results(row: dict, query: str, field: str) -> bool:
        needle = str(query or "").strip().casefold()
        if not needle:
            return True
        if field in {"keyframe_no", "frame_idx"}:
            try:
                return int(row[field]) == int(needle)
            except ValueError as exc:
                label = "Keyframe No." if field == "keyframe_no" else "Frame Index"
                raise ValueError(f"{label} must be an integer") from exc
        if field == "all":
            values = (
                row.get("keyframe_id"),
                row.get("video_id"),
                row.get("collection_id"),
                row.get("title"),
                row.get("author"),
                row.get("keyframe_no"),
                row.get("frame_idx"),
            )
            return any(needle in str(value or "").casefold() for value in values)
        return needle in str(row.get(field) or "").casefold()

    def _refined_rows(
        self,
        rows: list[dict],
        within_query,
        within_field,
        collections,
        videos,
        authors,
        minimum_score,
    ) -> list[dict]:
        selected_collections = set(collections or ())
        selected_videos = set(videos or ())
        selected_authors = set(authors or ())
        threshold = float(minimum_score)
        field = str(within_field or "all")
        return [
            row
            for row in rows or []
            if (not selected_collections or row["collection_id"] in selected_collections)
            and (not selected_videos or row["video_id"] in selected_videos)
            and (not selected_authors or row.get("author") in selected_authors)
            and float(row["score"]) >= threshold
            and self._matches_within_results(row, within_query, field)
        ]

    def search_keyframes(
        self,
        query,
        top_k,
        query_language,
        collections,
        video_id,
        object_entities,
        object_match_mode,
        minimum_object_confidence,
        author,
        publish_date_from,
        publish_date_to,
    ):
        try:
            rows, status = self._run_search(
                query,
                top_k,
                query_language,
                collections,
                video_id,
                object_entities,
                object_match_mode,
                minimum_object_confidence,
                author,
                publish_date_from,
                publish_date_to,
            )
            gallery, _page_rows, page, label, previous_update, next_update = (
                self.page_payload(rows, 0)
            )
            return (
                gallery,
                rows,
                page,
                status,
                label,
                previous_update,
                next_update,
                None,
                "<p style='color: #666; font-style: italic;'>Select a keyframe to play video.</p>",
                "Select a keyframe to view metadata",
                [],
            )
        except Exception as exc:
            logger.exception("Keyframe search failed")
            return (
                [],
                [],
                0,
                f"Error: {exc}",
                "Page 1 / 1 | 0 results",
                gr.update(interactive=False),
                gr.update(interactive=False),
                None,
                "<p style='color: #666; font-style: italic;'>Select a keyframe to play video.</p>",
                "Select a keyframe to view metadata",
                [],
            )

    def search_keyframes_v2(
        self,
        query,
        top_k,
        translate_vietnamese,
        collections,
        video_id,
        object_entities,
        object_match_mode,
        minimum_object_confidence,
        author,
        publish_date_from,
        publish_date_to,
    ):
        try:
            rows, status = self._run_search(
                query,
                top_k,
                "auto",
                collections,
                video_id,
                object_entities,
                object_match_mode,
                minimum_object_confidence,
                author,
                publish_date_from,
                publish_date_to,
                translate_vietnamese=bool(translate_vietnamese),
            )
            gallery, page_rows, page, label, previous_update, next_update = (
                self.page_payload(rows, 0)
            )
            collection_update, video_update, author_update = self._refinement_updates(rows)
            return (
                gallery,
                rows,
                # Separate list objects: the two states are refined independently.
                list(rows),
                page_rows,
                page,
                status,
                label,
                previous_update,
                next_update,
                None,
                "<p style='color: #666; font-style: italic;'>Select a keyframe to play video.</p>",
                "Select a keyframe to view metadata",
                [],
                collection_update,
                video_update,
                author_update,
                -1.0,
                "",
                "all",
                f"Refine current Top K results | {len(rows)} results",
            )
        except Exception as exc:
            logger.exception("Keyframe search failed")
            empty_update = gr.update(choices=[], value=[])
            return (
                [],
                [],
                [],
                [],
                0,
                f"Error: {exc}",
                "Page 1 / 1 | 0 results",
                gr.update(interactive=False),
                gr.update(interactive=False),
                None,
                "<p style='color: #666; font-style: italic;'>Select a keyframe to play video.</p>",
                "Select a keyframe to view metadata",
                [],
                empty_update,
                empty_update,
                empty_update,
                -1.0,
                "",
                "all",
                "Refine current Top K results | 0 results",
            )

    def refine_results(
        self,
        original_rows,
        current_rows,
        within_query,
        within_field,
        collections,
        videos,
        authors,
        minimum_score,
    ):
        try:
            rows = self._refined_rows(
                original_rows,
                within_query,
                within_field,
                collections,
                videos,
                authors,
                minimum_score,
            )
            message = (
                f"Refine current Top K results | {len(rows)} of "
                f"{len(original_rows or [])} results"
            )
        except ValueError as exc:
            rows = current_rows or []
            message = f"Refine error: {exc}"
        gallery, page_rows, page, label, previous_update, next_update = self.page_payload(
            rows,
            0,
            len(original_rows or []),
        )
        return (
            gallery,
            rows,
            page_rows,
            page,
            label,
            previous_update,
            next_update,
            None,
                "<p style='color: #666; font-style: italic;'>Select a keyframe to play video.</p>",
                "Select a keyframe to view metadata",
                [],
            message,
        )

    def clear_within_results(
        self,
        original_rows,
        current_rows,
        within_field,
        collections,
        videos,
        authors,
        minimum_score,
    ):
        return (
            "",
            *self.refine_results(
                original_rows,
                current_rows,
                "",
                within_field,
                collections,
                videos,
                authors,
                minimum_score,
            ),
        )

    def clear_all_refinements(self, original_rows):
        rows = original_rows or []
        gallery, page_rows, page, label, previous_update, next_update = self.page_payload(
            rows,
            0,
        )
        return (
            gallery,
            rows,
            page_rows,
            page,
            label,
            previous_update,
            next_update,
            None,
                "<p style='color: #666; font-style: italic;'>Select a keyframe to play video.</p>",
                "Select a keyframe to view metadata",
                [],
            f"Refine current Top K results | {len(rows)} results",
            "",
            "all",
            [],
            [],
            [],
            -1.0,
        )

    def previous_page(self, rows, original_rows, page):
        return self._change_page(rows, original_rows, int(page) - 1)

    def next_page(self, rows, original_rows, page):
        return self._change_page(rows, original_rows, int(page) + 1)

    def _change_page(self, rows, original_rows, page):
        payload = self.page_payload(rows, page, len(original_rows or []))
        return (
            *payload,
            None,
                "<p style='color: #666; font-style: italic;'>Select a keyframe to play video.</p>",
                "Select a keyframe to view metadata",
                [],
        )

    def select_keyframe(self, page_rows, evt: gr.SelectData):
        if not page_rows or evt.index is None:
            return None, "<p style='color: #666; font-style: italic;'>Select a keyframe to play video.</p>", "Select a keyframe to view metadata", []
        local_index = int(evt.index[0] if isinstance(evt.index, tuple) else evt.index)
        if local_index < 0 or local_index >= len(page_rows):
            return None, "<p style='color: #666; font-style: italic;'>Select a keyframe to play video.</p>", "Selected result is no longer available", []
        row = page_rows[local_index]
        details = self.search_mechanism.get_keyframe_details(row["keyframe_id"])

        video_html = "<p style='color: #666; font-style: italic;'>Video file not found in VIDEO_ROOT.</p>"
        video_id = details.keyframe["video_id"]
        pts = float(details.keyframe["pts_time_sec"])
        fps = float(details.video.get("fps", 25.0))
        video_path = get_video_path(video_id)
        if video_path:
            video_html = render_video_player(video_id, video_path, pts, fps, player_id="query-text-player")

        return (row["image_path"], video_html, _detail_markdown(details), _detection_rows(details),
                gr.update(interactive=bool(video_path)), gr.update(interactive=bool(video_path)), gr.update(interactive=bool(video_path)),
                fps, video_id, int(details.keyframe["frame_idx"]))

    def details_api(self, keyframe_id: str):
        details = self.search_mechanism.get_keyframe_details(keyframe_id)
        return {
            "keyframe": details.keyframe,
            "video": details.video,
            "detections": list(details.detections),
        }


_search_controller: SearchController | None = None
_keyframes_root: Path | None = None


@spaces.GPU(duration=120)
def search_keyframes_gpu(
    query,
    top_k,
    query_language,
    collections,
    video_id,
    object_entities,
    object_match_mode,
    minimum_object_confidence,
    author,
    publish_date_from,
    publish_date_to,
):
    """Run CLIP retrieval without passing unpicklable runtime state to ZeroGPU."""
    if _search_controller is None:
        raise RuntimeError("Search controller has not been initialized")
    return _search_controller.search_keyframes(
        query,
        top_k,
        query_language,
        collections,
        video_id,
        object_entities,
        object_match_mode,
        minimum_object_confidence,
        author,
        publish_date_from,
        publish_date_to,
    )


@spaces.GPU(duration=120)
def search_keyframes_gpu_v2(
    query,
    top_k,
    translate_vietnamese,
    collections,
    video_id,
    object_entities,
    object_match_mode,
    minimum_object_confidence,
    author,
    publish_date_from,
    publish_date_to,
):
    """Run the boolean-translation search flow on ZeroGPU."""
    if _search_controller is None:
        raise RuntimeError("Search controller has not been initialized")
    return _search_controller.search_keyframes_v2(
        query,
        top_k,
        translate_vietnamese,
        collections,
        video_id,
        object_entities,
        object_match_mode,
        minimum_object_confidence,
        author,
        publish_date_from,
        publish_date_to,
    )


def build_app(
    search_mechanism: SearchMechanism,
    *,
    page_size: int = 10,
    trake_searcher: TrakeSearcher | None = None,
) -> gr.Blocks:
    """Construct the Gradio UI and bind it to a prepared search mechanism."""
    global _search_controller

    options = search_mechanism.filter_options()
    controller = SearchController(search_mechanism, page_size)
    _search_controller = controller

    with gr.Blocks(css=APP_CSS) as webui:
        gr.Markdown("## AIOU", elem_id="app-title")
        with gr.Tabs():
            with gr.Tab("Query Text"):
                original_results_state = gr.State([])
                visible_results_state = gr.State([])
                page_rows_state = gr.State([])
                page_state = gr.State(0)

                # One visual search panel: query, pre-search filters, and the
                # Search button share a bordered Group so the filters cannot
                # be overlooked behind a collapsed accordion.
                with gr.Group():
                    with gr.Row(equal_height=True):
                        query = gr.Textbox(
                            label="Query",
                            placeholder=(
                                "Describe the keyframe you want to find — hoặc nhập "
                                "L26 · L26_V306 · L26_V306_049 · 'con cá, L26'"
                            ),
                            scale=5,
                        )
                        translate_vietnamese = gr.Checkbox(
                            label="Translate Vietnamese query to English",
                            value=True,
                            info="Off: direct multilingual search. On: NLLB translation before search.",
                            scale=2,
                        )
                        top_k = gr.Slider(
                            label="Top K",
                            minimum=1,
                            maximum=200,
                            step=1,
                            value=100,
                            scale=2,
                        )

                    gr.Markdown(
                        "*Bộ lọc (tuỳ chọn) — được áp dụng ngay khi bấm Search*"
                    )

                    with gr.Row():
                        collections = gr.Dropdown(
                            label="Collections",
                            choices=options["collections"],
                            multiselect=True,
                        )
                        video_id = gr.Dropdown(
                            label="Video ID",
                            choices=[("All videos", ""), *options["videos"]],
                            value="",
                            filterable=True,
                        )
                        author = gr.Dropdown(
                            label="Author / Channel",
                            choices=[("All authors", ""), *options["authors"]],
                            value="",
                            filterable=True,
                        )
                    with gr.Row():
                        object_entities = gr.Dropdown(
                            label="Objects",
                            choices=options["objects"],
                            multiselect=True,
                            filterable=True,
                            scale=4,
                        )
                        object_match_mode = gr.Radio(
                            label="Object match",
                            choices=[("Any", "any"), ("All", "all")],
                            value="any",
                            scale=1,
                        )
                        minimum_object_confidence = gr.Slider(
                            label="Minimum confidence",
                            minimum=0.3,
                            maximum=1.0,
                            step=0.05,
                            value=0.3,
                            scale=2,
                        )
                    with gr.Row():
                        publish_date_from = gr.Textbox(label="Published from", placeholder="YYYY-MM-DD")
                        publish_date_to = gr.Textbox(label="Published to", placeholder="YYYY-MM-DD")

                    search_button = gr.Button("Search", variant="primary")
                status = gr.Textbox(label="Status", value="Ready", interactive=False)

                with gr.Accordion("Refine current Top K results", open=False):
                    with gr.Row(equal_height=True):
                        within_results_query = gr.Textbox(
                            label="Search within results",
                            placeholder="Filter the current Top K results",
                            scale=5,
                        )
                        within_results_field = gr.Dropdown(
                            label="Field",
                            choices=RESULT_FIELD_CHOICES,
                            value="all",
                            scale=2,
                        )
                        filter_results_button = gr.Button("Filter", scale=1)
                        clear_within_button = gr.Button("Clear", scale=1)

                    refine_status = gr.Markdown("Refine current Top K results | 0 results")
                    with gr.Row():
                        refine_collections = gr.Dropdown(
                            label="Result collections",
                            choices=[],
                            multiselect=True,
                        )
                        refine_videos = gr.Dropdown(
                            label="Result video IDs",
                            choices=[],
                            multiselect=True,
                            filterable=True,
                        )
                        refine_authors = gr.Dropdown(
                            label="Result authors",
                            choices=[],
                            multiselect=True,
                            filterable=True,
                        )
                    with gr.Row():
                        minimum_result_score = gr.Slider(
                            label="Minimum similarity score",
                            minimum=-1.0,
                            maximum=1.0,
                            step=0.01,
                            value=-1.0,
                            scale=4,
                        )
                        clear_refinements_button = gr.Button("Clear all refinements", scale=1)

                gallery = gr.Gallery(
                    label="Keyframes",
                    show_label=True,
                    columns=5,
                    rows=2,
                    height="auto",
                    object_fit="contain",
                    allow_preview=False,
                    preview=False,
                    elem_id="keyframe-gallery",
                )
                with gr.Row():
                    previous_button = gr.Button("Previous", interactive=False)
                    page_label = gr.Textbox(
                        value="Page 1 / 1 | 0 results",
                        show_label=False,
                        interactive=False,
                    )
                    next_button = gr.Button("Next", interactive=False)

                with gr.Row(equal_height=False):
                    with gr.Column(scale=3):
                        with gr.Tabs():
                            with gr.Tab("Image Details"):
                                detail_image = gr.Image(
                                    label="Selected keyframe",
                                    interactive=False,
                                    height=420,
                                    elem_id="selected-keyframe",
                                )
                            with gr.Tab("Video Player"):
                                detail_video = gr.HTML(
                                    value="<p style='color: #666; font-style: italic;'>Select a keyframe to play video.</p>",
                                    elem_id="query-text-player-container",
                                )
                                with gr.Row():
                                    prev_btn = gr.Button("Prev Frame", interactive=False)
                                    next_btn = gr.Button("Next Frame", interactive=False)
                                    pin_btn = gr.Button("Chốt Frame (Đẩy lên Top)", interactive=False, variant="primary")
                                    clear_pins_btn = gr.Button("Gỡ hết frame đã chốt")
                                pinned_frames_state = gr.State({})

                    with gr.Column(scale=2):
                        detail_metadata = gr.Markdown("Select a keyframe to view metadata")
                detections = gr.Dataframe(
                    headers=["Object", "Score", "MID", "Label", "ymin", "xmin", "ymax", "xmax"],
                    datatype=["str", "number", "str", "number", "number", "number", "number", "number"],
                    label="Detected objects",
                    interactive=False,
                )

                with gr.Column(visible=False):
                    legacy_query_language = gr.Dropdown(
                        label="Language",
                        choices=[("Auto", "auto"), ("English", "english"), ("Vietnamese", "vietnamese")],
                        value="auto",
                    )
                    legacy_search_button = gr.Button("Legacy Search API")
                    api_keyframe_id = gr.Textbox()
                    api_details = gr.JSON()
                    api_details_button = gr.Button("Metadata API")

                    current_time_box = gr.Textbox(visible=False, elem_id="qt-current-time")
                    current_fps_box = gr.Number(visible=False, elem_id="qt-current-fps", value=25.0)
                    current_video_id_box = gr.Textbox(visible=False, elem_id="qt-current-video-id")
                    current_kf_frame_box = gr.Number(visible=False, elem_id="qt-current-kf-frame", value=0)


                gr.Markdown("---")
                gr.Markdown("### Xem trước file nộp bài (Textual KIS)")
                with gr.Row():
                    export_filename = gr.Textbox(label="Tên file export", value="query-1-kis.csv", max_lines=1)
                    export_button = gr.Button("Export submission file")
                    submission_file = gr.File(label="Submission file", interactive=False, height=80, visible=False)
                preview_textbox = gr.Textbox(label="Nội dung file nộp (Có thể chỉnh sửa thủ công)", lines=15, max_lines=50)

                legacy_search_outputs = [
                    gallery,
                    original_results_state,
                    page_state,
                    status,
                    page_label,
                    previous_button,
                    next_button,
                    detail_image,
                    detail_video,
                    detail_metadata,
                    detections,
                ]
                legacy_search_inputs = [
                    query,
                    top_k,
                    legacy_query_language,
                    collections,
                    video_id,
                    object_entities,
                    object_match_mode,
                    minimum_object_confidence,
                    author,
                    publish_date_from,
                    publish_date_to,
                ]

                search_inputs_v2 = [
                    query,
                    top_k,
                    translate_vietnamese,
                    collections,
                    video_id,
                    object_entities,
                    object_match_mode,
                    minimum_object_confidence,
                    author,
                    publish_date_from,
                    publish_date_to,
                ]
                search_outputs_v2 = [
                    gallery,
                    original_results_state,
                    visible_results_state,
                    page_rows_state,
                    page_state,
                    status,
                    page_label,
                    previous_button,
                    next_button,
                    detail_image,
                    detail_video,
                    detail_metadata,
                    detections,
                    refine_collections,
                    refine_videos,
                    refine_authors,
                    minimum_result_score,
                    within_results_query,
                    within_results_field,
                    refine_status,
                ]
                search_button.click(
                    fn=search_keyframes_gpu_v2,
                    inputs=search_inputs_v2,
                    outputs=search_outputs_v2,
                    api_name="search_keyframes_v2",
                )
                query.submit(
                    fn=search_keyframes_gpu_v2,
                    inputs=search_inputs_v2,
                    outputs=search_outputs_v2,
                    api_name=False,
                )



                pinned_frames_state.change(
                    fn=_generate_preview_text,
                    inputs=[original_results_state, pinned_frames_state],
                    outputs=[preview_textbox],
                    api_name=False,
                )

                original_results_state.change(
                    fn=_generate_preview_text,
                    inputs=[original_results_state, pinned_frames_state],
                    outputs=[preview_textbox],
                    api_name=False,
                )
                export_button.click(
                    fn=export_csv_file,
                    inputs=[preview_textbox, export_filename],
                    outputs=[submission_file, status],
                    api_name=False,
                )

                legacy_search_button.click(
                    fn=search_keyframes_gpu,
                    inputs=legacy_search_inputs,
                    outputs=legacy_search_outputs,
                    api_name="search_keyframes",
                )

                refine_inputs = [
                    original_results_state,
                    visible_results_state,
                    within_results_query,
                    within_results_field,
                    refine_collections,
                    refine_videos,
                    refine_authors,
                    minimum_result_score,
                ]
                refine_outputs = [
                    gallery,
                    visible_results_state,
                    page_rows_state,
                    page_state,
                    page_label,
                    previous_button,
                    next_button,
                    detail_image,
                    detail_video,
                    detail_metadata,
                    detections,
                    refine_status,
                ]
                filter_results_button.click(
                    controller.refine_results,
                    inputs=refine_inputs,
                    outputs=refine_outputs,
                    queue=False,
                    api_name=False,
                )
                within_results_query.submit(
                    controller.refine_results,
                    inputs=refine_inputs,
                    outputs=refine_outputs,
                    queue=False,
                    api_name=False,
                )
                for component in (
                    within_results_field,
                    refine_collections,
                    refine_videos,
                    refine_authors,
                ):
                    component.input(
                        controller.refine_results,
                        inputs=refine_inputs,
                        outputs=refine_outputs,
                        queue=False,
                        api_name=False,
                    )
                minimum_result_score.release(
                    controller.refine_results,
                    inputs=refine_inputs,
                    outputs=refine_outputs,
                    queue=False,
                    api_name=False,
                )

                clear_within_button.click(
                    controller.clear_within_results,
                    inputs=[
                        original_results_state,
                        visible_results_state,
                        within_results_field,
                        refine_collections,
                        refine_videos,
                        refine_authors,
                        minimum_result_score,
                    ],
                    outputs=[within_results_query, *refine_outputs],
                    queue=False,
                    api_name=False,
                )
                clear_refinements_button.click(
                    controller.clear_all_refinements,
                    inputs=[original_results_state],
                    outputs=[
                        *refine_outputs,
                        within_results_query,
                        within_results_field,
                        refine_collections,
                        refine_videos,
                        refine_authors,
                        minimum_result_score,
                    ],
                    queue=False,
                    api_name=False,
                )

                page_outputs = [
                    gallery,
                    page_rows_state,
                    page_state,
                    page_label,
                    previous_button,
                    next_button,
                    detail_image,
                    detail_video,
                    detail_metadata,
                    detections,
                ]
                previous_button.click(
                    controller.previous_page,
                    inputs=[visible_results_state, original_results_state, page_state],
                    outputs=page_outputs,
                    queue=False,
                    api_name=False,
                )
                next_button.click(
                    controller.next_page,
                    inputs=[visible_results_state, original_results_state, page_state],
                    outputs=page_outputs,
                    queue=False,
                    api_name=False,
                )
                gallery.select(
                    controller.select_keyframe,
                    inputs=[page_rows_state],
                    outputs=[
                        detail_image, detail_video, detail_metadata, detections,
                        prev_btn, next_btn, pin_btn,
                        current_fps_box, current_video_id_box, current_kf_frame_box
                    ],
                    api_name=False,
                )

                frame_step_js = """(fps) => {
                    const video = document.getElementById('query-text-player');
                    if (video) {
                        video.pause();
                        video.currentTime += (1.0 / fps);
                    }
                    return fps;
                }"""
                frame_prev_js = """(fps) => {
                    const video = document.getElementById('query-text-player');
                    if (video) {
                        video.pause();
                        video.currentTime -= (1.0 / fps);
                    }
                    return fps;
                }"""
                pin_js = """(c_time, pinned, vid, fps, kf_frame) => {
                    const video = document.getElementById('query-text-player');
                    const t = video ? video.currentTime.toString() : "";
                    return [t, pinned, vid, fps, kf_frame];
                }"""

                next_btn.click(None, inputs=[current_fps_box], outputs=[current_fps_box], js=frame_step_js)
                prev_btn.click(None, inputs=[current_fps_box], outputs=[current_fps_box], js=frame_prev_js)

                pin_btn.click(
                    process_pin_kis,
                    inputs=[current_time_box, pinned_frames_state, current_video_id_box, current_fps_box, current_kf_frame_box],
                    outputs=[pinned_frames_state, status],
                    js=pin_js,
                    api_name=False
                )
                clear_pins_btn.click(
                    clear_pins_kis,
                    inputs=[],
                    outputs=[pinned_frames_state, status],
                    api_name=False
                )

                api_details_button.click(
                    controller.details_api,
                    inputs=[api_keyframe_id],
                    outputs=[api_details],
                    api_name="get_keyframe_details",
                )

            if trake_searcher is not None:
                with gr.Tab("Query TRAKE"):
                    build_trake_tab(trake_searcher)

    return webui



def process_pin_kis(current_time, current_pins, video_id, fps, kf_frame):
    if not video_id:
        return current_pins, "Không có video nào được chọn."

    try:
        current_time = float(current_time)
        new_frame = round(current_time * fps)
    except (ValueError, TypeError):
        new_frame = kf_frame

    current_pins = current_pins or {}
    current_pins[video_id] = new_frame
    return current_pins, f"Đã chốt frame {new_frame} cho video {video_id}."

def clear_pins_kis():
    return {}, "Đã gỡ bỏ toàn bộ frame chốt tay."


def create_search_mechanism(runtime: RuntimePaths) -> SearchMechanism:
    environment = runtime.environment
    clip_searcher = CLIPSearcher(
        model_id=environment["MODEL_ID"],
        revision=environment["MODEL_REVISION"],
    )
    clip_searcher.load()
    return SearchMechanism(
        clip_searcher=clip_searcher,
        translator=QueryTranslator(
            model_id=environment["TRANSLATION_MODEL_ID"],
            revision=environment["TRANSLATION_MODEL_REVISION"],
        ),
        image_indexer=ImageIndexer(
            runtime.index_file,
            nprobe=int(environment["FAISS_NPROBE"]),
        ),
        sqlite_file=runtime.sqlite_file,
        embeddings_file=runtime.embeddings_file,
        data_root=runtime.data_root,
    )


def create_trake_searcher(runtime: RuntimePaths, search_mechanism: SearchMechanism) -> TrakeSearcher:
    """Reuse the already loaded CLIP and translator instances."""
    return TrakeSearcher(
        clip_searcher=search_mechanism.clip_searcher,
        translator=search_mechanism.translator,
        sqlite_file=runtime.sqlite_file,
        embeddings_file=runtime.embeddings_file,
        data_root=runtime.data_root,
    )


def create_app() -> gr.Blocks:
    global _keyframes_root

    runtime = prepare_runtime()
    _keyframes_root = _keyframe_directory(runtime.data_root)
    search_mechanism = create_search_mechanism(runtime)
    try:
        trake_searcher = create_trake_searcher(runtime, search_mechanism)
    except Exception:
        logger.warning("Failed to initialize TRAKE searcher; TRAKE tab disabled", exc_info=True)
        trake_searcher = None
    return build_app(
        search_mechanism,
        page_size=int(runtime.environment["RESULTS_PER_PAGE"]),
        trake_searcher=trake_searcher,
    )

demo = create_app()


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if _keyframes_root is None:
        raise RuntimeError("Keyframe data root has not been initialized")

    video_root = os.environ.get("VIDEO_ROOT")
    allowed_paths = [str(_keyframes_root)]
    if video_root:
        allowed_paths.append(str(video_root))

    demo.queue(default_concurrency_limit=2)
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", "7860")),
        ssr_mode=False,
        allowed_paths=allowed_paths,
    )


if __name__ == "__main__":
    main()