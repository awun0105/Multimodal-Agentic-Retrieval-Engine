"""
Module: Vietnamese Cultural & Rare Lexicon (Lớp Đọc Từ Hiếm & Khái Niệm Bản Địa)
Phục vụ phân hệ System 1 (AIC 2026):
- Bóc tách và nhận diện các khái niệm văn hóa, trang phục, ẩm thực, lễ hội, phương tiện đặc thù của Việt Nam.
- Ánh xạ sang mô tả thị giác tương đương (Fact-Grounded Visual Anchors) để mô hình Vision Embedding (SigLIP) hiểu chính xác.
- Tuân thủ nghiêm ngặt nguyên tắc TRUNG THỰC (No-Hallucination Rule): Chỉ làm giàu chi tiết thị giác của thực thể đã có trong câu gốc, không tự tiện thêm bối cảnh hay màu sắc ngoài luồng.
"""

from __future__ import annotations
import re
from typing import Any


VIETNAMESE_CULTURAL_LEXICON: dict[str, dict[str, Any]] = {
    # 1. LỄ HỘI & BIỂU DIỄN DÂN GIAN
    "múa lân": {
        "canonical_name": "Múa lân",
        "aliases": ["múa lân", "con lân", "đầu lân", "lân sư rồng", "múa sư tử", "lân rồng"],
        "category": "festival_performance",
        "visual_anchor_en": "traditional Vietnamese lion dance costume performance with lion head and drums",
        "keywords_vi": ["múa lân", "lân sư rồng", "đầu lân"]
    },
    "ông địa": {
        "canonical_name": "Ông Địa",
        "aliases": ["ông địa", "thần tài ông địa", "mặt nạ ông địa", "bụng bự cầm quạt"],
        "category": "folk_character",
        "visual_anchor_en": "traditional round-faced smiling folk character wearing mask and holding palm leaf fan",
        "keywords_vi": ["ông địa", "mặt nạ ông địa"]
    },
    "đèn ông sao": {
        "canonical_name": "Đèn ông sao",
        "aliases": ["đèn ông sao", "lồng đèn trung thu", "đèn ngôi sao", "lồng đèn ông sao"],
        "category": "festival_lantern",
        "visual_anchor_en": "traditional five-pointed star lantern made of bamboo frame and colorful cellophane paper",
        "keywords_vi": ["đèn ông sao", "lồng đèn trung thu"]
    },
    "đờn ca tài tử": {
        "canonical_name": "Đờn ca tài tử",
        "aliases": ["đờn ca tài tử", "hát cải lương", "đàn kìm", "nhã nhạc cung đình"],
        "category": "traditional_music",
        "visual_anchor_en": "traditional southern Vietnamese folk music ensemble performance with string instruments",
        "keywords_vi": ["đờn ca tài tử", "cải lương"]
    },

    # 2. TRANG PHỤC & PHỤ KIỆN TRUYỀN THỐNG
    "áo dài": {
        "canonical_name": "Áo dài",
        "aliases": ["áo dài", "áo dài truyền thống", "áo dài cách tân", "áo dài nữ", "áo dài nam"],
        "category": "traditional_clothing",
        "visual_anchor_en": "Vietnamese traditional long tunic dress worn over trousers",
        "keywords_vi": ["áo dài", "áo dài truyền thống"]
    },
    "áo bà ba": {
        "canonical_name": "Áo bà ba",
        "aliases": ["áo bà ba", "áo bà ba nam bộ", "áo bà ba đen", "áo bà ba nâu"],
        "category": "traditional_clothing",
        "visual_anchor_en": "traditional southern Vietnamese silk button-down everyday shirt with two lower pockets",
        "keywords_vi": ["áo bà ba", "nam bộ"]
    },
    "nón lá": {
        "canonical_name": "Nón lá",
        "aliases": ["nón lá", "nón bài thơ", "nón chóp", "nón lá cọ"],
        "category": "traditional_accessory",
        "visual_anchor_en": "traditional conical palm leaf hat worn by Vietnamese people",
        "keywords_vi": ["nón lá", "nón bài thơ"]
    },
    "nón quai thao": {
        "canonical_name": "Nón quai thao",
        "aliases": ["nón quai thao", "nón ba tầm", "nón quan họ"],
        "category": "traditional_accessory",
        "visual_anchor_en": "large flat round traditional Vietnamese hat worn with long silk ribbons",
        "keywords_vi": ["nón quai thao", "quan họ"]
    },

    # 3. PHƯƠNG TIỆN & BỐI CẢNH ĐẶC THÙ
    "xe xích lô": {
        "canonical_name": "Xe xích lô",
        "aliases": ["xe xích lô", "xích lô", "cyclo", "xe xích lô đạp"],
        "category": "transportation",
        "visual_anchor_en": "three-wheeled passenger tricycle with front passenger seat and rear pedaler",
        "keywords_vi": ["xích lô", "cyclo"]
    },
    "xe ba gác": {
        "canonical_name": "Xe ba gác",
        "aliases": ["xe ba gác", "ba gác máy", "xe lôi", "xe ba bánh"],
        "category": "transportation",
        "visual_anchor_en": "three-wheeled motorized cargo tricycle with rear open cargo bed",
        "keywords_vi": ["xe ba gác", "ba gác"]
    },
    "chợ nổi": {
        "canonical_name": "Chợ nổi",
        "aliases": ["chợ nổi", "chợ trên sông", "chợ nổi cái răng", "chợ nổi phong điền"],
        "category": "scenery_lifestyle",
        "visual_anchor_en": "vibrant floating market with wooden boats and canoes selling fruits and goods on river canal",
        "keywords_vi": ["chợ nổi", "trên sông"]
    },
    "ghe thuyền": {
        "canonical_name": "Ghe / Xuồng ba lá",
        "aliases": ["ghe", "xuồng ba lá", "thuyền tam bản", "vỏ lãi", "ghe thuyền"],
        "category": "transportation",
        "visual_anchor_en": "traditional wooden canoe boat or long-tail motorized boat navigating waterway",
        "keywords_vi": ["xuồng ba lá", "ghe thuyền", "vỏ lãi"]
    },

    # 4. ẨM THỰC TRUYỀN THỐNG
    "bánh chưng": {
        "canonical_name": "Bánh chưng",
        "aliases": ["bánh chưng", "bánh tét", "bánh chưng xanh", "bánh chưng tết"],
        "category": "traditional_food",
        "visual_anchor_en": "square green sticky rice cake wrapped in banana or dong leaves tied with bamboo strings",
        "keywords_vi": ["bánh chưng", "bánh tét"]
    },
    "cà phê sữa đá": {
        "canonical_name": "Cà phê sữa đá",
        "aliases": ["cà phê sữa đá", "cà phê phin", "cà phê đá", "nâu đá"],
        "category": "beverage",
        "visual_anchor_en": "iced coffee with condensed milk in a transparent glass with straw",
        "keywords_vi": ["cà phê sữa đá", "cà phê phin"]
    },

    # 5. BIỂU TƯỢNG QUỐC GIA & ĐỊA DANH
    "cờ tổ quốc": {
        "canonical_name": "Cờ Tổ quốc",
        "aliases": ["cờ tổ quốc", "cờ đỏ sao vàng", "quốc kỳ việt nam", "quốc kỳ", "lá cờ việt nam"],
        "category": "national_symbol",
        "visual_anchor_en": "Vietnamese national flag, bright red banner with large five-pointed central yellow star",
        "keywords_vi": ["cờ đỏ sao vàng", "quốc kỳ"]
    }
}


import unicodedata


def remove_accents(text: str) -> str:
    """Loại bỏ dấu tiếng Việt để so khớp không dấu."""
    if not text or not isinstance(text, str):
        return ""
    text = text.replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def lookup_cultural_concepts(query_vi: str) -> list[dict[str, Any]]:
    """
    Phát hiện và trích xuất các khái niệm văn hóa thuần Việt có trong câu truy vấn (hỗ trợ cả có dấu và không dấu).
    """
    if not query_vi or not isinstance(query_vi, str):
        return []

    q_lower = query_vi.lower().strip()
    q_no_acc = remove_accents(q_lower)
    detected = []
    matched_keys = set()

    for key, entity in VIETNAMESE_CULTURAL_LEXICON.items():
        if key in matched_keys:
            continue
        for alias in entity["aliases"]:
            alias_lower = alias.lower()
            alias_no_acc = remove_accents(alias_lower)
            
            # Khớp từ nguyên vẹn hoặc cụm từ (cả có dấu và không dấu)
            pattern_acc = rf"\b{re.escape(alias_lower)}\b"
            pattern_no_acc = rf"\b{re.escape(alias_no_acc)}\b"
            
            m_acc = re.search(pattern_acc, q_lower)
            m_no_acc = re.search(pattern_no_acc, q_no_acc)
            
            if m_acc or m_no_acc:
                start_pos = m_acc.start() if m_acc else m_no_acc.start()
                detected.append({
                    "start_pos": start_pos,
                    "matched_term": alias,
                    "canonical_name": entity["canonical_name"],
                    "category": entity["category"],
                    "visual_anchor_en": entity["visual_anchor_en"],
                    "keywords_vi": entity["keywords_vi"]
                })
                matched_keys.add(key)
                break

    # Sắp xếp theo thứ tự xuất hiện trong câu
    detected.sort(key=lambda x: x["start_pos"])
    return detected


def enrich_query_faithfully(
    query_vi: str,
    translated_text_en: str = ""
) -> dict[str, Any]:
    """
    Làm giàu câu truy vấn theo nguyên tắc TRUNG THỰC (Faithful & Fact-Grounded):
    - Không thêm thắt các chi tiết hư cấu (màu sắc, thời gian, hành động không có trong câu gốc).
    - Mở rộng các khái niệm văn hóa thuần Việt sang mô tả thị giác tương đương chuẩn xác trong tiếng Anh.
    - Trả về: dict chứa query tiếng Việt, query tiếng Anh gốc, query tiếng Anh làm giàu, và danh sách thực thể phát hiện.
    """
    query_clean = str(query_vi).strip() if query_vi else ""
    detected_concepts = lookup_cultural_concepts(query_clean)

    # Tạo query tiếng Anh làm giàu
    enriched_en_parts = []
    if translated_text_en:
        enriched_en = translated_text_en.strip()
    else:
        enriched_en = query_clean

    # Nếu có khái niệm văn hóa bản địa, chèn mô tả thị giác tương đương
    if detected_concepts:
        anchors = [c["visual_anchor_en"] for c in detected_concepts]
        anchor_str = " | ".join(anchors)
        if enriched_en and enriched_en != query_clean:
            final_enriched_en = f"{enriched_en} ({anchor_str})"
        else:
            final_enriched_en = f"{query_clean} ({anchor_str})"
    else:
        final_enriched_en = enriched_en

    fts_keywords = []
    for c in detected_concepts:
        fts_keywords.extend(c["keywords_vi"])

    return {
        "raw_query_vi": query_clean,
        "translated_en_raw": translated_text_en,
        "enriched_query_en": final_enriched_en,
        "detected_cultural_concepts": [c["canonical_name"] for c in detected_concepts],
        "fts_boost_keywords": list(set(fts_keywords))
    }
