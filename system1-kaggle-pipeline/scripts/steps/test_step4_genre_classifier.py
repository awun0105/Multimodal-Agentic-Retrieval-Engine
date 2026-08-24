"""
Kịch bản kiểm thử độc lập Step 4: Phân loại thể loại video từ siêu dữ liệu (Metadata Genre Classifier).
Chạy độc lập trên danh sách tiêu đề video tiếng Việt thực tế.
"""

from __future__ import annotations
import sys
from pathlib import Path

# Dam bao UTF-8 tren Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Thêm src vào đường dẫn
SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from genre_classifier import VideoGenreClassifier


def test_genre_classification():
    print("=" * 70)
    print("KIỂM THỬ ĐỘC LẬP: PHÂN LOẠI THỂ LOẠI VIDEO TỪ METADATA (STEP 4)")
    print("=" * 70)

    test_cases = [
        {"title": "Bản tin Thời sự 19h ngày 22/08/2026 - VTV1", "author": "VTV Go", "expected": "news"},
        {"title": "Điểm tin Chuyển động 24h trưa nay", "author": "Trung tâm Tin tức VTV24", "expected": "news"},
        {"title": "Bài giảng Toán lớp 12: Khảo sát hàm số nâng cao", "author": "Thầy Nguyễn Quốc Chí", "expected": "education"},
        {"title": "Ôn thi Tốt nghiệp THPT môn Lịch sử - Chữa đề thi thử", "author": "Cô Hương Giáo Dục", "expected": "education"},
        {"title": "Highlight Trận đấu Chung kết V-League 2026", "author": "VFF Channel", "expected": "sports"},
        {"title": "Siêu phẩm bàn thắng đẹp nhất vòng 10 Ngoại Hạng Anh", "author": "FPT Play Thể Thao", "expected": "sports"},
        {"title": "Gameshow Thách Thức Danh Hài Mùa Mới - Tập 1", "author": "Điền Quân Entertainment", "expected": "entertainment"},
        {"title": "Vlog Ẩm thực đường phố Sài Gòn về đêm", "author": "Khoai Lang Thang", "expected": "entertainment"},
        {"title": "Khám phá phong cảnh thiên nhiên Tây Bắc mùa lúa chín", "author": "Traveler Vietnam", "expected": "general"}
    ]

    correct_count = 0
    for idx, case in enumerate(test_cases, 1):
        res = VideoGenreClassifier.classify(title=case["title"], author=case["author"])
        is_pass = res["category"] == case["expected"]
        if is_pass:
            correct_count += 1
            status = "DAT"
        else:
            status = "KHONG DAT"

        print(f"[{idx}/{len(test_cases)}] {status}: '{case['title'][:40]}...'")
        print(f"       -> Nhan: {res['category']} (Ky vong: {case['expected']}) | Trong so: Dense {res['dense_weight']} / Sparse {res['sparse_weight']}")

    print("=" * 70)
    acc = (correct_count / len(test_cases)) * 100
    print(f"KET QUA: {correct_count}/{len(test_cases)} ({acc:.1f}%) TEST CASES DAT CHUAN.")
    print("=" * 70)
    assert correct_count == len(test_cases), "Co test case chua dat!"


if __name__ == "__main__":
    test_genre_classification()
