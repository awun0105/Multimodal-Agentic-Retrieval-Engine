"""Embedding retrieval with strict SQLite metadata filtering."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

from clip import CLIPSearcher
from clusterer import ImageIndexer
from schemas import KeyframeDetails, PreparedQuery, SearchFilters, SearchOutcome, SearchResult
from translation import QueryTranslator


MMR_SIMILARITY_THRESHOLD = 0.94
MMR_PENALTY_BASE = 0.4
# same-studio frames with different anchors top out at 0.939 cosine, so
# grouping starts just above them; the pool is widened because a raw top_k
# often holds far fewer distinct scenes than slots (13 across 100 measured)
MMR_OVERFETCH = 2

# Two readings of the same frames, neither strictly better.
GROUPING_ANCHOR = "anchor"
GROUPING_LINKAGE = "linkage"


def _apply_mmr(
    vectors: np.ndarray,
    scores: np.ndarray,
    vector_ids: np.ndarray,
    threshold: float = MMR_SIMILARITY_THRESHOLD,
    penalty_base: float = MMR_PENALTY_BASE,
    return_details: bool = False,
):
    """Demote near-duplicate frames so one screen shows distinct scenes.

    Walking best-first, each frame is scaled by penalty_base ** (number of already-kept
    frames it resembles). Duplicates sink instead of disappearing, so they stay reachable.
    `vectors` must already be float32 and L2-normalized.
    """
    if len(vector_ids) < 2:
        return (scores, vector_ids, {}) if return_details else (scores, vector_ids)

    similarity = vectors @ vectors.T
    order = np.argsort(-scores, kind="stable")

    kept: list[int] = []
    adjusted = np.empty(len(order), dtype=np.float64)
    details: dict[int, dict] = {}
    for position in order:
        resembles = [other for other in kept if similarity[position, other] >= threshold]
        adjusted[position] = float(scores[position]) * penalty_base ** len(resembles)
        details[int(vector_ids[position])] = {
            "duplicates": len(resembles),
            # first kept match is the one that survived at full score
            "similar_to": int(vector_ids[resembles[0]]) if resembles else None,
        }
        kept.append(int(position))

    reranked = np.argsort(-adjusted, kind="stable")
    ranked = (adjusted[reranked], np.asarray(vector_ids)[reranked])
    return (*ranked, details) if return_details else ranked


def _apply_linkage(
    vectors: np.ndarray,
    scores: np.ndarray,
    vector_ids: np.ndarray,
    threshold: float = MMR_SIMILARITY_THRESHOLD,
    return_details: bool = False,
):
    """Keep the best frame of each complete-linkage cluster, demote the rest.

    Resemblance is not transitive here: three views of one pitch measured
    A-B 0.944, A-C 0.946, B-C 0.853. Penalising against whichever frame ranked
    higher lets a cluster chain off one close pair until unrelated scenes sit
    together; requiring every pair inside a cluster to clear the threshold
    cannot chain.
    """
    if len(vector_ids) < 2:
        return (scores, vector_ids, {}) if return_details else (scores, vector_ids)

    distances = np.clip(1.0 - vectors @ vectors.T, 0.0, None)
    np.fill_diagonal(distances, 0.0)
    labels = fcluster(
        linkage(squareform(distances, checks=False), method="complete"),
        t=1.0 - threshold,
        criterion="distance",
    )

    adjusted = np.array(scores, dtype=np.float64)
    details: dict[int, dict] = {}
    for label in np.unique(labels):
        members = np.where(labels == label)[0]
        ranked = members[np.argsort(-adjusted[members], kind="stable")]
        keeper = int(ranked[0])
        details[int(vector_ids[keeper])] = {"duplicates": 0, "similar_to": None}
        for position, index in enumerate(ranked[1:], start=1):
            adjusted[index] = float(scores[index]) * MMR_PENALTY_BASE**position
            details[int(vector_ids[index])] = {
                "duplicates": position,
                "similar_to": int(vector_ids[keeper]),
            }

    order = np.argsort(-adjusted, kind="stable")
    ranked = (adjusted[order], np.asarray(vector_ids)[order])
    return (*ranked, details) if return_details else ranked


def _normalize_query_vector(vector: np.ndarray, expected_dimension: int) -> np.ndarray:
    query = np.asarray(vector, dtype=np.float32).reshape(1, -1)
    if query.shape[1] != expected_dimension:
        raise ValueError(
            f"Query dimension {query.shape[1]} does not match embeddings {expected_dimension}"
        )
    norm = float(np.linalg.norm(query[0]))
    if not np.isfinite(norm) or norm == 0:
        raise ValueError("Query embedding must have finite non-zero magnitude")
    return np.ascontiguousarray(query / norm, dtype=np.float32)


def _validate_iso_date(value: str | None, field: str) -> str | None:
    normalized = str(value).strip() if value else None
    if normalized:
        try:
            date.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError(f"{field} must use YYYY-MM-DD format") from exc
    return normalized


class SearchMechanism:
    """Coordinate translation, CLIP, metadata filters, FAISS, and exact cosine."""

    def __init__(
        self,
        clip_searcher: CLIPSearcher,
        translator: QueryTranslator,
        image_indexer: ImageIndexer,
        sqlite_file: str | Path,
        embeddings_file: str | Path,
        data_root: str | Path,
    ) -> None:
        self.clip_searcher = clip_searcher
        self.translator = translator
        self.image_indexer = image_indexer
        self.sqlite_file = Path(sqlite_file)
        self.data_root = Path(data_root)
        if not self.sqlite_file.is_file():
            raise FileNotFoundError(f"Runtime metadata database not found: {self.sqlite_file}")
        self.embeddings = np.load(Path(embeddings_file), mmap_mode="r", allow_pickle=False)
        if self.embeddings.ndim != 2:
            raise ValueError("Runtime embeddings must be a two-dimensional matrix")
        if self.embeddings.shape != (self.image_indexer.count, self.image_indexer.dimension):
            raise ValueError(
                "Embedding matrix and FAISS index disagree: "
                f"{self.embeddings.shape} != "
                f"({self.image_indexer.count}, {self.image_indexer.dimension})"
            )
        self._validate_database_count()
        # first search stays raw; grouping is applied from the refine panel
        self.mmr_enabled: bool = False
        self.grouping_mode: str = GROUPING_ANCHOR

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self.sqlite_file}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def _validate_database_count(self) -> None:
        with self._connect() as connection:
            count = int(connection.execute("SELECT COUNT(*) FROM keyframes").fetchone()[0])
        if count != self.embeddings.shape[0]:
            raise ValueError(
                f"SQLite keyframe count {count} does not match embeddings {self.embeddings.shape[0]}"
            )

    def filter_options(self) -> dict[str, list[str]]:
        with self._connect() as connection:
            collections = [
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT collection_id FROM keyframes ORDER BY collection_id"
                )
            ]
            videos = [
                row[0]
                for row in connection.execute("SELECT video_id FROM videos ORDER BY video_id")
            ]
            objects = [
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT entity FROM detections ORDER BY entity"
                )
            ]
            authors = [
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT author FROM videos WHERE author <> '' ORDER BY author"
                )
            ]
        return {
            "collections": collections,
            "videos": videos,
            "objects": objects,
            "authors": authors,
        }

    def search_by_text(
        self,
        query: str,
        top_k: int = 100,
        query_language: str = "auto",
        filters: SearchFilters | None = None,
        *,
        translate_vietnamese: bool | None = None,
    ) -> SearchOutcome:
        # checked before translation + CLIP so a bad top_k fails in microseconds
        top_k = int(top_k)
        if top_k < 1 or top_k > 200:
            raise ValueError("top_k must be in [1, 200]")
        if translate_vietnamese is None:
            prepared = self.translator.prepare(query, query_language)
        else:
            prepared = self.translator.prepare(
                query,
                query_language,
                translate_vietnamese=translate_vietnamese,
            )
        query_vector = _normalize_query_vector(
            self.clip_searcher.get_text_features(prepared.clip_query),
            self.embeddings.shape[1],
        )
        return self._rank(query_vector, top_k, filters or SearchFilters(), prepared)

    def search_by_vector(
        self,
        vector: np.ndarray,
        top_k: int = 100,
        filters: SearchFilters | None = None,
        use_mmr: bool | None = None,
    ) -> SearchOutcome:
        """Rank against a raw embedding — for 'more like this frame' on a result.

        Frames already in the corpus carry their own embedding, so the caller passes
        `self.embeddings[vector_id]` and no image encoder is ever loaded.
        Pass `use_mmr=False` for this call alone: duplicate grouping penalises exactly
        the near-identical frames this search exists to surface.
        """
        query_vector = _normalize_query_vector(vector, self.embeddings.shape[1])
        # no text to translate here, so bypass the translator rather than feed it ""
        prepared = PreparedQuery(
            original_query="",
            clip_query="",
            requested_language="auto",
            detected_language="auto",
            translation_enabled=False,
        )
        return self._rank(query_vector, top_k, filters or SearchFilters(), prepared, use_mmr)

    def _rank(
        self,
        query_vector: np.ndarray,
        top_k: int,
        filters: SearchFilters,
        prepared: PreparedQuery,
        use_mmr: bool | None = None,
    ) -> SearchOutcome:
        top_k = int(top_k)
        if top_k < 1 or top_k > 200:
            raise ValueError("top_k must be in [1, 200]")
        # per-call override; the shared flag stays untouched so a concurrent search
        # keeps whatever the user picked on the checkbox
        group_duplicates = self.mmr_enabled if use_mmr is None else bool(use_mmr)
        fetch_k = top_k * MMR_OVERFETCH if group_duplicates else top_k
        if filters.active:
            eligible_ids = self._eligible_vector_ids(filters)
            scores, vector_ids = self._search_filtered(query_vector, eligible_ids, fetch_k)
        else:
            scores, vector_ids = self.image_indexer.search(query_vector, fetch_k)
        details: dict[int, dict] = {}
        if group_duplicates and len(vector_ids) > 1:
            # embeddings are stored float16; matmul needs float32 to stay accurate
            vectors = np.asarray(self.embeddings[vector_ids], dtype=np.float32)
            group = (
                _apply_linkage
                if self.grouping_mode == GROUPING_LINKAGE
                else _apply_mmr
            )
            scores, vector_ids, details = group(
                vectors, scores, vector_ids, return_details=True
            )
            scores, vector_ids = scores[:top_k], vector_ids[:top_k]
            details = {int(v): details[int(v)] for v in vector_ids if int(v) in details}
        results = self._results_for_ids(vector_ids, scores)
        return SearchOutcome(tuple(results), prepared, details)

    def _eligible_vector_ids(self, filters: SearchFilters) -> np.ndarray:
        mode = filters.object_match_mode.strip().lower()
        if mode not in {"any", "all"}:
            raise ValueError("object_match_mode must be 'any' or 'all'")
        minimum_confidence = float(filters.minimum_object_confidence)
        if not 0 <= minimum_confidence <= 1:
            raise ValueError("minimum_object_confidence must be in [0, 1]")
        date_from = _validate_iso_date(filters.publish_date_from, "publish_date_from")
        date_to = _validate_iso_date(filters.publish_date_to, "publish_date_to")
        if date_from and date_to and date_from > date_to:
            raise ValueError("publish_date_from cannot be after publish_date_to")

        conditions: list[str] = []
        parameters: list[Any] = []
        if filters.collections:
            placeholders = ",".join("?" for _ in filters.collections)
            conditions.append(f"k.collection_id IN ({placeholders})")
            parameters.extend(filters.collections)
        scope_videos = tuple(
            dict.fromkeys(
                [
                    *(filters.video_ids or ()),
                    *([filters.video_id] if filters.video_id else []),
                ]
            )
        )
        if scope_videos:
            placeholders = ",".join("?" for _ in scope_videos)
            conditions.append(f"k.video_id IN ({placeholders})")
            parameters.extend(scope_videos)
        if filters.author:
            conditions.append("v.author = ?")
            parameters.append(filters.author)
        if date_from:
            conditions.append("v.publish_date_iso >= ?")
            parameters.append(date_from)
        if date_to:
            conditions.append("v.publish_date_iso <= ?")
            parameters.append(date_to)

        entities = tuple(dict.fromkeys(filters.object_entities))
        if entities:
            placeholders = ",".join("?" for _ in entities)
            if mode == "any":
                conditions.append(
                    "EXISTS (SELECT 1 FROM detections d "
                    "WHERE d.keyframe_id = k.keyframe_id "
                    f"AND d.entity IN ({placeholders}) AND d.score >= ?)"
                )
                parameters.extend(entities)
                parameters.append(minimum_confidence)
            else:
                conditions.append(
                    "(SELECT COUNT(DISTINCT d.entity) FROM detections d "
                    "WHERE d.keyframe_id = k.keyframe_id "
                    f"AND d.entity IN ({placeholders}) AND d.score >= ?) = ?"
                )
                parameters.extend(entities)
                parameters.extend([minimum_confidence, len(entities)])

        where = " AND ".join(conditions) if conditions else "1=1"
        query = (
            "SELECT k.vector_id FROM keyframes k "
            "JOIN videos v ON v.video_id = k.video_id "
            f"WHERE {where} ORDER BY k.vector_id"
        )
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return np.fromiter((int(row[0]) for row in rows), dtype=np.int64, count=len(rows))

    # One chunk of vectors in memory instead of every eligible row at once —
    # a broad filter on a 177k-keyframe release would otherwise copy ~360MB.
    SCORE_CHUNK_SIZE = 16_384

    def _search_filtered(
        self,
        query: np.ndarray,
        eligible_ids: np.ndarray,
        top_k: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        if eligible_ids.size == 0:
            return np.empty(0, dtype=np.float32), np.empty(0, dtype=np.int64)
        count = min(top_k, eligible_ids.size)
        all_scores = np.empty(eligible_ids.size, dtype=np.float32)
        for start in range(0, eligible_ids.size, self.SCORE_CHUNK_SIZE):
            stop = min(start + self.SCORE_CHUNK_SIZE, eligible_ids.size)
            vectors = np.asarray(
                self.embeddings[eligible_ids[start:stop]], dtype=np.float32
            )
            all_scores[start:stop] = vectors @ query[0]
        if count == eligible_ids.size:
            local_ids = np.argsort(all_scores)[::-1]
        else:
            candidates = np.argpartition(all_scores, -count)[-count:]
            local_ids = candidates[np.argsort(all_scores[candidates])[::-1]]
        return all_scores[local_ids], eligible_ids[local_ids]

    def _results_for_ids(
        self,
        vector_ids: Iterable[int],
        scores: Iterable[float],
    ) -> list[SearchResult]:
        ordered_ids = [int(value) for value in vector_ids]
        ordered_scores = [float(value) for value in scores]
        if not ordered_ids:
            return []
        placeholders = ",".join("?" for _ in ordered_ids)
        query = f"""
            SELECT k.vector_id, k.keyframe_id, k.video_id, k.collection_id,
                   k.keyframe_no, k.image_relpath, k.pts_time_sec, k.frame_idx,
                   k.fps, k.width, k.height, v.title, v.author
            FROM keyframes k
            JOIN videos v ON v.video_id = k.video_id
            WHERE k.vector_id IN ({placeholders})
        """
        with self._connect() as connection:
            by_id = {
                int(row["vector_id"]): dict(row)
                for row in connection.execute(query, ordered_ids).fetchall()
            }
        results = []
        for vector_id, score in zip(ordered_ids, ordered_scores, strict=True):
            results.append(self._row_to_result(by_id[vector_id], score))
        return results

    def get_temporal_window(
        self,
        keyframe_id: str,
        before: int = 5,
        after: int = 5,
    ) -> list[dict]:
        """Keyframes surrounding one selection, in time order, from the same video.

        Scores are 0.0 — these are neighbours, not ranked matches — so the caller can
        feed them straight into the same gallery renderer as a search result page.
        """
        with self._connect() as connection:
            target = connection.execute(
                "SELECT video_id, keyframe_no FROM keyframes WHERE keyframe_id = ?",
                (keyframe_id,),
            ).fetchone()
            if target is None:
                raise KeyError(f"Unknown keyframe: {keyframe_id}")
            rows = connection.execute(
                """
                SELECT k.*, v.title, v.author
                FROM keyframes k
                JOIN videos v ON v.video_id = k.video_id
                WHERE k.video_id = ? AND k.keyframe_no BETWEEN ? AND ?
                ORDER BY k.keyframe_no
                """,
                (
                    target["video_id"],
                    int(target["keyframe_no"]) - max(0, int(before)),
                    int(target["keyframe_no"]) + max(0, int(after)),
                ),
            ).fetchall()
        return [self._row_to_result(dict(row), 0.0).to_dict() for row in rows]

    def _row_to_result(self, row: dict, score: float) -> SearchResult:
        image_relpath = str(row["image_relpath"])
        return SearchResult(
            vector_id=int(row["vector_id"]),
            keyframe_id=str(row["keyframe_id"]),
            video_id=str(row["video_id"]),
            collection_id=str(row["collection_id"]),
            keyframe_no=int(row["keyframe_no"]),
            image_path=str(self.data_root / image_relpath),
            image_relpath=image_relpath,
            score=score,
            pts_time_sec=float(row["pts_time_sec"]),
            frame_idx=int(row["frame_idx"]),
            fps=float(row["fps"]),
            width=int(row["width"]),
            height=int(row["height"]),
            title=str(row["title"]),
            author=str(row["author"]),
        )

    def _ordered_results(self, where: str, parameters: list[Any]) -> list[SearchResult]:
        """All matching keyframes in canonical order (video, then keyframe_no),
        scored 1.0 because no similarity ranking is involved."""
        query = f"""
            SELECT k.vector_id, k.keyframe_id, k.video_id, k.collection_id,
                   k.keyframe_no, k.image_relpath, k.pts_time_sec, k.frame_idx,
                   k.fps, k.width, k.height, v.title, v.author
            FROM keyframes k
            JOIN videos v ON v.video_id = k.video_id
            WHERE {where}
            ORDER BY k.vector_id
        """
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._row_to_result(dict(row), 1.0) for row in rows]

    def get_video_keyframes(self, video_id: str) -> list[SearchResult]:
        return self._ordered_results("k.video_id = ?", [str(video_id)])

    def get_collection_keyframes(self, collection_id: str) -> list[SearchResult]:
        return self._ordered_results("k.collection_id = ?", [str(collection_id)])

    def find_exact_keyframe(
        self, video_id: str, keyframe_no: int
    ) -> SearchResult | None:
        rows = self._ordered_results(
            "k.video_id = ? AND k.keyframe_no = ?",
            [str(video_id), int(keyframe_no)],
        )
        return rows[0] if rows else None

    def get_keyframe_details(self, keyframe_id: str) -> KeyframeDetails:
        with self._connect() as connection:
            keyframe_row = connection.execute(
                "SELECT * FROM keyframes WHERE keyframe_id = ?",
                (keyframe_id,),
            ).fetchone()
            if keyframe_row is None:
                raise KeyError(f"Unknown keyframe: {keyframe_id}")
            video_row = connection.execute(
                "SELECT * FROM videos WHERE video_id = ?",
                (keyframe_row["video_id"],),
            ).fetchone()
            detection_rows = connection.execute(
                """
                SELECT rank, entity, class_mid, class_label, score,
                       ymin, xmin, ymax, xmax
                FROM detections WHERE keyframe_id = ?
                ORDER BY score DESC, rank ASC
                """,
                (keyframe_id,),
            ).fetchall()
        keyframe = dict(keyframe_row)
        keyframe["image_path"] = str(self.data_root / keyframe["image_relpath"])
        return KeyframeDetails(
            keyframe=keyframe,
            video=dict(video_row) if video_row is not None else {},
            detections=tuple(dict(row) for row in detection_rows),
        )
