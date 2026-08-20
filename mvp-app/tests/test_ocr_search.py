import sys
from unittest.mock import MagicMock

# Mock modules that might not be installed in the environment to avoid import crashes
sys.modules['sentence_transformers'] = MagicMock()
sys.modules['transformers'] = MagicMock()
sys.modules['pytest'] = MagicMock()

import unittest
import sqlite3
import numpy as np
import faiss
import tempfile
from pathlib import Path
from db import SearchMechanism, initialize_ocr_tables
from clusterer import ImageIndexer
from tests.test_search import FakeClipSearcher, FakeTranslator
from schemas import SearchFilters

class TestOcrSearch(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        
        self.data_root = self.tmp_path / "release"
        self.image_paths = [
            "keyframes/C01/V01/001.jpg",
            "keyframes/C01/V01/002.jpg",
            "keyframes/C02/V02/001.jpg",
        ]
        for relative_path in self.image_paths:
            path = self.data_root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"jpeg")

        embeddings = np.asarray([[1.0, 0.0], [0.8, 0.6], [0.0, 1.0]], dtype=np.float32)
        self.embeddings_file = self.tmp_path / "embeddings.npy"
        np.save(self.embeddings_file, embeddings.astype(np.float16))
        
        index = faiss.IndexFlatIP(2)
        index.add(embeddings)
        self.index_file = self.tmp_path / "keyframes.faiss"
        faiss.write_index(index, str(self.index_file))

        self.sqlite_file = self.tmp_path / "runtime.sqlite"
        connection = sqlite3.connect(self.sqlite_file)
        connection.executescript(
            """
            CREATE TABLE videos (
                video_id TEXT PRIMARY KEY, collection_id TEXT, title TEXT, author TEXT,
                channel_id TEXT, channel_url TEXT, description TEXT, keywords_json TEXT,
                duration_sec INTEGER, publish_date_raw TEXT, publish_date_iso TEXT,
                thumbnail_url TEXT, watch_url TEXT
            );
            CREATE TABLE keyframes (
                vector_id INTEGER PRIMARY KEY, keyframe_id TEXT UNIQUE, video_id TEXT,
                collection_id TEXT, keyframe_no INTEGER, frame_idx INTEGER,
                pts_time_sec REAL, fps REAL, width INTEGER, height INTEGER,
                image_relpath TEXT
            );
            CREATE TABLE detections (
                keyframe_id TEXT, rank INTEGER, entity TEXT, class_mid TEXT,
                class_label INTEGER, score REAL, ymin REAL, xmin REAL, ymax REAL, xmax REAL
            );
            """
        )
        connection.executemany(
            "INSERT INTO videos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("V01", "C01", "First video", "Alice", "channel-1", "", "description", "[]", 60, "01/01/2024", "2024-01-01", "", "https://example.com/watch?v=1"),
                ("V02", "C02", "Second video", "Bob", "channel-2", "", "", "[]", 90, "01/02/2024", "2024-02-01", "", "https://example.com/watch?v=2"),
            ],
        )
        connection.executemany(
            "INSERT INTO keyframes VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                (0, "V01_001", "V01", "C01", 1, 30, 1.0, 30.0, 640, 360, self.image_paths[0]),
                (1, "V01_002", "V01", "C01", 2, 60, 2.0, 30.0, 640, 360, self.image_paths[1]),
                (2, "V02_001", "V02", "C02", 1, 90, 3.0, 30.0, 1280, 720, self.image_paths[2]),
            ],
        )
        connection.commit()
        connection.close()

        initialize_ocr_tables(self.sqlite_file)

        # Insert sample OCR data
        connection = sqlite3.connect(self.sqlite_file)
        connection.executemany(
            "INSERT INTO ocr_texts VALUES (?, ?, ?)",
            [
                ("V01_001", "V01", "Cấm xe máy đi vào đường này"),
                ("V01_002", "V01", "Cảnh sát giao thông đang làm việc"),
            ]
        )
        connection.executemany(
            "INSERT INTO ocr_fts(keyframe_id, full_text) VALUES (?, ?)",
            [
                ("V01_001", "Cấm xe máy đi vào đường này"),
                ("V01_002", "Cảnh sát giao thông đang làm việc"),
            ]
        )
        connection.executemany(
            "INSERT INTO ocr_boxes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (1, "V01_001", "Cấm xe máy", 0.95, 0.1, 0.1, 0.3, 0.5),
                (2, "V01_002", "Cảnh sát", 0.90, 0.2, 0.2, 0.4, 0.6),
            ]
        )
        connection.commit()
        connection.close()

        self.store = SearchMechanism(
            FakeClipSearcher(),
            FakeTranslator(),
            ImageIndexer(self.index_file),
            self.sqlite_file,
            self.embeddings_file,
            self.data_root,
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_ocr_only_search(self):
        outcome = self.store.search_by_text("Cảnh sát", search_mode="ocr")
        self.assertEqual([res.keyframe_id for res in outcome.results], ["V01_002"])

    def test_hybrid_search(self):
        outcome = self.store.search_by_text("Cảnh sát", search_mode="hybrid", ocr_weight=0.8)
        self.assertEqual(outcome.results[0].keyframe_id, "V01_002")

    def test_get_keyframe_details_with_ocr(self):
        details = self.store.get_keyframe_details("V01_001")
        self.assertEqual(details.ocr_text, "Cấm xe máy đi vào đường này")
        self.assertEqual(len(details.ocr_boxes), 1)
        self.assertEqual(details.ocr_boxes[0]["text"], "Cấm xe máy")

if __name__ == "__main__":
    unittest.main()
