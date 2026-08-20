"""Gradio TRAKE tab content: dynamic event inputs, search, submission export."""

from __future__ import annotations

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

from schemas import TrakeOutcome
from trake import MAX_EVENTS, MIN_EVENTS, build_submission, format_submission
from video_locator import get_video_path
from trake_ui_render import (
    render_video_player,
    build_gallery_items,
    build_status_markdown,
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
        events = [e for e in event_texts if e and e.strip()]
        started = time.perf_counter()
        outcome = self.trake_searcher.search(
            events, translate_vietnamese=bool(translate_vietnamese)
        )
        elapsed = time.perf_counter() - started
        gallery_items = build_gallery_items(outcome)
        blocks_markdown = build_video_blocks(outcome)
        status_markdown = build_status_markdown(outcome, elapsed)
        # One row per video keeps each event chain readable left-to-right.
        gallery_update = gr.update(value=gallery_items, columns=max(1, len(events)))
        return gallery_update, blocks_markdown, status_markdown, outcome


    def preview_submission(
        self, outcome: TrakeOutcome | None, pinned_frames: dict
    ) -> Any:
        if not outcome:
            return gr.update(value="No search results to preview.")
        from trake import build_submission, format_submission

        rows = build_submission(
            outcome,
            max_rows=34,  # preview 34 rows (1 full video)
            pinned_frames=pinned_frames,
        )
        csv_text = format_submission(rows)
        md = "### Bản xem trước (Preview) kết quả nộp bài cho Top 1 Video:\n```csv\n" + csv_text + "\n```"
        return gr.update(value=md)

    def export_submission(self, outcome: TrakeOutcome | None, pinned_frames: dict):
        if outcome is None or not outcome.videos:
            return None, "No search results to export yet."
        rows = build_submission(outcome, pinned_frames=pinned_frames)
        content = format_submission(rows)
        timestamp = time.strftime("%y%m%d-%H%M")
        out_path = Path(tempfile.gettempdir()) / f"trake_submission_{timestamp}.csv"
        out_path.write_text(content, encoding="utf-8")
        return str(out_path), f"Exported {len(rows)} rows."


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
    
    # --- PHASE 3: Alignment Video Player ---
    video_player_html = gr.HTML("")
    with gr.Row():
        prev_btn = gr.Button("Prev Frame", interactive=False)
        next_btn = gr.Button("Next Frame", interactive=False)
        pin_btn = gr.Button("Chốt Frame (Pin)", interactive=False, variant="primary")
    
    pinned_frames_markdown = gr.Markdown("**Danh sách các Frame đã chốt (Pinned):**\n*Chưa có frame nào.*")
    
    # Hidden elements for JS to Python communication
    current_time_box = gr.Textbox(visible=False, elem_id="trake-current-time")
    current_fps_box = gr.Number(visible=False, elem_id="trake-current-fps", value=25.0)
    current_video_id_box = gr.Textbox(visible=False, elem_id="trake-current-video-id")
    current_event_idx_box = gr.Number(visible=False, elem_id="trake-current-event-idx", value=0)
    sync_btn = gr.Button("Sync", visible=False, elem_id="trake-sync-btn")

    results = gr.Markdown("")

    with gr.Row():
        preview_button = gr.Button("Xem trước kết quả (Preview)")
        export_button = gr.Button("Export submission file")
        submission_file = gr.File(label="Submission file", interactive=False)
    
    preview_markdown = gr.Markdown("")

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
    search_outputs = [gallery, results, status, outcome_state]
    search_button.click(
        search_trake_gpu,
        inputs=search_inputs,
        outputs=search_outputs,
        api_name="search_trake",
    )
    event_boxes[-1].submit(
        search_trake_gpu,
        inputs=search_inputs,
        outputs=search_outputs,
        api_name=False,
    )

    preview_button.click(
        controller.preview_submission,
        inputs=[outcome_state, pinned_frames_state],
        outputs=[preview_markdown],
        api_name=False,
    )
    
    export_button.click(
        controller.export_submission,
        inputs=[outcome_state, pinned_frames_state],
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
    
    pin_js = """(fps, pinned, vid, eidx) => {
        const video = document.getElementById('trake-player');
        const c_time = video ? video.currentTime.toString() : "";
        return [c_time, pinned, vid, eidx, fps];
    }"""

    next_btn.click(None, inputs=[current_fps_box], outputs=[current_fps_box], js=frame_step_js)
    prev_btn.click(None, inputs=[current_fps_box], outputs=[current_fps_box], js=frame_prev_js)

    def process_pin(c_time, pinned_frames, v_id, e_idx, fps):
        if v_id and c_time is not None and c_time != "":
            try:
                frame_id = round(float(c_time) * float(fps))
                pinned_frames[(v_id, int(e_idx))] = frame_id
            except ValueError:
                pass
                
        if not pinned_frames:
            text = "**Danh sách các Frame đã chốt (Pinned):**\n*Chưa có frame nào.*"
        else:
            text = "**Danh sách các Frame đã chốt (Pinned):**\n"
            for (vid, e_idx_iter), fid in pinned_frames.items():
                text += f"- **{vid}**: Event {e_idx_iter + 1} -> Frame {fid}\n"
                
        return pinned_frames, gr.update(value="**Chốt thành công!**"), gr.update(value=text)
        
    pin_btn.click(
        process_pin, 
        inputs=[current_fps_box, pinned_frames_state, current_video_id_box, current_event_idx_box], 
        outputs=[pinned_frames_state, status, pinned_frames_markdown], 
        js=pin_js,
        api_name=False,
    )
    
    def on_gallery_select(evt: gr.SelectData, outcome):
        if not outcome or not outcome.videos:
            return gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update()
        
        # Determine which video and event was clicked
        idx = evt.index
        # idx maps to the flat list of images in gallery
        # we iterate over outcome.videos and their events to find the matching flat idx
        flat_idx = 0
        for video in outcome.videos:
            for ev in video.events:
                # We skip missing files in trake_ui_render, but here we assume the index matches
                # Actually trake_ui_render filters out missing files. Let's do the same logic to match indices.
                import os
                if not os.path.isfile(ev.image_path):
                    continue
                if flat_idx == idx:
                    v_path = get_video_path(video.video_id)
                    if v_path:
                        html_str = render_video_player(video.video_id, v_path, ev.pts_time_sec, ev.fps)
                        return (
                            gr.update(value=html_str), 
                            gr.update(interactive=True), 
                            gr.update(interactive=True), 
                            gr.update(interactive=True),
                            ev.fps,
                            video.video_id,
                            ev.event_index
                        )
                    else:
                        return (
                            gr.update(value=f"<p>Proxy video not found for {video.video_id}</p>"),
                            gr.update(interactive=False), gr.update(interactive=False), gr.update(interactive=False),
                            25.0, video.video_id, ev.event_index
                        )
                flat_idx += 1
                
        return gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update()
        
    gallery.select(
        on_gallery_select,
        inputs=[outcome_state],
        outputs=[video_player_html, prev_btn, next_btn, pin_btn, current_fps_box, current_video_id_box, current_event_idx_box],
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
