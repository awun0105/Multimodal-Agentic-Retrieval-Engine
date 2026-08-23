"""
Phase 00: Metadata Ingestion & Video Genre Classification
Module phân loại thể loại video từ siêu dữ liệu (Title, Author, Description) siêu nhẹ.

Chức năng:
1. Nhận diện 5 nhóm thể loại chính: news, education, sports, entertainment, general.
2. Cung cấp cấu hình trọng số tìm kiếm RRF (Dynamic Weight Routing) giữa SigLIP Dense và FTS5 Sparse.

Hợp đồng dữ liệu đầu vào (Input):
- title (str): Tiêu đề video.
- author (str): Tên kênh / Tác giả / Đài truyền hình.
- description (str): Mô tả tóm tắt nếu có.

Hợp đồng dữ liệu đầu ra (Output):
- Dict: {"category": str, "dense_weight": float, "sparse_weight": float, "reasons": list[str]}.
"""

from __future__ import annotations
import re
from typing import Any


class VideoGenreClassifier:
    """
    Bộ phân loại thể loại video đa tầng dựa trên Regex và Từ khóa chuyên ngành tiếng Việt.
    Tốc độ: < 0.1ms / video.
    """

    GENRE_PATTERNS = {
        "news": [
            r"\b(thời\s*sự|tin\s*tức|bản\s*tin|tin\s*nóng|chuyển\s*động\s*24h|vtv|htv|vov|truyền\s*hình|phóng\s*sự|điểm\s*tin|toàn\s*cảnh|chính\s*trị|kinh\s*tế|xã\s*hội|dự\s*báo\s*thời\s*tiết)\b",
            r"\b(breaking\s*news|daily\s*news|reportage|journalism)\b"
        ],
        "education": [
            r"\b(bài\s*giảng|ôn\s*thi|học\s*tập|toán|văn|vật\s*lý|hóa\s*học|tiếng\s*anh|sinh\s*học|lịch\s*sử|địa\s*lý|giáo\s*dục|hướng\s*dẫn|thầy|cô|lớp\s*\d+|đề\s*thi|chữa\s*đề|khóa\s*học)\b",
            r"\b(lecture|tutorial|education|course|lesson|mathematics|physics|exam)\b"
        ],
        "sports": [
            r"\b(bóng\s*đá|thể\s*thao|highlight|trận\s*đấu|v-league|world\s*cup|ngoại\s*hạng|bàn\s*thắng|bóng\s*chuyền|cầu\s*lông|quần\s*vợt|tennis|futsal|sea\s*games|olympic|tuyển\s*thủ|huấn\s*luyện\s*viên)\b",
            r"\b(football|soccer|sports|highlights|match|goals|champion)\b"
        ],
        "entertainment": [
            r"\b(gameshow|game\s*show|phim|ca\s*nhạc|vlog|giải\s*trí|hài\s*kịch|talkshow|talk\s*show|mv|nhạc\s*sống|ẩm\s*thực|du\s*lịch|phố\s*đi\s*bộ|hài\s*hước|tiểu\s*phẩm|thách\s*thức)\b",
            r"\b(entertainment|movie|music|comedy|drama|reality\s*show)\b"
        ]
    }

    # Cấu hình trọng số tìm kiếm tương ứng từng thể loại
    GENRE_WEIGHTS = {
        "news": {"dense_weight": 0.4, "sparse_weight": 0.6},        # Ưu tiên chữ OCR/ASR
        "education": {"dense_weight": 0.35, "sparse_weight": 0.65},  # Ưu tiên chữ bài giảng & lời thầy cô
        "sports": {"dense_weight": 0.75, "sparse_weight": 0.25},     # Ưu tiên hình ảnh & vật thể chuyển động
        "entertainment": {"dense_weight": 0.6, "sparse_weight": 0.4},# Cân bằng hình ảnh nhân vật & lời thoại
        "general": {"dense_weight": 0.5, "sparse_weight": 0.5}       # Mặc định cân bằng 50-50
    }

    @classmethod
    def classify(cls, title: str = "", author: str = "", description: str = "") -> dict[str, Any]:
        """
        Phân tích và trả về nhãn thể loại cùng trọng số tìm kiếm tối ưu.
        """
        full_text = f"{title} {author} {description}".lower()
        matched_reasons = []

        for genre, patterns in cls.GENRE_PATTERNS.items():
            for pattern in patterns:
                matches = re.findall(pattern, full_text)
                if matches:
                    matched_reasons.append(f"Khớp từ khóa {genre}: {', '.join(matches[:3])}")
                    weights = cls.GENRE_WEIGHTS[genre]
                    return {
                        "category": genre,
                        "dense_weight": weights["dense_weight"],
                        "sparse_weight": weights["sparse_weight"],
                        "reasons": matched_reasons
                    }

        # Mặc định thể loại chung
        weights = cls.GENRE_WEIGHTS["general"]
        return {
            "category": "general",
            "dense_weight": weights["dense_weight"],
            "sparse_weight": weights["sparse_weight"],
            "reasons": ["Không khớp mẫu đặc thù, sử dụng trọng số cân bằng tiêu chuẩn"]
        }
