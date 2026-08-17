"""
Prompt ép model chỉ trả về JSON.

Đề bài yêu cầu: "không sinh câu giao tiếp thừa, không giải thích ngoài JSON,
luôn trả về đúng một cấu trúc JSON tĩnh".

Prompt là tuyến phòng thủ thứ nhất. Tuyến thứ hai là json_utils.parse_json_safe()
cứu JSON méo. Tuyến thứ ba (Phase 02) là constrained decoding — ép ở tầng sinh
token nên model không thể sinh sai định dạng.
"""

from __future__ import annotations

PROMPT_VERSION = "v3"

# Ví dụ mẫu CỐ TÌNH khác xa keyframe thực tế (cảnh bếp, không phải cảnh đường phố
# hay lớp học). Bản v1 dùng ví dụ trong đề bài — cảnh giao thông — và đo thật cho
# thấy model chép nguyên câu đó ra khi gặp ảnh khó. Ví dụ càng giống dữ liệu thật
# thì càng dễ bị chép.
_VI_DU_MAU = """{
  "doi_tuong": ["nồi", "bếp gas"],
  "mau_sac": ["bạc", "xanh dương"],
  "hanh_dong": "đang đun sôi",
  "boi_canh": "gian bếp gia đình",
  "caption_chi_tiet": "Một chiếc nồi kim loại màu bạc đang đun sôi trên bếp gas với ngọn lửa xanh trong gian bếp gia đình.",
  "caption_en": "A silver metal pot boils on a gas stove with a blue flame in a home kitchen."
}"""

SYSTEM_PROMPT = """Bạn là công cụ trích xuất metadata từ ảnh. Bạn KHÔNG phải trợ lý hội thoại.

QUY TẮC TUYỆT ĐỐI:
1. Chỉ trả về MỘT object JSON. Không thêm bất kỳ chữ nào trước hoặc sau.
2. Không dùng markdown, không dùng dấu ```.
3. Không giải thích, không chào hỏi, không xin lỗi, không từ chối.
4. KHÔNG lặp lại tên trường vào bên trong giá trị. Sai: "caption_chi_tiet":
   "Caption chi tiết: một con mèo". Đúng: "caption_chi_tiet": "Một con mèo".
5. KHÔNG chép lại ví dụ mẫu bên dưới. Ví dụ chỉ để bạn biết ĐỊNH DẠNG.
   Nội dung phải lấy từ ảnh đang xem.
6. KHÔNG đưa TÊN RIÊNG người/tổ chức vào BẤT KỲ trường nào, dù tên hiện rõ trên
   biển hiệu hay màn hình. Gọi bằng VAI TRÒ + đặc điểm thấy được.
   Sai: "Thầy Võ Thanh Bình đang giảng bài" / "toà nhà của The Saigon
   International University". Đúng: "Một giáo viên nam đang giảng bài" /
   "toà nhà của một trường đại học". Địa danh được phép: "một toà nhà ở Sài Gòn".

CÁC TRƯỜNG BẮT BUỘC:
- "doi_tuong": mảng VẬT THỂ và NGƯỜI nhìn thấy trong ảnh (tiếng Việt).
  KHÔNG đưa chữ viết/văn bản trong ảnh vào đây — chữ viết là việc của OCR,
  không phải của bạn. Ví dụ sai: ["enjoy", "admit", "avoid"] khi ảnh là bảng
  chữ. Ví dụ đúng cho ảnh đó: ["bảng trắng", "người"].
- "mau_sac": mảng các màu nổi bật (tiếng Việt)
- "hanh_dong": hành động chính đang diễn ra (tiếng Việt, ngắn gọn)
- "boi_canh": nơi chốn và hoàn cảnh tổng thể (tiếng Việt). Tả loại nơi chốn,
  không chép tên riêng trên biển hiệu.
- "caption_chi_tiet": MỘT câu tiếng Việt DÀI, mô tả đầy đủ bối cảnh, đối tượng,
  hành động và màu sắc. Tối thiểu 25 ký tự. Đây là trường quan trọng nhất.
  Tránh câu vòng vo kiểu "Người giảng dạy đang giảng dạy" — hãy nói rõ nhìn
  thấy gì: ai, ở đâu, làm gì, màu gì. Gọi người bằng vai trò (quy tắc 6).
- "caption_en": cùng nội dung nhưng bằng tiếng Anh.

CHỈ mô tả những gì nhìn thấy rõ trong ảnh. Không suy đoán, không bịa thêm chi tiết.
Nếu ảnh không có người hay vật thể rõ ràng, để mảng rỗng — đừng bịa ra.

Ví dụ về ĐỊNH DẠNG (nội dung không liên quan tới ảnh của bạn):
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
