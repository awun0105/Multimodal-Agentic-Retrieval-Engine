"""Embedding retrieval with strict SQLite metadata filtering."""

from __future__ import annotations

import sqlite3
import re
import logging
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from clip import CLIPSearcher
from clusterer import ImageIndexer
from schemas import KeyframeDetails, SearchFilters, SearchOutcome, SearchResult
from translation import QueryTranslator


logger = logging.getLogger(__name__)


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

def initialize_ocr_tables(sqlite_file: str | Path) -> None:
    """Ensure the OCR tables exist in the runtime database."""
    db_path = Path(sqlite_file)
    if not db_path.is_file():
        return
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ocr_texts (
                keyframe_id TEXT PRIMARY KEY,
                video_id TEXT NOT NULL,
                full_text TEXT NOT NULL,
                FOREIGN KEY (keyframe_id) REFERENCES keyframes (keyframe_id)
            );
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ocr_boxes (
                box_id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyframe_id TEXT NOT NULL,
                text TEXT NOT NULL,
                score REAL NOT NULL,
                ymin REAL NOT NULL,
                xmin REAL NOT NULL,
                ymax REAL NOT NULL,
                xmax REAL NOT NULL,
                FOREIGN KEY (keyframe_id) REFERENCES keyframes (keyframe_id)
            );
            """
        )
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ocr_fts'"
        ).fetchone()
        if not exists:
            connection.execute(
                "CREATE VIRTUAL TABLE ocr_fts USING fts5(keyframe_id UNINDEXED, full_text);"
            )
            connection.execute(
                "INSERT INTO ocr_fts(keyframe_id, full_text) SELECT keyframe_id, full_text FROM ocr_texts;"
            )
        connection.commit()


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
        initialize_ocr_tables(self.sqlite_file)
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

    def _search_ocr_fts(self, query_text: str) -> dict[str, float]:
        """Perform FTS5 BM25 search on the ocr_fts table."""
        sanitized = re.sub(r'[^\w\s]', ' ', query_text).strip()
        if not sanitized:
            return {}
        sql = "SELECT keyframe_id, bm25(ocr_fts) FROM ocr_fts WHERE ocr_fts MATCH ?"
        with self._connect() as connection:
            try:
                rows = connection.execute(sql, (sanitized,)).fetchall()
            except sqlite3.OperationalError as exc:
                logger.warning("FTS5 query failed: %s. Retrying with simple quote query.", exc)
                try:
                    rows = connection.execute(sql, (f'"{sanitized}"',)).fetchall()
                except sqlite3.OperationalError:
                    return {}
        return {row[0]: -float(row[1]) for row in rows}

    def _map_keyframe_ids_to_vectors(self, keyframe_ids: list[str]) -> dict[str, int]:
        """Map a list of keyframe_ids to their corresponding vector_ids from the database."""
        if not keyframe_ids:
            return {}
        placeholders = ",".join("?" for _ in keyframe_ids)
        sql = f"SELECT keyframe_id, vector_id FROM keyframes WHERE keyframe_id IN ({placeholders})"
        with self._connect() as connection:
            rows = connection.execute(sql, keyframe_ids).fetchall()
        return {row[0]: int(row[1]) for row in rows}

    def search_by_text(
        self,
        query: str,
        top_k: int = 100,
        query_language: str = "auto",
        filters: SearchFilters | None = None,
        *,
        translate_vietnamese: bool | None = None,
        search_mode: str = "hybrid",
        ocr_weight: float = 0.5,
    ) -> SearchOutcome:
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
        filters = filters or SearchFilters()

        if search_mode == "ocr":
            # 1. OCR only
            ocr_results = self._search_ocr_fts(query)
            if not ocr_results:
                return SearchOutcome((), prepared)
            
            kf_to_vec = self._map_keyframe_ids_to_vectors(list(ocr_results.keys()))
            eligible_vector_ids = None
            if filters.active:
                eligible_vector_ids = set(self._eligible_vector_ids(filters))
            
            filtered_candidates = []
            for kf_id, ocr_score in ocr_results.items():
                vec_id = kf_to_vec.get(kf_id)
                if vec_id is not None:
                    if eligible_vector_ids is None or vec_id in eligible_vector_ids:
                        filtered_candidates.append((vec_id, ocr_score))
            
            filtered_candidates.sort(key=lambda x: x[1], reverse=True)
            top_candidates = filtered_candidates[:top_k]
            
            if not top_candidates:
                return SearchOutcome((), prepared)
            
            vector_ids = np.array([x[0] for x in top_candidates], dtype=np.int64)
            scores = np.array([x[1] for x in top_candidates], dtype=np.float32)
            results = self._results_for_ids(vector_ids, scores)
            return SearchOutcome(tuple(results), prepared)

        elif search_mode == "hybrid":
            # 2. Hybrid search (CLIP + OCR)
            clip_pool_size = max(top_k * 5, 200)
            if filters.active:
                eligible_ids = self._eligible_vector_ids(filters)
                if eligible_ids.size == 0:
                    return SearchOutcome((), prepared)
                clip_scores, clip_vector_ids = self._search_filtered(query_vector, eligible_ids, clip_pool_size)
            else:
                clip_scores, clip_vector_ids = self.image_indexer.search(query_vector, clip_pool_size)
                
            clip_results = {int(vec_id): float(score) for vec_id, score in zip(clip_vector_ids, clip_scores)}
            ocr_results = self._search_ocr_fts(query)
            
            # If no OCR results found, fallback to CLIP search
            if not ocr_results:
                results = self._results_for_ids(clip_vector_ids[:top_k], clip_scores[:top_k])
                return SearchOutcome(tuple(results), prepared)
            
            kf_to_vec = self._map_keyframe_ids_to_vectors(list(ocr_results.keys()))
            ocr_results_by_vec = {}
            for kf_id, ocr_score in ocr_results.items():
                vec_id = kf_to_vec.get(kf_id)
                if vec_id is not None:
                    ocr_results_by_vec[vec_id] = ocr_score
            
            union_vector_ids = set(clip_results.keys()).union(ocr_results_by_vec.keys())
            if filters.active:
                eligible_vector_ids = set(eligible_ids)
                union_vector_ids = union_vector_ids.intersection(eligible_vector_ids)
            
            if not union_vector_ids:
                return SearchOutcome((), prepared)
            
            # MinMax normalize CLIP scores in candidates
            clip_scores_vals = [clip_results[v] for v in union_vector_ids if v in clip_results]
            max_clip = max(clip_scores_vals) if clip_scores_vals else 1.0
            min_clip = min(clip_scores_vals) if clip_scores_vals else 0.0
            clip_span = max_clip - min_clip
            
            # MinMax normalize OCR scores in candidates
            ocr_scores_vals = [ocr_results_by_vec[v] for v in union_vector_ids if v in ocr_results_by_vec]
            max_ocr = max(ocr_scores_vals) if ocr_scores_vals else 1.0
            min_ocr = min(ocr_scores_vals) if ocr_scores_vals else 0.0
            ocr_span = max_ocr - min_ocr
            
            combined_candidates = []
            for vec_id in union_vector_ids:
                c_score = clip_results.get(vec_id, 0.0)
                if vec_id in clip_results:
                    norm_c = (c_score - min_clip) / clip_span if clip_span > 0 else 1.0
                else:
                    norm_c = 0.0
                
                o_score = ocr_results_by_vec.get(vec_id, 0.0)
                if vec_id in ocr_results_by_vec:
                    norm_o = (o_score - min_ocr) / ocr_span if ocr_span > 0 else 1.0
                else:
                    norm_o = 0.0
                
                fusion_score = (1.0 - ocr_weight) * norm_c + ocr_weight * norm_o
                combined_candidates.append((vec_id, fusion_score))
            
            combined_candidates.sort(key=lambda x: x[1], reverse=True)
            top_candidates = combined_candidates[:top_k]
            
            vector_ids = np.array([x[0] for x in top_candidates], dtype=np.int64)
            scores = np.array([x[1] for x in top_candidates], dtype=np.float32)
            results = self._results_for_ids(vector_ids, scores)
            return SearchOutcome(tuple(results), prepared)
        
        else:
            # 3. CLIP only (Standard)
            if filters.active:
                eligible_ids = self._eligible_vector_ids(filters)
                scores, vector_ids = self._search_filtered(query_vector, eligible_ids, top_k)
            else:
                scores, vector_ids = self.image_indexer.search(query_vector, top_k)
            results = self._results_for_ids(vector_ids, scores)
            return SearchOutcome(tuple(results), prepared)

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
        if filters.video_id:
            conditions.append("k.video_id = ?")
            parameters.append(filters.video_id)
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

    def _search_filtered(
        self,
        query: np.ndarray,
        eligible_ids: np.ndarray,
        top_k: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        if eligible_ids.size == 0:
            return np.empty(0, dtype=np.float32), np.empty(0, dtype=np.int64)
        vectors = np.asarray(self.embeddings[eligible_ids], dtype=np.float32)
        scores = vectors @ query[0]
        count = min(top_k, eligible_ids.size)
        if count == eligible_ids.size:
            local_ids = np.argsort(scores)[::-1]
        else:
            candidates = np.argpartition(scores, -count)[-count:]
            local_ids = candidates[np.argsort(scores[candidates])[::-1]]
        return scores[local_ids], eligible_ids[local_ids]

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
            row = by_id[vector_id]
            image_relpath = str(row["image_relpath"])
            results.append(
                SearchResult(
                    vector_id=vector_id,
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
            )
        return results

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
            
            # Query OCR text
            try:
                ocr_text_row = connection.execute(
                    "SELECT full_text FROM ocr_texts WHERE keyframe_id = ?",
                    (keyframe_id,),
                ).fetchone()
                ocr_text = ocr_text_row[0] if ocr_text_row is not None else None
            except sqlite3.OperationalError:
                ocr_text = None

            # Query OCR boxes
            try:
                ocr_box_rows = connection.execute(
                    "SELECT text, score, ymin, xmin, ymax, xmax FROM ocr_boxes WHERE keyframe_id = ?",
                    (keyframe_id,),
                ).fetchall()
                ocr_boxes = tuple(dict(row) for row in ocr_box_rows)
            except sqlite3.OperationalError:
                ocr_boxes = ()

        keyframe = dict(keyframe_row)
        keyframe["image_path"] = str(self.data_root / keyframe["image_relpath"])
        return KeyframeDetails(
            keyframe=keyframe,
            video=dict(video_row) if video_row is not None else {},
            detections=tuple(dict(row) for row in detection_rows),
            ocr_text=ocr_text,
            ocr_boxes=ocr_boxes,
        )
