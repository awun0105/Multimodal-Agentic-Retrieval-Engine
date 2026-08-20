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
from trake_ui_render import (
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

    def export_submission(self, outcome: TrakeOutcome | None):
        if outcome is None or not outcome.videos:
            return None, "No search results to export yet."
        rows = build_submission(outcome)
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
    """Build TRAKE tab content inside an already-open gr.Blocks/gr.Tab context."""
    global _trake_controller

    controller = TrakeController(trake_searcher)
    _trake_controller = controller

    outcome_state = gr.State(None)
    visible_count_state = gr.State(3)

    event_boxes: list[gr.Textbox] = []
    with gr.Column():
        for i in range(MAX_EVENTS):
            box = gr.Textbox(
                label=f"Event {i + 1}",
                placeholder="Describe this event in the sequence",
                visible=(i < 3),
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
    results = gr.Markdown("")

    with gr.Row():
        export_button = gr.Button("Export submission file")
        submission_file = gr.File(label="Submission file", interactive=False)

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

    export_button.click(
        controller.export_submission,
        inputs=[outcome_state],
        outputs=[submission_file, status],
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
    }
