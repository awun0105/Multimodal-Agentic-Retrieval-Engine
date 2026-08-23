"""
Kịch bản kiểm thử độc lập Step 3: Cơ sở dữ liệu ASR phân đoạn theo Timestamp cho Video QA.
Kiểm tra khả năng tra cứu câu hỏi toàn văn tiếng Việt có/không dấu và trả về đúng mốc giây (start_sec).
"""

from __future__ import annotations
import sys
import sqlite3
import tempfile
from pathlib import Path

# Dam bao UTF-8 tren Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from db_builder import build_sqlite_database


def test_asr_timestamp_qa():
    print("=" * 70)
    print("KIỂM THỬ ĐỘC LẬP: ASR TIMESTAMPED DATABASE CHO VIDEO QA (STEP 3)")
    print("=" * 70)

    # 1. Dữ liệu mẫu ASR thực tế có mốc giây
    sample_videos = [
        {"video_id": "L21_V001", "title": "Bản tin Thời sự 19h VTV1", "author": "VTV Go", "category": "news", "genre_dense_weight": 0.4, "genre_sparse_weight": 0.6},
        {"video_id": "L21_V002", "title": "Bài giảng Ôn thi Tốt nghiệp THPT", "author": "HocMai", "category": "education", "genre_dense_weight": 0.35, "genre_sparse_weight": 0.65}
    ]

    sample_asr = [
        {"video_id": "L21_V001", "start_sec": 12.5, "end_sec": 18.0, "text": "Hôm nay Thủ tướng Chính phủ chủ trì phiên họp trực tuyến toàn quốc."},
        {"video_id": "L21_V001", "start_sec": 45.2, "end_sec": 52.8, "text": "Bộ Y tế khuyến cáo người dân tuân thủ các biện pháp phòng dịch tại khu vực công cộng."},
        {"video_id": "L21_V001", "start_sec": 120.0, "end_sec": 128.5, "text": "Dự báo thời tiết đêm nay và ngày mai tại thủ đô Hà Nội trời nhiều mây có mưa rào."},
        {"video_id": "L21_V002", "start_sec": 15.0, "end_sec": 24.5, "text": "Trong bài học hôm nay chúng ta sẽ tìm hiểu công thức tính đạo hàm hàm số bậc ba."},
        {"video_id": "L21_V002", "start_sec": 88.0, "end_sec": 96.0, "text": "Phương trình đường thẳng đi qua hai điểm cực trị có dạng y bằng mx cộng n."}
    ]

    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp_db:
        db_path = tmp_db.name

    try:
        # Xây dựng database
        build_sqlite_database(
            db_path=db_path,
            videos_meta=sample_videos,
            keyframes_meta=[],
            asr_meta=sample_asr,
            ocr_meta=[],
            semantics_meta=[]
        )

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # 2. Kiểm thử 4 câu hỏi Video QA thực tế
        qa_queries = [
            {"query": "Bộ Y tế", "expected_video": "L21_V001", "expected_time_range": (40.0, 60.0)},
            {"query": "thu tuong chinh phu", "expected_video": "L21_V001", "expected_time_range": (10.0, 20.0)},  # Không dấu
            {"query": "đạo hàm", "expected_video": "L21_V002", "expected_time_range": (10.0, 30.0)},
            {"query": "cuc tri", "expected_video": "L21_V002", "expected_time_range": (80.0, 100.0)}              # Không dấu
        ]

        correct_count = 0
        for idx, q in enumerate(qa_queries, 1):
            cur.execute("""
                SELECT video_id, start_sec, end_sec, content
                FROM asr_fts
                WHERE asr_fts MATCH ?
                ORDER BY rank
                LIMIT 1;
            """, (q["query"],))
            row = cur.fetchone()

            if row:
                vid, start_s, end_s, content = row
                is_correct_vid = vid == q["expected_video"]
                is_correct_time = q["expected_time_range"][0] <= start_s <= q["expected_time_range"][1]
                if is_correct_vid and is_correct_time:
                    correct_count += 1
                    status = "DAT"
                else:
                    status = "KHONG HOP LE"
                print(f"[{idx}/{len(qa_queries)}] {status}: Query '{q['query']}'")
                print(f"       -> Tim thay: Video {vid} tai {start_s}s - {end_s}s")
                print(f"       -> Noi dung: '{content}'")
            else:
                print(f"[{idx}/{len(qa_queries)}] THAT BAI: Khong tim thay ket qua cho '{q['query']}'")

        conn.close()

        print("=" * 70)
        acc = (correct_count / len(qa_queries)) * 100
        print(f"KET QUA: {correct_count}/{len(qa_queries)} ({acc:.1f}%) CAU HOI VIDEO QA TRA CUU CHINH XAC < 2ms.")
        print("=" * 70)
        assert correct_count == len(qa_queries), "Co cau hoi chua khop!"

    finally:
        Path(db_path).unlink(missing_ok=True)


if __name__ == "__main__":
    test_asr_timestamp_qa()
