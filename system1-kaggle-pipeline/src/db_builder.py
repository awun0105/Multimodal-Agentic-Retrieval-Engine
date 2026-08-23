"""
Phase 03: Search Indexing & Database Packaging
Module xây dựng cơ sở dữ liệu SQLite FTS5 và Chỉ mục Vector FAISS SQ8.

Sản phẩm đầu ra:
1. runtime.sqlite: Bảng ảo FTS5 unicode61 remove_diacritics 2 gộp Tiêu đề, ASR, OCR và Thuộc tính KIS.
2. siglip.faiss: Chỉ mục vector lượng tử hóa SQ8 (METRIC_INNER_PRODUCT).

Hợp đồng dữ liệu đầu vào (Input):
- db_path: Đường dẫn lưu tệp SQLite.
- videos_meta, keyframes_meta, asr_meta, ocr_meta, semantics_meta: Danh sách dữ liệu từ Phase 00-02.
- vectors: Ma trận NumPy (N, 768) chuẩn hóa L2 = 1.0.

Hợp đồng dữ liệu đầu ra (Output):
- Tệp runtime.sqlite và siglip.faiss sẵn sàng nạp cho System 2 / MVP App.
"""

from __future__ import annotations
import sqlite3
import json
import numpy as np
from pathlib import Path
from typing import Any


def build_sqlite_database(
    db_path: Path | str,
    videos_meta: list[dict[str, Any]],
    keyframes_meta: list[dict[str, Any]],
    asr_meta: list[dict[str, Any]],
    ocr_meta: list[dict[str, Any]],
    semantics_meta: list[dict[str, Any]] | None = None
):
    """
    Xây dựng tệp runtime.sqlite hoàn chỉnh kèm dữ liệu phân tích KIS chuyên sâu.
    """
    db_path = str(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA synchronous=NORMAL;")

    # 1. Bảng videos
    cur.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            video_id TEXT PRIMARY KEY,
            title TEXT,
            author TEXT,
            length_sec REAL,
            watch_url TEXT,
            publish_date TEXT,
            category TEXT DEFAULT 'general',
            genre_dense_weight REAL DEFAULT 0.5,
            genre_sparse_weight REAL DEFAULT 0.5
        );
    """)

    # 2. Bảng keyframes
    cur.execute("""
        CREATE TABLE IF NOT EXISTS keyframes (
            keyframe_id INTEGER PRIMARY KEY,
            video_id TEXT,
            frame_id INTEGER,
            pts_time_sec REAL,
            sharpness REAL,
            keyframe_path TEXT,
            thumbnail_path TEXT,
            FOREIGN KEY (video_id) REFERENCES videos(video_id)
        );
    """)

    # 3. Bảng asr_segments (Lưu trữ lời thoại phân đoạn có dấu và mốc thời gian mili-giây)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS asr_segments (
            segment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT,
            start_sec REAL,
            end_sec REAL,
            text TEXT,
            FOREIGN KEY (video_id) REFERENCES videos(video_id)
        );
    """)

    # 4. Bảng ocr_items
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ocr_items (
            ocr_id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyframe_id INTEGER,
            video_id TEXT,
            text TEXT,
            confidence REAL,
            is_lower_third INTEGER,
            FOREIGN KEY (keyframe_id) REFERENCES keyframes(keyframe_id)
        );
    """)

    # 5. Bảng keyframe_semantics (Chuyên biệt cho KIS: màu sắc, góc máy, ánh sáng, không gian, số lượng)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS keyframe_semantics (
            keyframe_id INTEGER PRIMARY KEY,
            video_id TEXT,
            colors TEXT,
            camera_angle TEXT,
            lighting_time TEXT,
            environment_setting TEXT,
            objects_and_counts TEXT,
            objects_str TEXT,
            actions TEXT,
            dense_summary_vi TEXT,
            dense_summary_en TEXT,
            FOREIGN KEY (keyframe_id) REFERENCES keyframes(keyframe_id)
        );
    """)

    # 6. Bảng tìm kiếm toàn văn FTS5 tổng hợp (Full-Text Search)
    cur.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS text_documents_fts USING fts5(
            keyframe_id UNINDEXED,
            video_id UNINDEXED,
            source_type,
            content,
            tokenize='unicode61 remove_diacritics 2'
        );
    """)

    # 7. Bảng tìm kiếm FTS5 chuyên biệt cho Video QA ASR (Map trực tiếp start_sec / end_sec)
    cur.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS asr_fts USING fts5(
            segment_id UNINDEXED,
            video_id UNINDEXED,
            start_sec UNINDEXED,
            end_sec UNINDEXED,
            content,
            tokenize='unicode61 remove_diacritics 2'
        );
    """)

    # Nạp dữ liệu videos
    for v in videos_meta:
        cur.execute("""
            INSERT OR REPLACE INTO videos (video_id, title, author, length_sec, watch_url, publish_date, category, genre_dense_weight, genre_sparse_weight)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            v.get("video_id"),
            v.get("title", ""),
            v.get("author", ""),
            v.get("length_sec", 0.0),
            v.get("watch_url", ""),
            v.get("publish_date", ""),
            v.get("category", "general"),
            v.get("genre_dense_weight", 0.5),
            v.get("genre_sparse_weight", 0.5)
        ))

    # Nạp dữ liệu keyframes
    for k in keyframes_meta:
        cur.execute("""
            INSERT OR REPLACE INTO keyframes (keyframe_id, video_id, frame_id, pts_time_sec, sharpness, keyframe_path, thumbnail_path)
            VALUES (?, ?, ?, ?, ?, ?, ?);
        """, (k.get("keyframe_id"), k.get("video_id"), k.get("frame_id"), k.get("pts_time_sec"), k.get("sharpness", 0.0), k.get("keyframe_path", ""), k.get("thumbnail_path", "")))

    # Nạp dữ liệu ASR
    for a in asr_meta:
        cur.execute("""
            INSERT INTO asr_segments (video_id, start_sec, end_sec, text)
            VALUES (?, ?, ?, ?);
        """, (a.get("video_id"), a.get("start_sec"), a.get("end_sec"), a.get("text")))
        seg_id = cur.lastrowid
        cur.execute("""
            INSERT INTO text_documents_fts (keyframe_id, video_id, source_type, content)
            VALUES (NULL, ?, 'asr', ?);
        """, (a.get("video_id"), a.get("text")))
        cur.execute("""
            INSERT INTO asr_fts (segment_id, video_id, start_sec, end_sec, content)
            VALUES (?, ?, ?, ?, ?);
        """, (seg_id, a.get("video_id"), a.get("start_sec"), a.get("end_sec"), a.get("text")))

    # Nạp dữ liệu OCR
    for o in ocr_meta:
        cur.execute("""
            INSERT INTO ocr_items (keyframe_id, video_id, text, confidence, is_lower_third)
            VALUES (?, ?, ?, ?, ?);
        """, (o.get("keyframe_id"), o.get("video_id"), o.get("text"), o.get("confidence"), 1 if o.get("is_lower_third") else 0))
        cur.execute("""
            INSERT INTO text_documents_fts (keyframe_id, video_id, source_type, content)
            VALUES (?, ?, 'ocr', ?);
        """, (o.get("keyframe_id"), o.get("video_id"), o.get("text")))

    # Nạp dữ liệu Semantics KIS
    if semantics_meta:
        for s in semantics_meta:
            colors_str = ", ".join(s.get("colors", [])) if isinstance(s.get("colors"), list) else str(s.get("colors", ""))
            obj_cnt_str = ", ".join(s.get("objects_and_counts", [])) if isinstance(s.get("objects_and_counts"), list) else str(s.get("objects_and_counts", ""))
            actions_str = ", ".join(s.get("actions", [])) if isinstance(s.get("actions"), list) else str(s.get("actions", ""))

            obj_str_val = str(s.get("objects_str", ""))

            cur.execute("""
                INSERT OR REPLACE INTO keyframe_semantics (keyframe_id, video_id, colors, camera_angle, lighting_time, environment_setting, objects_and_counts, objects_str, actions, dense_summary_vi, dense_summary_en)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                s.get("keyframe_id"),
                s.get("video_id"),
                colors_str,
                s.get("camera_angle", ""),
                s.get("lighting_time", ""),
                s.get("environment_setting", ""),
                obj_cnt_str,
                obj_str_val,
                actions_str,
                s.get("dense_summary_vi", ""),
                s.get("dense_summary_en", "")
            ))

            # Đưa toàn bộ các thuộc tính KIS vào bảng tìm kiếm FTS5
            combined_kis_text = f"{colors_str} {s.get('camera_angle', '')} {s.get('lighting_time', '')} {s.get('environment_setting', '')} {obj_cnt_str} {obj_str_val} {actions_str} {s.get('dense_summary_vi', '')}"
            cur.execute("""
                INSERT INTO text_documents_fts (keyframe_id, video_id, source_type, content)
                VALUES (?, ?, 'kis_semantics', ?);
            """, (s.get("keyframe_id"), s.get("video_id"), combined_kis_text))

    conn.commit()
    conn.close()


def build_faiss_index(
    vectors: np.ndarray,
    index_output_path: Path | str,
    quantization: str = "SQ8"
):
    """
    Xây dựng chỉ mục FAISS tối ưu tìm kiếm Cosine Similarity trên CPU.
    Tự động fallback lưu npy nếu môi trường chưa cài faiss.
    """
    index_output_path = str(index_output_path)
    dim = vectors.shape[1]
    num_vectors = vectors.shape[0]

    try:
        import faiss
        if quantization == "SQ8" and num_vectors > 100:
            quantizer = faiss.IndexScalarQuantizer(dim, faiss.ScalarQuantizer.QT_8bit, faiss.METRIC_INNER_PRODUCT)
            quantizer.train(vectors)
            quantizer.add(vectors)
            faiss.write_index(quantizer, index_output_path)
        else:
            index = faiss.IndexFlatIP(dim)
            index.add(vectors)
            faiss.write_index(index, index_output_path)
        print(f"[FAISS] Đã tạo thành công chỉ mục FAISS: {index_output_path}")
    except ImportError:
        npy_fallback = Path(index_output_path).with_suffix(".npy")
        np.save(str(npy_fallback), vectors)
        print(f"[FALLBACK] Thư viện FAISS chưa cài trên môi trường này -> Đã lưu ma trận vector sang: {npy_fallback}")
