"""Standalone Gradio application for filtered keyframe retrieval."""

from __future__ import annotations

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
import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

from clip import CLIPSearcher
from clusterer import ImageIndexer
from database_utils import RuntimePaths, prepare_runtime
from db import GROUPING_ANCHOR, GROUPING_LINKAGE, SearchMechanism
from frame_math import validate_frame
from keyframe_details import detail_markdown as _detail_markdown
from keyframe_details import detection_rows as _detection_rows
from keyframe_details import timestamp as _timestamp
from keyframe_details import watch_at as _watch_at
from player import build_player, player_head_html
from query_parser import parse_search_query
from schemas import SearchFilters
from trake import SUBMISSION_MAX_ROWS, TrakeSearcher, format_submission
from trake_submission import export_csv_file
from trake_ui import build_trake_tab
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

/* Grid tự lấy chiều cao theo số hàng đang cấu hình */
#keyframe-gallery .grid-container {
    height: auto !important;
    max-height: none !important;
    overflow: visible !important;
    align-content: start !important;
}

/* the frame others were folded into — outlined so the kept side is visible too.
   Gradio wraps thumbnails in a button or a div depending on the render path. */
#keyframe-gallery .aiou-anchor,
#cluster-gallery .aiou-anchor {
    outline: 3px solid #a855f7 !important;
    outline-offset: -3px;
    border-radius: 4px;
}

#keyframe-gallery .aiou-grouped,
#cluster-gallery .aiou-grouped {
    outline: 2px dashed #c4b5fd !important;
    outline-offset: -2px;
    border-radius: 4px;
}

#selected-keyframe,
#trake-selected-keyframe {
    min-height: 400px;
}

#selected-keyframe img,
#trake-selected-keyframe img {
    object-fit: contain !important;
}

@media (max-width: 600px) {
    #app-title {
        margin-top: 3.5rem;
    }

    #selected-keyframe,
    #trake-selected-keyframe {
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


def _keyframe_directory(data_root: Path) -> Path:
    return (data_root / "keyframes").resolve()



def _normalize_kis_pins(pinned: object) -> list[tuple[str, int]]:
    """Return ordered, unique KIS pins while accepting the legacy dict state."""
    items = pinned.items() if isinstance(pinned, dict) else pinned or []
    normalized: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for item in items:
        try:
            video_id, frame = item
            pair = (str(video_id), int(frame))
        except (TypeError, ValueError):
            continue
        if not pair[0] or pair[1] < 0 or pair in seen:
            continue
        normalized.append(pair)
        seen.add(pair)
    return normalized


SHORTCUTS_HEAD = """
<script>
(function () {
  // Typing in a box must stay typing: only fire when focus is outside an input.
  function isTyping(target) {
    if (!target) return false;
    var tag = (target.tagName || '').toUpperCase();
    return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable;
  }
  function press(id) {
    var el = document.getElementById(id);
    var button = el && (el.tagName === 'BUTTON' ? el : el.querySelector('button'));
    if (button && !button.disabled) { button.click(); return true; }
    return false;
  }
  document.addEventListener('keydown', function (event) {
    if (event.ctrlKey || event.altKey || event.metaKey) return;
    if (isTyping(event.target)) return;
    var handled = false;
    switch (event.key) {
      case 'ArrowLeft':  handled = press('prev-page-btn'); break;
      case 'ArrowRight': handled = press('next-page-btn'); break;
      case 's': case 'S': handled = press('similar-search-btn'); break;
      case 'x': case 'X': handled = press('exclude-btn'); break;
      case 'g': case 'G': handled = press('grouped-btn'); break;
      case '/':
        var box = document.querySelector('#component-0 textarea, textarea');
        if (box) { box.focus(); handled = true; }
        break;
    }
    if (handled) event.preventDefault();
  });
})();
</script>
<script>
(function () {
  // Gradio owns the gallery DOM and rebuilds it on every render, so the marker
  // is re-derived from the caption text rather than set once.
  var GALLERIES = ['#keyframe-gallery', '#cluster-gallery'];
  function cellOf(node) {
    // the caption sits beside the image button, so walk up to their shared cell
    for (var el = node; el && el !== document.body; el = el.parentElement) {
      if (el.classList && (el.classList.contains('thumbnail-item')
          || el.classList.contains('gallery-item')
          || el.tagName === 'BUTTON')) return el;
    }
    return node.parentElement;
  }
  function mark() {
    GALLERIES.forEach(function (selector) {
      var root = document.querySelector(selector);
      if (!root) return;
      root.querySelectorAll('.aiou-anchor, .aiou-grouped').forEach(function (el) {
        el.classList.remove('aiou-anchor', 'aiou-grouped');
      });
      root.querySelectorAll('.caption-label, figcaption, .caption').forEach(function (label) {
        var caption = label.textContent || '';
        var cell = cellOf(label);
        if (!cell) return;
        if (caption.indexOf('[đại diện]') !== -1) cell.classList.add('aiou-anchor');
        if (caption.indexOf('[gộp x') !== -1) cell.classList.add('aiou-grouped');
      });
    });
  }
  var pending = null;
  new MutationObserver(function () {
    if (pending) return;
    pending = requestAnimationFrame(function () { pending = null; mark(); });
  }).observe(document.body, { childList: true, subtree: true });
  document.addEventListener('DOMContentLoaded', mark);
  mark();
})();
</script>
"""

HISTORY_LIMIT = 10

# len(restore_outputs): original_results_state + refine_outputs (12) + six refinement controls
HISTORY_RESTORE_OUTPUTS = 19


def _push_history(history: list, label: str, rows: list, limit: int = HISTORY_LIMIT) -> list:
    """Prepend a search snapshot, newest first, replacing a repeat of the same query.

    Returns a new list: gr.State only re-renders when the object identity changes.
    """
    label = (label or "").strip()
    if not rows or not label:
        return list(history or [])
    kept = [entry for entry in (history or []) if entry.get("label") != label]
    return [{"label": label, "rows": list(rows)}, *kept][:limit]


def _handoff_text(details) -> str:
    """One selectable line the searcher hands to the teammate verifying the answer."""
    keyframe = details.keyframe
    seconds = float(keyframe["pts_time_sec"])
    parts = [
        str(keyframe["video_id"]),
        _timestamp(seconds),
        f"frame {int(keyframe['frame_idx'])}",
        _watch_at(str(details.video.get("watch_url") or ""), seconds),
    ]
    return " | ".join(part for part in parts if part)


def _generate_preview_text(rows: list[dict], pinned: object = None):
    """Put ordered pins first, then preserve ranked keyframe candidates."""
    pinned_rows = _normalize_kis_pins(pinned)
    if not rows and not pinned_rows:
        return "Chưa có kết quả để xem trước."

    ordered_rows: list[tuple[str, int]] = []
    seen = set()
    candidates = [
        (str(row["video_id"]), int(row["frame_idx"]))
        for row in rows
    ]
    for pair in [*pinned_rows, *candidates]:
        if pair in seen:
            continue
        ordered_rows.append(pair)
        seen.add(pair)

    # The contest accepts at most SUBMISSION_MAX_ROWS lines per file.
    submission_rows = [(video_id, (frame,)) for video_id, frame in ordered_rows]
    return format_submission(submission_rows[:SUBMISSION_MAX_ROWS])


class SearchController:
    """UI callbacks bound to one immutable runtime release."""

    def __init__(self, search_mechanism: SearchMechanism, page_size: int) -> None:
        self.search_mechanism = search_mechanism
        self.page_size = page_size

    def set_mmr(self, enabled: bool, mode: str | None = None) -> None:
        setattr(self.search_mechanism, "mmr_enabled", bool(enabled))
        setattr(
            self.search_mechanism,
            "grouping_mode",
            GROUPING_LINKAGE if mode == self.LINKAGE_MODE else GROUPING_ANCHOR,
        )

    def page_payload(
        self,
        rows: list[dict],
        page: int,
        original_count: int | None = None,
        excluded: set | None = None,
        hide_excluded: bool = False,
    ):
        rows = rows or []
        excluded = excluded or set()
        if hide_excluded:
            # drop before slicing, so pages stay full and the count label stays truthful
            rows = [row for row in rows if row["keyframe_id"] not in excluded]
        total_pages = max(1, (len(rows) + self.page_size - 1) // self.page_size)
        page = max(0, min(int(page), total_pages - 1))
        start = page * self.page_size
        page_rows = rows[start : start + self.page_size]
        rendered_rows = [row for row in page_rows if Path(row["image_path"]).is_file()]
        # a frame is a representative when others were demoted in its favour
        anchors = {
            row["similar_to"] for row in rows if row.get("similar_to") is not None
        }
        gallery = [
            (
                row["image_path"],
                ("[ĐÃ LOẠI] " if row["keyframe_id"] in excluded else "")
                + ("[đại diện] " if row.get("vector_id") in anchors
                   and not row.get("duplicates") else "")
                + (f"[gộp x{row['duplicates']}] " if row.get("duplicates") else "")
                + f"{row['keyframe_id']} | {_timestamp(row['pts_time_sec'])} | {row['score']:.4f}",
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
        for row in rows:
            entry = outcome.duplicate_details.get(row["vector_id"]) or {}
            row["duplicates"] = int(entry.get("duplicates", 0))
            row["similar_to"] = entry.get("similar_to")
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

    def _repaint(self, rows, page, excluded, mode):
        """Redraw one page with the current exclusion set and display mode."""
        return self.page_payload(rows, page, None, excluded or set(), mode == "Ẩn hẳn")

    CLUSTER_LINK_THRESHOLD = 0.94

    def linkage_clusters(self, original_rows) -> list[list[dict]]:
        """Group by complete linkage: every pair inside a cluster must clear the
        threshold, not just one pair.

        Resemblance is not transitive here — measured A-B 0.944, A-C 0.946,
        B-C 0.853 among frames of the same pitch. Chaining off a single close
        pair swells a cluster until unrelated scenes sit together; requiring the
        whole cluster to agree cannot chain. Measured across eight queries:
        0% mismatched pairs, against 24.5% for a drifting centroid.
        """
        rows = [row for row in (original_rows or []) if row.get("vector_id") is not None]
        if len(rows) < 2:
            return []
        vectors = np.asarray(
            self.search_mechanism.embeddings[[row["vector_id"] for row in rows]],
            dtype=np.float32,
        )
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        distances = np.clip(1.0 - vectors @ vectors.T, 0.0, None)
        np.fill_diagonal(distances, 0.0)
        labels = fcluster(
            linkage(squareform(distances, checks=False), method="complete"),
            t=1.0 - self.CLUSTER_LINK_THRESHOLD,
            criterion="distance",
        )
        grouped: dict[int, list[dict]] = {}
        for row, label in zip(rows, labels):
            grouped.setdefault(int(label), []).append(row)
        clusters = [members for members in grouped.values() if len(members) > 1]
        clusters.sort(key=lambda members: (-len(members), members[0]["vector_id"]))
        return clusters

    @staticmethod
    def duplicate_clusters(original_rows) -> list[list[dict]]:
        """Group penalised frames under the representative that outranked them.

        `similar_to` points at the frame kept at full score. A representative can
        fall outside top_k once the widened pool is trimmed, so its cluster is
        dropped rather than shown headless.
        """
        by_vector = {row["vector_id"]: row for row in (original_rows or [])}
        clusters: dict[int, list[dict]] = {}
        for row in original_rows or []:
            anchor = row.get("similar_to")
            if anchor is None or anchor not in by_vector:
                continue
            clusters.setdefault(int(anchor), []).append(row)
        ordered = sorted(clusters.items(), key=lambda item: (-len(item[1]), item[0]))
        return [[by_vector[anchor], *members] for anchor, members in ordered]

    @staticmethod
    def cluster_choices(clusters) -> list[str]:
        return [f"Cụm {i + 1} ({len(c)} ảnh)" for i, c in enumerate(clusters)]

    @staticmethod
    def cluster_summary_text(clusters, total_rows: int) -> str:
        if not clusters:
            return "Lượt tìm này không có ảnh trùng nào bị gộp."
        grouped = sum(len(c) - 1 for c in clusters)
        return (
            f"Trong {total_rows} kết quả: **{grouped} ảnh** bị gộp thành "
            f"**{len(clusters)} cụm**. Ảnh đầu mỗi cụm là ảnh được giữ."
        )

    # Two readings of the same frames, neither strictly better: the anchor mode
    # yields fewer near-identical clusters, complete linkage yields cleaner ones.
    ANCHOR_MODE = "MMR"
    LINKAGE_MODE = "Complete Linkage"
    CLUSTER_MODES = [ANCHOR_MODE, LINKAGE_MODE]

    def _clusters_for(self, original_rows, mode):
        builders = {
            self.ANCHOR_MODE: self.duplicate_clusters,
            self.LINKAGE_MODE: self.linkage_clusters,
        }
        return builders.get(mode, self.duplicate_clusters)(original_rows)

    def compare_modes_text(self, original_rows) -> str:
        """Both counts at once — the modes disagree, and the gap is the point."""
        parts = []
        for label in self.CLUSTER_MODES:
            clusters = self._clusters_for(original_rows, label)
            grouped = sum(len(c) - 1 for c in clusters)
            parts.append(f"{label}: **{len(clusters)} cụm** ({grouped} ảnh)")
        return " · ".join(parts)

    def refresh_clusters(self, original_rows, mode=None):
        clusters = self._clusters_for(original_rows, mode)
        choices = self.cluster_choices(clusters)
        summary = self.cluster_summary_text(clusters, len(original_rows or []))
        if clusters:
            summary += "  \n" + self.compare_modes_text(original_rows)
        return (
            summary,
            gr.update(choices=choices, value=choices[0] if choices else None),
            self._cluster_items(clusters[0]) if clusters else [],
        )

    def show_cluster(self, original_rows, choice, mode=None):
        clusters = self._clusters_for(original_rows, mode)
        if not choice or not clusters:
            return []
        try:
            index = self.cluster_choices(clusters).index(choice)
        except ValueError:
            return []
        return self._cluster_items(clusters[index])

    @staticmethod
    def _rendered(cluster) -> list[dict]:
        """Only the rows with a file on disk — the gallery and the row list that
        drives selection have to agree on index."""
        return [row for row in cluster if Path(row["image_path"]).is_file()]

    @staticmethod
    def _cluster_items(cluster) -> list[tuple[str, str]]:
        items = []
        for position, row in enumerate(cluster):
            # same wording as the main gallery, so one marker rule covers both
            tag = "[đại diện] " if position == 0 else f"[gộp x{row.get('duplicates', 1)}] "
            items.append((row["image_path"], f"{tag}{row['keyframe_id']}"))
        return items

    def show_grouped_frames(self, original_rows, excluded, mode):
        """List exactly the frames duplicate-grouping penalised, so a mis-group is visible.

        Selected by the penalty flag, not by rank: a frame can sit last simply because it
        scored low, which says nothing about grouping.
        """
        rows = [row for row in (original_rows or []) if row.get("duplicates")]
        status = (
            f"Đang xem {len(rows)} ảnh bị gán trọng số (gộp trùng). "
            "Bấm 'Bỏ lọc trọng số' để xem lại toàn bộ."
            if rows
            else "Không có ảnh nào bị gán trọng số trong lượt tìm này."
        )
        return (*self._repaint(rows, 0, excluded, mode), status)

    def show_all_frames(self, original_rows, excluded, mode):
        rows = original_rows or []
        return (
            *self._repaint(rows, 0, excluded, mode),
            f"Refine current Top K results | {len(rows)} results",
        )

    def toggle_excluded(self, excluded, selected_keyframe_id, rows, page, mode):
        """Mark or unmark the selected frame so a rejected shot is not re-read on the next pass.

        Keyed by keyframe id, not grid position: every repaint reshuffles the grid, so a
        remembered index would toggle whichever frame later landed in that slot.
        """
        updated = set(excluded or set())
        if selected_keyframe_id:
            updated.symmetric_difference_update({str(selected_keyframe_id)})
        return (updated, *self._repaint(rows, page, updated, mode))

    def clear_excluded(self, rows, page, mode):
        return (set(), *self._repaint(rows, page, set(), mode))

    def restyle_excluded(self, excluded, rows, page, mode):
        """Re-render when the user switches between marking and hiding."""
        return self._repaint(rows, page, excluded, mode)

    def record_history(self, query, rows, history):
        """Snapshot a completed search so a worse follow-up query can be undone."""
        updated = _push_history(history, query, rows)
        labels = [entry["label"] for entry in updated]
        return updated, gr.update(choices=labels, value=None)

    def restore_history(self, history, label):
        """Re-render a stored result set without re-running the search.

        Refreshing the dropdown's choices after a search also fires `change` with an
        empty value; restoring nothing there would wipe the results just found.
        """
        if not label:
            return tuple(gr.update() for _ in range(HISTORY_RESTORE_OUTPUTS))
        for entry in history or []:
            if entry.get("label") == label:
                return self.clear_all_refinements(entry["rows"])
        return tuple(gr.update() for _ in range(HISTORY_RESTORE_OUTPUTS))

    def _neighbour_rows(self, keyframe_id: str) -> list[dict]:
        """Filmstrip around the selection: confirms a scene without opening the video."""
        try:
            rows = self.search_mechanism.get_temporal_window(keyframe_id)
        except (KeyError, AttributeError):
            return []
        return [row for row in rows if Path(row["image_path"]).is_file()]

    @staticmethod
    def _neighbour_items(rows: list[dict]) -> list[tuple[str, str]]:
        return [
            (row["image_path"], f"{row['keyframe_id']} | {_timestamp(row['pts_time_sec'])}")
            for row in rows
        ]

    def search_similar_images(self, page_rows, selected_keyframe_id, top_k):
        """Re-rank around the selected frame's own embedding.

        Duplicate grouping is suppressed for this one call: it penalises exactly the
        near-identical frames this search exists to surface. Looked up by keyframe id
        because every repaint reshuffles the grid a remembered index pointed into.
        """
        try:
            source = next(
                (row for row in page_rows or [] if row["keyframe_id"] == selected_keyframe_id),
                None,
            )
            if source is None:
                raise ValueError("Chọn một keyframe trước khi tìm ảnh giống.")
            vector_id = int(source["vector_id"])
            mechanism = self.search_mechanism
            outcome = mechanism.search_by_vector(
                mechanism.embeddings[vector_id], top_k=int(top_k), use_mmr=False
            )
            rows = [
                result.to_dict()
                for result in outcome.results
                if int(result.vector_id) != vector_id
            ]
            gallery, page_rows_out, page, label, previous_update, next_update = (
                self.page_payload(rows, 0)
            )
            collection_update, video_update, author_update = self._refinement_updates(rows)
            status = (
                f"Ảnh giống {source['keyframe_id']} | {len(rows)} kết quả | "
                "Gộp ảnh trùng tạm tắt cho lượt này"
            )
            return (
                gallery, rows, list(rows), page_rows_out, page, status, label,
                previous_update, next_update, None,
                "<p style='color: #666; font-style: italic;'>Select a keyframe to play video.</p>",
                "Select a keyframe to view metadata", [],
                collection_update, video_update, author_update,
                -1.0, "", "all",
                f"Refine current Top K results | {len(rows)} results",
            )
        except Exception as exc:
            logger.exception("Similar-image search failed")
            empty_update = gr.update(choices=[], value=[])
            return (
                [], [], [], [], 0, f"Error: {exc}", "Page 1 / 1 | 0 results",
                gr.update(interactive=False), gr.update(interactive=False), None,
                "<p style='color: #666; font-style: italic;'>Select a keyframe to play video.</p>",
                "Select a keyframe to view metadata", [],
                empty_update, empty_update, empty_update,
                -1.0, "", "all",
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
            # first slot feeds original_results_state: restoring history must move the
            # baseline too, or refine/clear/paging keep working on the previous search
            rows,
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

    @staticmethod
    def _no_selection(metadata_message: str):
        """Same shape as a successful selection, so all three branches stay aligned."""
        return (None, "<p style='color: #666; font-style: italic;'>Select a keyframe to play video.</p>",
                metadata_message, [],
                gr.update(), gr.update(), gr.update(), "", "", [], [],
                gr.update(), gr.update(), gr.update())

    def select_keyframe(self, page_rows, evt: gr.SelectData):
        if not page_rows or evt.index is None:
            return self._no_selection("Select a keyframe to view metadata")
        local_index = int(evt.index[0] if isinstance(evt.index, tuple) else evt.index)
        if local_index < 0 or local_index >= len(page_rows):
            return self._no_selection("Selected result is no longer available")
        row = page_rows[local_index]
        details = self.search_mechanism.get_keyframe_details(row["keyframe_id"])

        video_html = "<p style='color: #666; font-style: italic;'>Select a keyframe to view its player.</p>"
        video_id = details.keyframe["video_id"]
        pts = float(details.keyframe["pts_time_sec"])
        # The keyframe row is authoritative; the videos row has no per-frame fps.
        fps = float(details.keyframe["fps"])
        frame_idx = int(details.keyframe["frame_idx"])
        watch_url = str(details.video.get("watch_url") or "")
        video_path = get_video_path(video_id)
        video_html = build_player(
            video_id,
            local_path=video_path,
            watch_url=watch_url,
            pts_time_sec=pts,
            fps=fps,
            player_id="query-text-player",
            pin_button_id="query-text-pin-btn",
        )

        can_step_video = bool(video_path) or bool(watch_url)
        neighbour_rows = self._neighbour_rows(row["keyframe_id"])
        return (row["image_path"], video_html, _detail_markdown(details), _detection_rows(details),
                gr.update(interactive=can_step_video), gr.update(interactive=can_step_video), gr.update(interactive=True),
                _handoff_text(details), row["keyframe_id"], self._neighbour_items(neighbour_rows),
                neighbour_rows,
                fps, video_id, frame_idx)

    def details_api(self, keyframe_id: str):
        details = self.search_mechanism.get_keyframe_details(keyframe_id)
        return {
            "keyframe": details.keyframe,
            "video": details.video,
            "detections": list(details.detections),
        }


_search_controller: SearchController | None = None
if gr.NO_RELOAD:
    _keyframes_root: Path | None = None
    _runtime: RuntimePaths | None = None
    _search_mechanism: SearchMechanism | None = None
    _trake_searcher: TrakeSearcher | None = None


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

    with gr.Blocks(css=APP_CSS, head=player_head_html() + SHORTCUTS_HEAD) as webui:
        gr.Markdown("## AIOU", elem_id="app-title")
        with gr.Tabs():
            with gr.Tab("Query Text"):
                original_results_state = gr.State([])
                visible_results_state = gr.State([])
                selected_keyframe_state = gr.State("")
                history_state = gr.State([])
                excluded_state = gr.State(set())
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

                    history_dropdown = gr.Dropdown(
                        label="Lịch sử truy vấn (10 gần nhất)",
                        choices=[],
                        value=None,
                        interactive=True,
                        elem_id="history-dropdown",
                    )

                    gr.Markdown(
                        "*Bộ lọc (tuỳ chọn) — được áp dụng ngay khi bấm Search*  \n"
                        "*Phím tắt (khi con trỏ không ở ô nhập): `←` `→` chuyển trang · "
                        "`S` tìm ảnh giống · `X` loại ảnh · `G` xem ảnh bị gán trọng số · `/` về ô tìm*"
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

                    search_button = gr.Button(
                        "Search", variant="primary", elem_id="search-btn"
                    )
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
                    with gr.Row(equal_height=True):
                        with gr.Column(scale=4):
                            mmr_checkbox = gr.Checkbox(
                                label="Gộp ảnh trùng lặp",
                                value=False,
                                info="Tìm lại trên gấp đôi số ảnh rồi đẩy ảnh trùng xuống.",
                            )
                            cluster_mode = gr.Radio(
                                choices=SearchController.CLUSTER_MODES,
                                value=SearchController.ANCHOR_MODE,
                                label="Cách gộp",
                                info=(
                                    "MMR: gom quanh ảnh mạnh nhất, ít cụm na ná nhau. "
                                    "Complete Linkage: chỉ gom khi mọi ảnh đều giống nhau."
                                ),
                                elem_id="cluster-mode",
                            )
                        apply_mmr_button = gr.Button(
                            "Áp dụng", variant="primary", scale=1, elem_id="apply-mmr-btn"
                        )

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
                    previous_button = gr.Button(
                        "Previous", interactive=False, elem_id="prev-page-btn"
                    )
                    page_label = gr.Textbox(
                        value="Page 1 / 1 | 0 results",
                        show_label=False,
                        interactive=False,
                    )
                    next_button = gr.Button(
                        "Next", interactive=False, elem_id="next-page-btn"
                    )

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
                                    pin_btn = gr.Button(
                                        "Chốt Frame (Đẩy lên Top)",
                                        interactive=False,
                                        variant="primary",
                                        elem_id="query-text-pin-btn",
                                    )
                                    clear_pins_btn = gr.Button("Gỡ hết frame đã chốt")
                                pinned_frames_state = gr.State([])
                    with gr.Column(scale=2):
                        detail_metadata = gr.Markdown("Select a keyframe to view metadata")
                detections = gr.Dataframe(
                    headers=["Object", "Score", "MID", "Label", "ymin", "xmin", "ymax", "xmax"],
                    datatype=["str", "number", "str", "number", "number", "number", "number", "number"],
                    label="Detected objects",
                    interactive=False,
                )

                gr.Markdown("---")
                gr.Markdown("### Ảnh bị gộp trùng")
                cluster_summary = gr.Markdown(
                    "Lượt tìm này không có ảnh trùng nào bị gộp."
                )
                with gr.Row():
                    cluster_dropdown = gr.Dropdown(
                        label="Chọn cụm",
                        choices=[],
                        value=None,
                        interactive=True,
                        elem_id="cluster-dropdown",
                    )
                    grouped_button = gr.Button(
                        "Xem ảnh bị gộp trùng", elem_id="grouped-btn"
                    )
                    all_frames_button = gr.Button("Bỏ lọc, xem hết")
                cluster_gallery = gr.Gallery(
                    label="Ảnh trong cụm",
                    columns=5,
                    rows=1,
                    height="auto",
                    allow_preview=False,
                    object_fit="contain",
                    elem_id="cluster-gallery",
                )
                cluster_rows_state = gr.State([])

                gr.Markdown("---")
                gr.Markdown("### Làm việc với ảnh đang chọn")
                handoff_box = gr.Textbox(
                    label="Bàn giao (copy cho người kiểm tra)",
                    value="",
                    lines=1,
                    interactive=False,
                    show_copy_button=True,
                    elem_id="handoff-box",
                )
                with gr.Row():
                    similar_button = gr.Button(
                        "Tìm ảnh giống thế này",
                        elem_id="similar-search-btn",
                    )
                    exclude_button = gr.Button("Loại ảnh này", elem_id="exclude-btn")
                    clear_excluded_button = gr.Button("Bỏ đánh dấu tất cả")
                    exclude_mode = gr.Radio(
                        choices=["Chỉ đánh dấu", "Ẩn hẳn"],
                        value="Chỉ đánh dấu",
                        label="Ảnh đã loại",
                        elem_id="exclude-mode",
                    )
                neighbour_gallery = gr.Gallery(
                    label="Khung hình lân cận (cùng video)",
                    columns=11,
                    rows=1,
                    height="auto",
                    allow_preview=False,
                    object_fit="contain",
                    elem_id="neighbour-gallery",
                )
                neighbour_rows_state = gr.State([])

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

                    current_fps_box = gr.Number(visible=False, elem_id="qt-current-fps", value=25.0)
                    current_video_id_box = gr.Textbox(visible=False, elem_id="qt-current-video-id")
                    current_kf_frame_box = gr.Number(visible=False, elem_id="qt-current-kf-frame", value=0)
                    pin_calc_frame_box = gr.Number(visible=False, elem_id="qt-pin-calc-frame", value=None)
                    pin_accuracy_box = gr.Textbox(visible=False, elem_id="qt-pin-accuracy", value="")


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
                # history rides on .then() so search_inputs_v2 keeps its asserted arity
                search_button.click(
                    fn=search_keyframes_gpu_v2,
                    inputs=search_inputs_v2,
                    outputs=search_outputs_v2,
                    api_name="search_keyframes_v2",
                ).then(
                    fn=controller.record_history,
                    inputs=[query, original_results_state, history_state],
                    outputs=[history_state, history_dropdown],
                    api_name=False,
                ).then(
                    fn=controller.refresh_clusters,
                    inputs=[original_results_state, cluster_mode],
                    outputs=[cluster_summary, cluster_dropdown, cluster_gallery, cluster_rows_state],
                    api_name=False,
                )
                query.submit(
                    fn=search_keyframes_gpu_v2,
                    inputs=search_inputs_v2,
                    outputs=search_outputs_v2,
                    api_name=False,
                ).then(
                    fn=controller.record_history,
                    inputs=[query, original_results_state, history_state],
                    outputs=[history_state, history_dropdown],
                    api_name=False,
                ).then(
                    fn=controller.refresh_clusters,
                    inputs=[original_results_state, cluster_mode],
                    outputs=[cluster_summary, cluster_dropdown, cluster_gallery, cluster_rows_state],
                    api_name=False,
                )
                # kept out of search_inputs_v2 on purpose: the endpoint parameter count is asserted.
                # Applied on demand rather than on toggle: the first search stays raw so the
                # grouped result can be compared against it.
                apply_mmr_button.click(
                    fn=controller.set_mmr,
                    inputs=[mmr_checkbox, cluster_mode],
                    outputs=[],
                    api_name=False,
                ).then(
                    fn=search_keyframes_gpu_v2,
                    inputs=search_inputs_v2,
                    outputs=search_outputs_v2,
                    api_name=False,
                ).then(
                    fn=controller.refresh_clusters,
                    inputs=[original_results_state, cluster_mode],
                    outputs=[cluster_summary, cluster_dropdown, cluster_gallery, cluster_rows_state],
                    api_name=False,
                )
                cluster_mode.change(
                    fn=controller.refresh_clusters,
                    inputs=[original_results_state, cluster_mode],
                    outputs=[cluster_summary, cluster_dropdown, cluster_gallery, cluster_rows_state],
                    api_name=False,
                )
                cluster_dropdown.change(
                    fn=controller.show_cluster,
                    inputs=[original_results_state, cluster_dropdown, cluster_mode],
                    outputs=[cluster_gallery, cluster_rows_state],
                    api_name=False,
                )
                similar_button.click(
                    fn=controller.search_similar_images,
                    inputs=[page_rows_state, selected_keyframe_state, top_k],
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
                restore_outputs = [
                    original_results_state,
                    *refine_outputs,
                    within_results_query,
                    within_results_field,
                    refine_collections,
                    refine_videos,
                    refine_authors,
                    minimum_result_score,
                ]
                clear_refinements_button.click(
                    controller.clear_all_refinements,
                    inputs=[original_results_state],
                    outputs=restore_outputs,
                    queue=False,
                    api_name=False,
                )
                history_dropdown.change(
                    fn=controller.restore_history,
                    inputs=[history_state, history_dropdown],
                    outputs=restore_outputs,
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
                # page_payload's own six outputs, without the detail panes _change_page resets
                repaint_outputs = [
                    gallery,
                    page_rows_state,
                    page_state,
                    page_label,
                    previous_button,
                    next_button,
                ]
                exclude_button.click(
                    fn=controller.toggle_excluded,
                    inputs=[
                        excluded_state, selected_keyframe_state,
                        visible_results_state, page_state, exclude_mode,
                    ],
                    outputs=[excluded_state, *repaint_outputs],
                    queue=False,
                    api_name=False,
                )
                clear_excluded_button.click(
                    fn=controller.clear_excluded,
                    inputs=[visible_results_state, page_state, exclude_mode],
                    outputs=[excluded_state, *repaint_outputs],
                    queue=False,
                    api_name=False,
                )
                exclude_mode.change(
                    fn=controller.restyle_excluded,
                    inputs=[excluded_state, visible_results_state, page_state, exclude_mode],
                    outputs=repaint_outputs,
                    queue=False,
                    api_name=False,
                )
                grouped_button.click(
                    fn=controller.show_grouped_frames,
                    inputs=[original_results_state, excluded_state, exclude_mode],
                    outputs=[*repaint_outputs, refine_status],
                    queue=False,
                    api_name=False,
                )
                all_frames_button.click(
                    fn=controller.show_all_frames,
                    inputs=[original_results_state, excluded_state, exclude_mode],
                    outputs=[*repaint_outputs, refine_status],
                    queue=False,
                    api_name=False,
                )
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
                        prev_btn, next_btn, pin_btn, handoff_box, selected_keyframe_state,
                        neighbour_gallery, neighbour_rows_state,
                        current_fps_box, current_video_id_box, current_kf_frame_box
                    ],
                    api_name=False,
                )
                # a cluster thumbnail promotes to the selection like any other frame
                cluster_gallery.select(
                    controller.select_keyframe,
                    inputs=[cluster_rows_state],
                    outputs=[
                        detail_image, detail_video, detail_metadata, detections,
                        prev_btn, next_btn, pin_btn, handoff_box, selected_keyframe_state,
                        neighbour_gallery, neighbour_rows_state,
                        current_fps_box, current_video_id_box, current_kf_frame_box
                    ],
                    api_name=False,
                )
                # the filmstrip feeds the same handler, driven by its own row list
                neighbour_gallery.select(
                    controller.select_keyframe,
                    inputs=[neighbour_rows_state],
                    outputs=[
                        detail_image, detail_video, detail_metadata, detections,
                        prev_btn, next_btn, pin_btn, handoff_box, selected_keyframe_state,
                        neighbour_gallery, neighbour_rows_state,
                        current_fps_box, current_video_id_box, current_kf_frame_box
                    ],
                    api_name=False,
                )

                frame_step_js = """(fps) => {
                    if (window.__aiouStep) { window.__aiouStep('query-text-player', 1); }
                    return fps;
                }"""
                frame_prev_js = """(fps) => {
                    if (window.__aiouStep) { window.__aiouStep('query-text-player', -1); }
                    return fps;
                }"""
                # The browser sends the latest presented frame plus its accuracy
                # label; the server never recomputes a frame from wall-clock time.
                pin_js = """(vid, kf_frame, pinned, calc, acc) => {
                    const snap = window.__aiouFrameSnapshot
                        ? window.__aiouFrameSnapshot('query-text-player')
                        : {frame: null, accuracy: 'none'};
                    return [vid, kf_frame, pinned, snap.frame, snap.accuracy];
                }"""

                next_btn.click(None, inputs=[current_fps_box], outputs=[current_fps_box], js=frame_step_js)
                prev_btn.click(None, inputs=[current_fps_box], outputs=[current_fps_box], js=frame_prev_js)

                pin_btn.click(
                    process_pin_kis,
                    inputs=[
                        current_video_id_box,
                        current_kf_frame_box,
                        pinned_frames_state,
                        pin_calc_frame_box,
                        pin_accuracy_box,
                    ],
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
                    build_trake_tab(
                        trake_searcher,
                        keyframe_details_provider=search_mechanism,
                    )

    return webui



def process_pin_kis(video_id, kf_frame, current_pins, calc_frame, accuracy):
    """Store the browser-reported frame; fall back to the keyframe's own
    frame_idx whenever the player state is missing or malformed. Parameter
    order matches the click handler's `inputs` list."""
    if not video_id:
        return current_pins, "Không có video nào được chọn."

    fallback = validate_frame(kf_frame, 0)
    try:
        candidate = int(str(calc_frame).strip())
        parsed_candidate = candidate if candidate >= 0 else None
    except (TypeError, ValueError):
        parsed_candidate = None
    new_frame = parsed_candidate if parsed_candidate is not None else fallback
    trusted = parsed_candidate is not None and accuracy in {"calculated", "estimated"}
    if accuracy == "calculated" and trusted:
        label = "Calculated"
    elif accuracy == "estimated" and trusted:
        label = "Estimated"
    else:
        label = f"Keyframe {fallback}"

    pair = (str(video_id), new_frame)
    previous_pins = _normalize_kis_pins(current_pins)
    ordered_pins = [pair, *(existing for existing in previous_pins if existing != pair)]
    new_pins = [list(existing) for existing in ordered_pins[:SUBMISSION_MAX_ROWS]]
    return new_pins, f"Đã chốt frame {new_frame} cho video {video_id} ({label})."

def clear_pins_kis():
    return [], "Đã gỡ bỏ toàn bộ frame chốt tay."


def _configured_model_device(value: str, setting_name: str) -> str | None:
    device = str(value or "auto").strip().lower()
    if device == "auto":
        return None
    if device not in {"cpu", "cuda"}:
        raise ValueError(f"{setting_name} must be one of: auto, cpu, cuda")
    return device


def create_search_mechanism(runtime: RuntimePaths) -> SearchMechanism:
    environment = runtime.environment
    clip_searcher = CLIPSearcher(
        model_id=environment["MODEL_ID"],
        revision=environment["MODEL_REVISION"],
        device=_configured_model_device(environment["CLIP_DEVICE"], "CLIP_DEVICE"),
    )
    clip_searcher.load()
    return SearchMechanism(
        clip_searcher=clip_searcher,
        translator=QueryTranslator(
            model_id=environment["TRANSLATION_MODEL_ID"],
            revision=environment["TRANSLATION_MODEL_REVISION"],
            device=_configured_model_device(
                environment["TRANSLATION_DEVICE"],
                "TRANSLATION_DEVICE",
            ),
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
    global _keyframes_root, _runtime, _search_mechanism, _trake_searcher

    if _runtime is None:
        runtime = prepare_runtime()
        search_mechanism = create_search_mechanism(runtime)
        try:
            trake_searcher = create_trake_searcher(runtime, search_mechanism)
        except Exception:
            logger.warning(
                "Failed to initialize TRAKE searcher; TRAKE tab disabled",
                exc_info=True,
            )
            trake_searcher = None
        _runtime = runtime
        _search_mechanism = search_mechanism
        _trake_searcher = trake_searcher

    assert _search_mechanism is not None
    _keyframes_root = _keyframe_directory(_runtime.data_root)
    return build_app(
        _search_mechanism,
        page_size=int(_runtime.environment["RESULTS_PER_PAGE"]),
        trake_searcher=_trake_searcher,
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
