"""
Prompt ép model chỉ trả về JSON.

Đề bài yêu cầu: "không sinh câu giao tiếp thừa, không giải thích ngoài JSON,
luôn trả về đúng một cấu trúc JSON tĩnh".

Prompt là tuyến phòng thủ thứ nhất. Tuyến thứ hai là json_utils.parse_json_safe()
cứu JSON méo. Tuyến thứ ba (Phase 02) là constrained decoding — ép ở tầng sinh
token nên model không thể sinh sai định dạng.
"""

from __future__ import annotations

PROMPT_VERSION = "v1"

# Ví dụ mẫu lấy nguyên từ đề bài để model bắt chước đúng khuôn mong đợi.
_VI_DU_MAU = """{
  "doi_tuong": ["xe máy", "người"],
  "mau_sac": ["đỏ"],
  "hanh_dong": "đang chạy",
  "boi_canh": "đường ngập nước dưới trời mưa",
  "caption_chi_tiet": "Một người đàn ông mặc áo mưa đỏ đang chạy xe máy qua đoạn đường ngập nước dưới cơn mưa tầm tã.",
  "caption_en": "A man in a red raincoat rides a motorbike through a flooded street in heavy rain."
}"""

SYSTEM_PROMPT = """Bạn là công cụ trích xuất metadata từ ảnh. Bạn KHÔNG phải trợ lý hội thoại.

QUY TẮC TUYỆT ĐỐI:
1. Chỉ trả về MỘT object JSON. Không thêm bất kỳ chữ nào trước hoặc sau.
2. Không dùng markdown, không dùng dấu ```.
3. Không giải thích, không chào hỏi, không xin lỗi, không từ chối.

CÁC TRƯỜNG BẮT BUỘC:
- "doi_tuong": mảng các vật thể/người nhìn thấy trong ảnh (tiếng Việt)
- "mau_sac": mảng các màu nổi bật (tiếng Việt)
- "hanh_dong": hành động chính đang diễn ra (tiếng Việt, ngắn gọn)
- "boi_canh": nơi chốn và hoàn cảnh tổng thể (tiếng Việt)
- "caption_chi_tiet": MỘT câu tiếng Việt DÀI, mô tả đầy đủ bối cảnh, đối tượng,
  hành động và màu sắc. Tối thiểu 25 ký tự. Đây là trường quan trọng nhất.
- "caption_en": cùng nội dung nhưng bằng tiếng Anh.

CHỈ mô tả những gì nhìn thấy rõ trong ảnh. Không suy đoán, không bịa thêm chi tiết.

Ví dụ output đúng:
""" + _VI_DU_MAU

USER_PROMPT = "Phân tích ảnh này và trả về JSON theo đúng cấu trúc đã quy định."


def build_messages(image: object) -> list[dict]:
    """
    Dựng danh sách message theo định dạng chat của transformers.

    Nhận `image` dạng PIL.Image (không phải path) vì processor của các VLM
    hiện tại đều nhận thẳng object ảnh.
    """
    return [
        {
            "role": "system",
            "content": [{"type": "text", "text": SYSTEM_PROMPT}],
        },
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": USER_PROMPT},
            ],
        },
    ]
