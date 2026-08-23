"""
BƯỚC 4: KIỂM THỬ XÂY DỰNG CƠ SỞ DỮ LIỆU SQLITE FTS5 & TRUY VẤN TÌM KIẾM.
"""

from __future__ import annotations
import sys
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "system1-kaggle-pipeline" / "test_output"


def test_real_database():
    print("=" * 70)
    print("BƯỚC 4: KIỂM THỬ XÂY DỰNG SQLITE FTS5 & TRUY VẤN TÌM KIẾM (REAL DATA)")
    print("=" * 70)
    db_path = OUTPUT_DIR / "quick_step4_test.sqlite"
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("CREATE VIRTUAL TABLE text_fts USING fts5(video_id, content, tokenize='unicode61 remove_diacritics 2');")
    cur.execute("INSERT INTO text_fts VALUES ('L21_V001', 'Bản tin 60 giây HTV cập nhật tin tức thời sự TP Hồ Chí Minh');")
    cur.execute("SELECT video_id, snippet(text_fts, 1, '[', ']', '...', 6) FROM text_fts WHERE text_fts MATCH 'thời sự';")
    row = cur.fetchone()
    print(f"  -> Truy vấn FTS5 'thời sự' ➔ Khớp Video {row[0]}: {row[1]}")
    conn.close()
    if db_path.exists():
        db_path.unlink()
    print("=" * 70)


if __name__ == "__main__":
    test_real_database()
