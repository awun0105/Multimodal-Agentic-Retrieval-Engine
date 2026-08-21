"""Gradio TRAKE tab content: dynamic event inputs, search, submission export."""

from __future__ import annotations

import html
import tempfile
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

import trake
from schemas import TrakeOutcome
from trake import (
    MAX_EVENTS,
    MIN_EVENTS,
    SPREAD_RADIUS,
    build_submission,
    format_submission,
)
from trake_submission import build_submission as build_submission_rows
from trake_submission import parse_pin_key, pin_key, export_csv_file
from video_locator import get_video_path
from trake_ui_render import (
    render_video_player,
    build_gallery_items,
    build_status_markdown,
    build_submission_preview_markdown,
    build_video_blocks,
)

_trake_controller: TrakeController | None = None


class TrakeController:
    """UI callbacks bound to one TrakeSearcher instance."""

    def __init__(self, trake_searcher: Any) -> None:
        self.trake_searcher = trake_searcher

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

    def search_events(self, translate_vietnamese: bool, *event_texts: str):
        import time
        events = [e for e in event_texts if e and e.strip()]
        started = time.perf_counter()
        outcome = self.trake_searcher.search(
            events, translate_vietnamese=bool(translate_vietnamese)
        )
        elapsed = time.perf_counter() - started
        status_markdown = build_status_markdown(outcome, elapsed)
        
        gal_up, blocks_md, label, prev_up, next_up = self._render_video_page(outcome, 0)
        return gal_up, blocks_md, status_markdown, outcome, 0, label, prev_up, next_up


    def _render_video_page(self, outcome, page_idx: int):
        import gradio as gr
        import math
        from trake_ui_render import build_gallery_items_slice, build_video_blocks_slice
        if not outcome or not outcome.videos:
            return gr.update(value=[]), "No matching video sequences found.", "Page 1 / 1 | 0 results", gr.update(interactive=False), gr.update(interactive=False)
        
        total_videos = len(outcome.videos)
        num_events = len(outcome.videos[0].events)
        
        if num_events == 1:
            per_page = 10
            columns = 5
        elif num_events == 2:
            per_page = 4
            columns = 4
        elif num_events == 3:
            per_page = 2
            columns = 3
        elif num_events == 4:
            per_page = 2
            columns = 4
        else:
            per_page = 1
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
        per_page = 10 if num_events == 1 else (4 if num_events == 2 else (2 if num_events <= 4 else 1))
        
        import math
        total_pages = max(1, math.ceil(total_videos / per_page))
        new_idx = page_idx + delta
        new_idx = max(0, min(new_idx, total_pages - 1))
        return new_idx, *self._render_video_page(outcome, new_idx)

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
        return primary + spread, len(primary)

    def preview_submission(
        self, outcome: TrakeOutcome | None, pinned_frames: dict
    ) -> Any:
        if not outcome:
            return gr.update(value="No search results to preview.")
        rows, primary_count = self._build_rows(outcome, pinned_frames)
        pinned_counts: dict[str, int] = {}
        for key in pinned_frames or {}:
            parsed = parse_pin_key(key)
            if parsed is None:
                continue
            video_id, _event_index = parsed
            pinned_counts[video_id] = pinned_counts.get(video_id, 0) + 1
        content = format_submission(rows)
        return gr.update(value=content)




PINNED_HEADING = "**Danh sách các Frame đã chốt (Pinned):**"
PINNED_EMPTY_MARKDOWN = f"{PINNED_HEADING}\n*Chưa có frame nào.*"


def render_pinned_frames(pinned_frames: dict) -> str:
    if not pinned_frames:
        return PINNED_EMPTY_MARKDOWN
    lines = [PINNED_HEADING]
    for key, frame_id in pinned_frames.items():
        parsed = parse_pin_key(key)
        if parsed is None:
            continue
        video_id, event_index = parsed
        lines.append(
            f"- **{html.escape(video_id)}**: Event {event_index + 1} -> Frame {frame_id}"
        )
    return "\n".join(lines) if len(lines) > 1 else PINNED_EMPTY_MARKDOWN


def _selected_event(outcome, gallery_index: int):
    """Map a gallery position back to its event. build_gallery_items drops events
    whose image is missing, so the same filter has to run here or the indices skew."""
    position = 0
    for video in outcome.videos:
        for event in video.events:
            if not Path(event.image_path).is_file():
                continue
            if position == gallery_index:
                return video, event
            position += 1
    return None


def _pinned_frame_id(c_time, fps, kf_frame) -> int | None:
    """Player time wins when it is readable; otherwise the keyframe's own frame_idx
    already is the answer."""
    try:
        return round(float(c_time) * float(fps))
    except (TypeError, ValueError):
        pass
    try:
        return int(kf_frame)
    except (TypeError, ValueError):
        return None


def process_pin(c_time, pinned_frames, v_id, e_idx, fps, kf_frame):
    """Pin the frame under review. The video player is optional: pinning falls back
    to the keyframe, so it works with or without a proxy video on disk."""
    pinned_frames = dict(pinned_frames or {})
    frame_id = _pinned_frame_id(c_time, fps, kf_frame) if v_id else None
    if frame_id is not None:
        pinned_frames[pin_key(v_id, int(e_idx))] = frame_id

    # Report this click's outcome, not whether the dict happens to be non-empty.
    status = (
        f"**Đã chốt frame {frame_id}.**"
        if frame_id is not None
        else "Chưa chốt được — hãy chọn một ảnh trong kết quả trước."
    )
    return (
        pinned_frames,
        gr.update(value=status),
        gr.update(value=render_pinned_frames(pinned_frames)),
    )


def clear_pins():
    return (
        {},
        gr.update(value="Đã gỡ hết frame đã chốt."),
        gr.update(value=PINNED_EMPTY_MARKDOWN),
    )


def reset_pins_for_new_search():
    """Same reset as clear_pins, minus the status line — the search result just
    wrote there and must stay visible."""
    return {}, gr.update(value=PINNED_EMPTY_MARKDOWN)


@spaces.GPU(duration=120)
def search_trake_gpu(translate_vietnamese, *event_texts):
    """Run TRAKE event-chain retrieval without passing unpicklable state to ZeroGPU."""
    if _trake_controller is None:
        raise RuntimeError("TRAKE controller has not been initialized")
    return _trake_controller.search_events(translate_vietnamese, *event_texts)


def build_trake_tab(trake_searcher: Any) -> dict:
    global _trake_controller
    controller = TrakeController(trake_searcher)
    _trake_controller = controller

    outcome_state = gr.State(None)
    current_page_idx = gr.State(0)
    visible_count_state = gr.State(1)
    pinned_frames_state = gr.State({})

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
    
    # --- PHASE 3: Alignment Video Player ---
    video_player_html = gr.HTML("")
    with gr.Row():
        prev_btn = gr.Button("Prev Frame", interactive=False)
        next_btn = gr.Button("Next Frame", interactive=False)
        pin_btn = gr.Button("Chốt Frame (Pin)", interactive=False, variant="primary")
        clear_pins_btn = gr.Button("Gỡ hết frame đã chốt")

    pinned_frames_markdown = gr.Markdown(PINNED_EMPTY_MARKDOWN)

    # Hidden elements for JS to Python communication
    current_time_box = gr.Textbox(visible=False, elem_id="trake-current-time")
    current_fps_box = gr.Number(visible=False, elem_id="trake-current-fps", value=25.0)
    current_video_id_box = gr.Textbox(visible=False, elem_id="trake-current-video-id")
    current_event_idx_box = gr.Number(visible=False, elem_id="trake-current-event-idx", value=0)
    # Keyframe's own frame_idx — the fallback answer when no video is available.
    current_kf_frame_box = gr.Number(visible=False, elem_id="trake-current-kf-frame", value=0)
    sync_btn = gr.Button("Sync", visible=False, elem_id="trake-sync-btn")

    with gr.Accordion("Log thông tin kết quả (Chi tiết)", open=False):
        results = gr.Markdown("")

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

    search_inputs = [translate_vietnamese, *event_boxes]
    search_outputs = [gallery, results, status, outcome_state, current_page_idx, page_label, prev_btn_pg, next_btn_pg]
    # Pins name a video and an event slot, not a query — carrying them into the next
    # search would silently rewrite the new answer's frames.
    pin_reset_outputs = [pinned_frames_state, pinned_frames_markdown]

    prev_btn_pg.click(
        lambda o, i: controller.change_video_page(o, i, -1),
        inputs=[outcome_state, current_page_idx],
        outputs=[current_page_idx, gallery, results, page_label, prev_btn_pg, next_btn_pg],
        api_name=False
    )
    next_btn_pg.click(
        lambda o, i: controller.change_video_page(o, i, 1),
        inputs=[outcome_state, current_page_idx],
        outputs=[current_page_idx, gallery, results, page_label, prev_btn_pg, next_btn_pg],
        api_name=False
    )

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
        const video = document.getElementById('trake-player');
        if (video) {
            video.pause();
            video.currentTime += (1.0 / fps);
        }
        return fps;
    }"""
    
    frame_prev_js = """(fps) => {
        const video = document.getElementById('trake-player');
        if (video) {
            video.pause();
            video.currentTime -= (1.0 / fps);
        }
        return fps;
    }"""
    
    # Order must match process_pin's signature exactly — Gradio validates the count
    # of `inputs` against the handler, and the JS return replaces those values.
    pin_js = """(c_time, pinned, vid, eidx, fps, kf_frame) => {
        const video = document.getElementById('trake-player');
        const t = video ? video.currentTime.toString() : "";
        return [t, pinned, vid, eidx, fps, kf_frame];
    }"""

    next_btn.click(None, inputs=[current_fps_box], outputs=[current_fps_box], js=frame_step_js)
    prev_btn.click(None, inputs=[current_fps_box], outputs=[current_fps_box], js=frame_prev_js)

    pin_btn.click(
        process_pin,
        inputs=[
            current_time_box,
            pinned_frames_state,
            current_video_id_box,
            current_event_idx_box,
            current_fps_box,
            current_kf_frame_box,
        ],
        outputs=[pinned_frames_state, status, pinned_frames_markdown],
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
        outputs=[pinned_frames_state, status, pinned_frames_markdown],
        api_name=False,
    ).then(
        controller.preview_submission,
        inputs=[outcome_state, pinned_frames_state],
        outputs=[preview_markdown],
        api_name=False,
    )
    
    def on_gallery_select(evt: gr.SelectData, outcome, idx: int):
        unchanged = (gr.update(),) * 8
        if not outcome or not outcome.videos:
            return unchanged
            
        video = outcome.videos[idx]
        if evt.index >= len(video.events):
            return unchanged
        event = video.events[evt.index]

        video_path = get_video_path(video.video_id)
        if video_path:
            player = render_video_player(
                video.video_id, video_path, event.pts_time_sec, event.fps
            )
            step_enabled = gr.update(interactive=True)
        else:
            player = (
                f"<p>Chưa có video cho {html.escape(video.video_id)} — "
                "vẫn chốt được frame từ ảnh keyframe.</p>"
            )
            step_enabled = gr.update(interactive=False)

        # Pinning never depends on the player: the keyframe already carries frame_idx.
        return (
            gr.update(value=player),
            step_enabled,
            step_enabled,
            gr.update(interactive=True),
            event.fps,
            video.video_id,
            event.event_index,
            event.frame_idx,
        )

    gallery.select(
        on_gallery_select,
        inputs=[outcome_state, current_page_idx],
        outputs=[
            video_player_html,
            prev_btn,
            next_btn,
            pin_btn,
            current_fps_box,
            current_video_id_box,
            current_event_idx_box,
            current_kf_frame_box,
        ],
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
        "results": results,
        "export_button": export_button,
        "submission_file": submission_file,
        "outcome_state": outcome_state,
        "visible_count_state": visible_count_state,
        "pinned_frames_state": pinned_frames_state,
    }
