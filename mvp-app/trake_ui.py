"""Gradio TRAKE tab content: dynamic event inputs, search, submission export."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

# Duplicated intentionally from app.py to avoid a circular import
# (app.py will import build_trake_tab from this module).
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

from frame_math import validate_frame
from keyframe_details import detail_markdown, detection_rows
from player import build_player, resolve_player_source
from schemas import KeyframeDetails, TrakeOutcome
from trake import (
    MAX_EVENTS,
    MIN_EVENTS,
    SPREAD_RADIUS,
    SUBMISSION_MAX_ROWS,
    build_submission,
    format_submission,
)
from trake_submission import build_submission as build_submission_rows
from trake_submission import export_csv_file, pin_key
from trake_ui_render import (
    build_status_markdown,
)
from video_locator import get_video_path

logger = logging.getLogger(__name__)

_trake_controller: TrakeController | None = None


class TrakeController:
    """UI callbacks bound to one TrakeSearcher instance."""

    def __init__(self, trake_searcher: Any, keyframe_details_provider: Any = None) -> None:
        self.trake_searcher = trake_searcher
        self.keyframe_details_provider = keyframe_details_provider

    @staticmethod
    def _resize(new_count: int, *, clear_hidden: bool) -> tuple[Any, ...]:
        updates = [
            gr.update(
                visible=(i < new_count),
                # Only clearing on shrink; growing must not wipe what the user typed.
                **({"value": ""} if clear_hidden and i >= new_count else {}),
            )
            for i in range(MAX_EVENTS)
        ]
        add_state = gr.update(interactive=new_count < MAX_EVENTS)
        remove_state = gr.update(interactive=new_count > MIN_EVENTS)
        return new_count, *updates, add_state, remove_state

    @staticmethod
    def add_event(visible_count: int) -> tuple[Any, ...]:
        return TrakeController._resize(
            min(MAX_EVENTS, int(visible_count) + 1), clear_hidden=False
        )

    @staticmethod
    def remove_event(visible_count: int) -> tuple[Any, ...]:
        return TrakeController._resize(
            max(MIN_EVENTS, int(visible_count) - 1), clear_hidden=True
        )

    @staticmethod
    def _videos_per_page(event_count: int) -> int:
        if event_count == 1:
            return 10
        if event_count == 2:
            return 4
        if event_count <= 4:
            return 2
        return 1

    def search_events(
        self,
        translate_vietnamese: bool,
        ranking_objective: str,
        penalty_weight: float,
        *event_texts: str,
    ):
        events = [e for e in event_texts if e and e.strip()]
        if not events:
            # Friendly guard instead of a ValueError escaping into the UI.
            return (
                gr.update(value=[]),
                "",
                "Hãy nhập mô tả cho ít nhất một sự kiện.",
                None,
                0,
                "Page 1 / 1 | 0 results",
                gr.update(interactive=False),
                gr.update(interactive=False),
            )
        try:
            started = time.perf_counter()
            outcome = self.trake_searcher.search(
                events,
                translate_vietnamese=bool(translate_vietnamese),
                penalty_weight=float(penalty_weight),
                ranking_objective=str(ranking_objective),
            )
            elapsed = time.perf_counter() - started
            status_markdown = build_status_markdown(outcome, elapsed)
            gal_up, blocks_md, label, prev_up, next_up = self._render_video_page(outcome, 0)
            return gal_up, blocks_md, status_markdown, outcome, 0, label, prev_up, next_up
        except Exception as exc:
            logger.exception("TRAKE search failed")
            return (
                gr.update(value=[]),
                "",
                f"Error: {exc}",
                None,
                0,
                "Page 1 / 1 | 0 results",
                gr.update(interactive=False),
                gr.update(interactive=False),
            )


    def _render_video_page(self, outcome, page_idx: int):
        import math

        import gradio as gr

        from trake_ui_render import build_gallery_items_slice, build_video_blocks_slice
        if not outcome or not outcome.videos:
            return gr.update(value=[]), "No matching video sequences found.", "Page 1 / 1 | 0 results", gr.update(interactive=False), gr.update(interactive=False)

        total_videos = len(outcome.videos)
        num_events = len(outcome.videos[0].events)

        per_page = self._videos_per_page(num_events)
        if num_events == 1:
            columns = 5
        elif num_events == 2:
            columns = 4
        elif num_events == 3:
            columns = 3
        elif num_events == 4:
            columns = 4
        else:
            columns = num_events

        total_pages = max(1, math.ceil(total_videos / per_page))
        page_idx = max(0, min(page_idx, total_pages - 1))
        start_idx = page_idx * per_page
        end_idx = start_idx + per_page
        videos_page = outcome.videos[start_idx:end_idx]

        gallery_items = build_gallery_items_slice(videos_page, start_idx + 1)
        block_md = build_video_blocks_slice(videos_page, start_idx + 1)

        label = f"Page {page_idx + 1} / {total_pages} | {total_videos} videos"
        gallery_update = gr.update(value=gallery_items, columns=columns)

        return gallery_update, block_md, label, gr.update(interactive=page_idx > 0), gr.update(interactive=page_idx < total_pages - 1)

    def change_video_page(self, outcome, page_idx: int, delta: int):
        if not outcome or not outcome.videos:
            return 0, *self._render_video_page(outcome, 0)

        total_videos = len(outcome.videos)
        num_events = len(outcome.videos[0].events)
        per_page = self._videos_per_page(num_events)

        import math
        total_pages = max(1, math.ceil(total_videos / per_page))
        new_idx = page_idx + delta
        new_idx = max(0, min(new_idx, total_pages - 1))
        return new_idx, *self._render_video_page(outcome, new_idx)

    def select_gallery_event(self, outcome, page_idx: int, gallery_index: int):
        unchanged = (gr.update(),) * 11
        if not outcome or not outcome.videos:
            return unchanged

        total_videos = len(outcome.videos)
        num_events = len(outcome.videos[0].events) if total_videos > 0 else 1
        per_page = self._videos_per_page(num_events)
        start_idx = int(page_idx) * per_page
        page_videos = outcome.videos[start_idx : start_idx + per_page]
        local_index = int(
            gallery_index[0] if isinstance(gallery_index, tuple) else gallery_index
        )
        found = _selected_event(page_videos, local_index)
        if found is None:
            return unchanged
        video, event = found

        details = self._keyframe_details(video, event)
        keyframe = details.keyframe
        video_metadata = details.video
        video_id = str(keyframe["video_id"])
        fps = float(keyframe["fps"])
        frame_idx = int(keyframe["frame_idx"])
        pts_time_sec = float(keyframe["pts_time_sec"])
        image_path = str(keyframe.get("image_path") or event.image_path)
        watch_url = str(video_metadata.get("watch_url") or "")
        video_path = get_video_path(video_id)
        player = build_player(
            video_id,
            local_path=video_path,
            watch_url=watch_url,
            pts_time_sec=pts_time_sec,
            fps=fps,
            player_id="trake-player",
            pin_button_id="trake-pin-btn",
        )
        source_kind, _source = resolve_player_source(
            local_path=video_path,
            watch_url=watch_url,
        )
        step_enabled = gr.update(interactive=source_kind != "none")

        return (
            image_path,
            gr.update(value=player),
            detail_markdown(details),
            detection_rows(details),
            step_enabled,
            step_enabled,
            gr.update(interactive=True),
            fps,
            video_id,
            event.event_index,
            frame_idx,
        )

    def _keyframe_details(self, video, event) -> KeyframeDetails:
        provider = self.keyframe_details_provider
        if provider is not None and hasattr(provider, "get_keyframe_details"):
            try:
                return provider.get_keyframe_details(event.keyframe_id)
            except Exception:
                logger.exception("Unable to load TRAKE keyframe details: %s", event.keyframe_id)

        return KeyframeDetails(
            keyframe={
                "keyframe_id": event.keyframe_id,
                "video_id": event.video_id,
                "collection_id": video.collection_id,
                "keyframe_no": event.keyframe_no,
                "frame_idx": event.frame_idx,
                "pts_time_sec": event.pts_time_sec,
                "fps": event.fps,
                "image_path": event.image_path,
            },
            video={
                "title": video.title,
                "author": video.author,
                "watch_url": getattr(video, "watch_url", "") or "",
            },
        )

    @staticmethod
    def _build_rows(
        outcome: TrakeOutcome, pinned_frames: dict
    ) -> tuple[list[tuple[str, tuple[int, ...]]], int]:
        """One answer per video first, jitter after. The organizers take a single
        answer per query, so the row people actually submit must come first.

        SUBMISSION_MAX_ROWS counts every row, and with ~34 jittered rows per video
        the cap is reached after two or three videos. Collecting the answers with
        rows_per_video=1 first keeps the rest of the ranking reachable."""
        primary = build_submission_rows(
            outcome,
            max_rows=len(outcome.videos),
            rows_per_video=1,
            radius=SPREAD_RADIUS,
            pinned_frames=pinned_frames,
        )
        answered = {video_id for video_id, _frames in primary}
        spread = [
            row
            for row in build_submission(outcome, pinned_frames=pinned_frames)
            if row not in primary and row[0] in answered
        ]
        # The 100-row contest budget counts the answers too — jitter only fills
        # whatever room is left after one row per ranked video.
        rows = (primary + spread)[:SUBMISSION_MAX_ROWS]
        return rows, len(primary)

    def preview_submission(
        self, outcome: TrakeOutcome | None, pinned_frames: dict
    ) -> Any:
        if not outcome:
            return gr.update(value="No search results to preview.")
        rows, _ = self._build_rows(outcome, pinned_frames)
        content = format_submission(rows)
        return gr.update(value=content)




EMPTY_PLAYER_HTML = (
    "<p style='color: #666; font-style: italic;'>Select a keyframe to play video.</p>"
)


def _selected_event(videos, gallery_index: int):
    """Map a gallery position back to its event within `videos`. The gallery
    builders drop events whose image is missing, so the same filter has to run
    here or the indices skew."""
    position = 0
    for video in videos:
        for event in video.events:
            if not Path(event.image_path).is_file():
                continue
            if position == gallery_index:
                return video, event
            position += 1
    return None


def process_pin(v_id, e_idx, kf_frame, pinned_frames, current_accuracies, calc_frame, accuracy):
    """Pin the frame the browser reported. Parameter order matches the click
    handler's `inputs` list — Gradio binds arguments positionally. The video
    player is optional: when its state is missing or malformed the keyframe's
    own frame_idx is stored, so pinning works with or without a playable
    source."""
    if not v_id:
        return (
            dict(pinned_frames or {}),
            dict(current_accuracies or {}),
            gr.update(value="Chưa chốt được — hãy chọn một ảnh trong kết quả trước."),
        )

    fallback = validate_frame(kf_frame, 0)
    parsed_candidate: int | None
    try:
        candidate = int(str(calc_frame).strip())
        parsed_candidate = candidate if candidate >= 0 else None
    except (TypeError, ValueError):
        parsed_candidate = None
    frame_id = parsed_candidate if parsed_candidate is not None else fallback
    trusted = parsed_candidate is not None and accuracy in {"calculated", "estimated"}
    label = (
        accuracy.capitalize() if trusted else f"Keyframe {fallback}"
    )

    try:
        event_index = int(float(e_idx))
    except (TypeError, ValueError):
        event_index = 0
    key = pin_key(str(v_id), event_index)
    new_frames = dict(pinned_frames or {})
    new_frames[key] = frame_id
    new_accuracies = dict(current_accuracies or {})
    new_accuracies[key] = accuracy if trusted else "keyframe"

    return (
        new_frames,
        new_accuracies,
        gr.update(value=f"**Đã chốt frame {frame_id} ({label}).**"),
    )


def clear_pins():
    return (
        {},
        {},
        gr.update(value="Đã gỡ hết frame đã chốt."),
    )


def reset_pins_for_new_search():
    """Same reset as clear_pins, minus the status line — the search result just
    wrote there and must stay visible."""
    return {}, {}


def reset_selected_keyframe():
    return (
        None,
        EMPTY_PLAYER_HTML,
        "Select a keyframe to view metadata",
        [],
        gr.update(interactive=False),
        gr.update(interactive=False),
        gr.update(interactive=False),
        25.0,
        "",
        0,
        0,
    )


@spaces.GPU(duration=120)
def search_trake_gpu(translate_vietnamese, ranking_objective, penalty_weight, *event_texts):
    """Run TRAKE event-chain retrieval without passing unpicklable state to ZeroGPU."""
    if _trake_controller is None:
        raise RuntimeError("TRAKE controller has not been initialized")
    return _trake_controller.search_events(translate_vietnamese, ranking_objective, penalty_weight, *event_texts)


def build_trake_tab(
    trake_searcher: Any,
    *,
    keyframe_details_provider: Any = None,
) -> dict:
    global _trake_controller
    controller = TrakeController(trake_searcher, keyframe_details_provider)
    _trake_controller = controller

    outcome_state = gr.State(None)
    current_page_idx = gr.State(0)
    visible_count_state = gr.State(1)
    pinned_frames_state = gr.State({})
    pinned_accuracies_state = gr.State({})

    event_boxes: list[gr.Textbox] = []
    with gr.Column():
        for i in range(MAX_EVENTS):
            box = gr.Textbox(
                label=f"Event {i + 1}",
                placeholder="Describe this event in the sequence",
                visible=(i < 1),
            )
            event_boxes.append(box)
        with gr.Row():
            remove_button = gr.Button("Remove event", interactive=True)
            add_button = gr.Button("Add event", interactive=True)
            translate_vietnamese = gr.Checkbox(
                label="Translate Vietnamese query to English",
                value=True,
                info="Off: direct multilingual search. On: NLLB translation before search.",
            )
        with gr.Row():
            ranking_objective = gr.Dropdown(
                label="Ranking Objective",
                choices=[
                    ("Min (No penalty)", "min"),
                    ("Sum (No penalty)", "sum"),
                    ("DANTE Sum (With penalty)", "dante"),
                    ("DANTE Min (With penalty)", "dante_min"),
                ],
                value="dante_min",
                info="Objective function for temporal alignment dynamic programming.",
            )
            penalty_weight = gr.Slider(
                label="Penalty Weight (λ)",
                minimum=0.0,
                maximum=0.05,
                step=0.001,
                value=0.005,
                info="Temporal distance penalty. Active only for DANTE objectives.",
            )

    search_button = gr.Button("Search event chain", variant="primary")
    status = gr.Markdown("Ready")

    gallery = gr.Gallery(
        label="Event keyframes",
        show_label=True,
        columns=6,
        height="auto",
        object_fit="contain",
        allow_preview=False,
        preview=False,
    )
    with gr.Row():
        prev_btn_pg = gr.Button("Previous", interactive=False)
        page_label = gr.Textbox(
            value="Page 1 / 1 | 0 results",
            show_label=False,
            interactive=False,
        )
        next_btn_pg = gr.Button("Next", interactive=False)

    with gr.Row(equal_height=False, elem_classes=["keyframe-detail-layout"]):
        with gr.Column(scale=3, elem_classes=["keyframe-media-column"]):
            with gr.Tabs():
                with gr.Tab("Image Details"):
                    detail_image = gr.Image(
                        label="Selected keyframe",
                        interactive=False,
                        height=420,
                        elem_id="trake-selected-keyframe",
                    )
                with gr.Tab("Video Player"):
                    video_player_html = gr.HTML(EMPTY_PLAYER_HTML)
                    with gr.Row():
                        prev_btn = gr.Button("Prev Frame", interactive=False)
                        next_btn = gr.Button("Next Frame", interactive=False)
                        pin_btn = gr.Button(
                            "Pin Frame",
                            interactive=False,
                            variant="primary",
                            elem_id="trake-pin-btn",
                        )
                        clear_pins_btn = gr.Button("Gỡ hết frame đã chốt")
        with gr.Column(
            scale=2,
            elem_id="trake-metadata-column",
            elem_classes=["keyframe-metadata-column"],
        ):
            gr.Markdown(
                "### Metadata & Object Detection",
                elem_classes=["keyframe-metadata-heading"],
            )
            detail_metadata = gr.Markdown(
                "Select a keyframe to view metadata",
                elem_classes=["keyframe-metadata"],
            )
            detections = gr.Dataframe(
                headers=["Object", "Score", "MID", "Label", "ymin", "xmin", "ymax", "xmax"],
                datatype=["str", "number", "str", "number", "number", "number", "number", "number"],
                label="Detected objects",
                interactive=False,
                elem_classes=["keyframe-detections"],
            )

    # Hidden elements for JS to Python communication
    current_fps_box = gr.Number(visible=False, elem_id="trake-current-fps", value=25.0)
    current_video_id_box = gr.Textbox(visible=False, elem_id="trake-current-video-id")
    current_event_idx_box = gr.Number(visible=False, elem_id="trake-current-event-idx", value=0)
    # Keyframe's own frame_idx — the fallback answer when no video is available.
    current_kf_frame_box = gr.Number(visible=False, elem_id="trake-current-kf-frame", value=0)
    # Browser-reported calculated frame + its accuracy label (read at pin time).
    pin_calc_frame_box = gr.Number(visible=False, elem_id="trake-pin-calc-frame", value=None)
    pin_accuracy_box = gr.Textbox(visible=False, elem_id="trake-pin-accuracy", value="")
    # sync_btn removed

    # Search and pagination still exchange the formatted detail payload, but it
    # is internal state rather than a duplicate block in the visible UI.
    results_state = gr.State("")

    gr.Markdown("---")
    gr.Markdown("### Xem trước file nộp bài (Query TRAKE)")
    with gr.Row():
        export_filename = gr.Textbox(label="Tên file export", value="query-4-trake.csv", max_lines=1)
        export_button = gr.Button("Export submission file")
        submission_file = gr.File(label="Submission file", interactive=False, height=80, visible=False)

    preview_markdown = gr.Textbox(label="Nội dung file nộp (Có thể chỉnh sửa thủ công)", lines=15, max_lines=50)

    add_button.click(
        controller.add_event,
        inputs=[visible_count_state],
        outputs=[visible_count_state, *event_boxes, add_button, remove_button],
        api_name=False,
    )
    remove_button.click(
        controller.remove_event,
        inputs=[visible_count_state],
        outputs=[visible_count_state, *event_boxes, add_button, remove_button],
        api_name=False,
    )

    def update_penalty_slider(objective):
        is_dante = objective in {"dante", "dante_min"}
        return gr.update(interactive=is_dante)

    ranking_objective.change(
        update_penalty_slider,
        inputs=[ranking_objective],
        outputs=[penalty_weight],
        api_name=False,
    )

    search_inputs = [translate_vietnamese, ranking_objective, penalty_weight, *event_boxes]
    search_outputs = [gallery, results_state, status, outcome_state, current_page_idx, page_label, prev_btn_pg, next_btn_pg]
    # Pins name a video and an event slot, not a query — carrying them into the next
    # search would silently rewrite the new answer's frames.
    pin_reset_outputs = [pinned_frames_state, pinned_accuracies_state]
    selection_outputs = [
        detail_image,
        video_player_html,
        detail_metadata,
        detections,
        prev_btn,
        next_btn,
        pin_btn,
        current_fps_box,
        current_video_id_box,
        current_event_idx_box,
        current_kf_frame_box,
    ]

    prev_btn_pg.click(
        lambda o, i: controller.change_video_page(o, i, -1),
        inputs=[outcome_state, current_page_idx],
        outputs=[current_page_idx, gallery, results_state, page_label, prev_btn_pg, next_btn_pg],
        api_name=False
    ).then(reset_selected_keyframe, inputs=[], outputs=selection_outputs, api_name=False)
    next_btn_pg.click(
        lambda o, i: controller.change_video_page(o, i, 1),
        inputs=[outcome_state, current_page_idx],
        outputs=[current_page_idx, gallery, results_state, page_label, prev_btn_pg, next_btn_pg],
        api_name=False
    ).then(reset_selected_keyframe, inputs=[], outputs=selection_outputs, api_name=False)

    search_button.click(
        search_trake_gpu,
        inputs=search_inputs,
        outputs=search_outputs,
        api_name="search_trake",
    ).then(
        reset_pins_for_new_search,
        inputs=[],
        outputs=pin_reset_outputs,
        api_name=False,
    ).then(
        reset_selected_keyframe,
        inputs=[],
        outputs=selection_outputs,
        api_name=False,
    )
    event_boxes[-1].submit(
        search_trake_gpu,
        inputs=search_inputs,
        outputs=search_outputs,
        api_name=False,
    ).then(
        reset_pins_for_new_search,
        inputs=[],
        outputs=pin_reset_outputs,
        api_name=False,
    ).then(
        reset_selected_keyframe,
        inputs=[],
        outputs=selection_outputs,
        api_name=False,
    )

    outcome_state.change(
        controller.preview_submission,
        inputs=[outcome_state, pinned_frames_state],
        outputs=[preview_markdown],
        api_name=False,
    )
    pinned_frames_state.change(
        controller.preview_submission,
        inputs=[outcome_state, pinned_frames_state],
        outputs=[preview_markdown],
        api_name=False,
    )

    export_button.click(
        export_csv_file,
        inputs=[preview_markdown, export_filename],
        outputs=[submission_file, status],
        api_name=False,
    )

    # Custom JS for frame stepping
    frame_step_js = """(fps) => {
        if (window.__aiouStep) { window.__aiouStep('trake-player', 1); }
        return fps;
    }"""

    frame_prev_js = """(fps) => {
        if (window.__aiouStep) { window.__aiouStep('trake-player', -1); }
        return fps;
    }"""

    # Order must match process_pin's signature exactly — Gradio validates the count
    # of `inputs` against the handler, and the JS return replaces those values.
    pin_js = """(vid, eidx, kf_frame, pinned, accs, calc, acc) => {
        const snap = window.__aiouFrameSnapshot
            ? window.__aiouFrameSnapshot('trake-player')
            : {frame: null, accuracy: 'none'};
        return [vid, eidx, kf_frame, pinned, accs, snap.frame, snap.accuracy];
    }"""

    next_btn.click(None, inputs=[current_fps_box], outputs=[current_fps_box], js=frame_step_js)
    prev_btn.click(None, inputs=[current_fps_box], outputs=[current_fps_box], js=frame_prev_js)

    pin_btn.click(
        process_pin,
        inputs=[
            current_video_id_box,
            current_event_idx_box,
            current_kf_frame_box,
            pinned_frames_state,
            pinned_accuracies_state,
            pin_calc_frame_box,
            pin_accuracy_box,
        ],
        outputs=[pinned_frames_state, pinned_accuracies_state, status],
        js=pin_js,
        api_name=False,
    ).then(
        controller.preview_submission,
        inputs=[outcome_state, pinned_frames_state],
        outputs=[preview_markdown],
        api_name=False,
    )

    clear_pins_btn.click(
        clear_pins,
        inputs=[],
        outputs=[pinned_frames_state, pinned_accuracies_state, status],
        api_name=False,
    ).then(
        controller.preview_submission,
        inputs=[outcome_state, pinned_frames_state],
        outputs=[preview_markdown],
        api_name=False,
    )

    def on_gallery_select(evt: gr.SelectData, outcome, page_idx: int):
        return controller.select_gallery_event(outcome, page_idx, evt.index)

    gallery.select(
        on_gallery_select,
        inputs=[outcome_state, current_page_idx],
        outputs=selection_outputs,
        api_name=False,
    )

    return {
        "event_boxes": event_boxes,
        "add_button": add_button,
        "remove_button": remove_button,
        "translate_vietnamese": translate_vietnamese,
        "search_button": search_button,
        "status": status,
        "gallery": gallery,
        "detail_image": detail_image,
        "video_player_html": video_player_html,
        "detail_metadata": detail_metadata,
        "detections": detections,
        "results_state": results_state,
        "export_button": export_button,
        "submission_file": submission_file,
        "outcome_state": outcome_state,
        "visible_count_state": visible_count_state,
        "pinned_frames_state": pinned_frames_state,
        "pinned_accuracies_state": pinned_accuracies_state,
    }
