"""
====================================================================================================
SERVICES - DECOUPLED DUAL-CHANNEL BILINGUAL CAPTIONS (caption_service.py)
====================================================================================================

1. MỤC TIÊU VÀ VAI TRÒ:
   - Module này triển khai cơ chế sinh miêu tả song ngữ tự thân độc lập (Decoupled Dual-Channel):
     a) Kênh Tiếng Việt: Bối cảnh khách quan + Phụ lục `[Thực thể nhận diện: ...]`.
     b) Kênh Tiếng Anh: 100% Pure English Prompt + Phụ lục `[Detected entities: ...]`.
   - Ngăn ngừa hiện tượng bóp méo vector ngữ nghĩa khi YOLO Local bắt nhầm hoặc thiếu vật thể.

2. CÁC HÀM CỐT LÕI:
   - `generate_keyframe_bilingual_captions(...)`: Trả về tuple `(caption_vi, caption_en)` chuẩn hóa.
====================================================================================================
"""

from __future__ import annotations
import re


def generate_keyframe_bilingual_captions(
    meaning: str,
    scene: str,
    objects: str = "",
    natural_vi_objects: str = "",
    natural_en_objects: str = "",
    ocr: str = "",
    color: str = "",
    cultural_concepts: list = None,
    is_virtual: bool = False,
    delta_tag: str = "",
    anchor_id: str = ""
) -> tuple[str, str]:
    """
    Sinh cặp miêu tả song ngữ tự thân hoàn toàn độc lập và khách quan (Decoupled Dual-Channel):
    1. Kênh Tiếng Việt:
       - Mô tả bối cảnh cốt lõi tự thân độc lập (Visual Semantic Grounding).
       - Phụ lục thực thể nhận diện tự nhiên gắn ở cuối câu [Thực thể nhận diện: 1 người mặc áo đen, 2 chiếc xe ô tô màu tím].
       - Đảm bảo câu bối cảnh chính không bị bóp méo khi YOLO bắt nhầm vật thể.
    2. Kênh Tiếng Anh:
       - 100% Pure English Scene Description độc lập, tự thân khách quan.
       - Phụ lục thực thể Tiếng Anh gắn ở cuối câu: [Detected entities: 1 person in black clothes, 2 purple cars].
       - Tuyệt đối không lẫn bất kỳ từ tiếng Việt nào vào prompt của SigLIP SO400M.
    """
    m_clean = str(meaning or "").strip()
    s_clean = str(scene or "").strip()
    ocr_clean = str(ocr or "").strip()

    # Chuẩn bị cụm từ vật thể tự nhiên
    vi_obj_text = str(natural_vi_objects or objects or "").strip()
    if not vi_obj_text or "Không bắt được" in vi_obj_text or "Khong phat hien" in vi_obj_text or "Không phát hiện" in vi_obj_text:
        vi_obj_text = "Không ghi nhận thực thể nổi bật"

    en_obj_text = str(natural_en_objects or "").strip()
    if not en_obj_text or "No distinct" in en_obj_text or "Không bắt được" in en_obj_text:
        en_obj_text = "No prominent entities"

    # =========================================================================
    # 1. KÊNH TIẾNG VIỆT TỰ THÂN ĐỘC LẬP + PHỤ LỤC THỰC THỂ
    # =========================================================================
    core_vi_parts = []
    
    if m_clean and m_clean not in ["Khung hình chuẩn BTC", "Cảnh Quay Thị Giác", "Chưa xác định"]:
        core_vi_parts.append(m_clean)
    elif s_clean and s_clean not in ["Chưa xác định", "Bối cảnh"]:
        core_vi_parts.append(f"Khung cảnh ghi nhận tại không gian {s_clean}")
    else:
        core_vi_parts.append("Khung cảnh thị giác ghi nhận sự kiện thực tế trong video")

    # Bổ sung thông tin OCR nếu có
    if ocr_clean:
        core_vi_parts.append(f'Bảng đồ họa hiển thị nội dung: "{ocr_clean}"')

    # Bổ sung thông tin Frame Cắt Nghĩa nếu là frame ảo
    if is_virtual and delta_tag:
        core_vi_parts.append(f"(Mốc xuất hiện thông tin mới {delta_tag})")

    core_vi_str = ". ".join(core_vi_parts).strip()
    caption_vi = f"{core_vi_str}. [Thực thể nhận diện: {vi_obj_text}]"

    # =========================================================================
    # 2. KÊNH TIẾNG ANH 100% PURE VISUAL PROMPT + PHỤ LỤC THỰC THỂ (SIGLIP SO400M)
    # =========================================================================
    core_en_parts = []
    
    if "buồng lái" in m_clean.lower() or "xe ô tô" in m_clean.lower():
        core_en_parts.append("Interior perspective inside vehicle cabin")
    elif "dẫn bản tin" in m_clean.lower() or "thời sự" in m_clean.lower() or "studio" in s_clean.lower() or "trường quay" in s_clean.lower():
        core_en_parts.append("News broadcast studio set with presenter")
    elif "thi đấu" in m_clean.lower() or "thể thao" in m_clean.lower() or "sân cỏ" in m_clean.lower():
        core_en_parts.append("Competitive sports tournament match action")
    elif "chuyển cảnh" in m_clean.lower() or "tiêu đề" in m_clean.lower():
        core_en_parts.append("Broadcast title transition graphics banner")
    else:
        core_en_parts.append("Clear visual scene depicting actual recording perspective")

    if ocr_clean:
        core_en_parts.append(f"with on-screen text: '{ocr_clean}'")

    if cultural_concepts:
        anchors = " | ".join([c.get("visual_anchor_en", "") for c in cultural_concepts if c.get("visual_anchor_en")])
        if anchors:
            core_en_parts.append(f"({anchors})")

    core_en_str = ", ".join(core_en_parts).strip()
    caption_en = f"{core_en_str}. [Detected entities: {en_obj_text}]"

    return caption_vi, caption_en
