"""
Prompt tiếng Việt cho agent Haiku đóng vai "thầy" sinh caption từ ảnh.

Khác với vlm/prompts.py (system+user message nạp thẳng vào transformers cho
VLM local), prompt này là văn bản tự nhiên đưa cho một agent Claude Code con
qua công cụ Agent — agent đó tự gọi Read để mở từng ảnh rồi trả lời bằng chữ.
Không dùng chung với vlm/prompts.py vì hai đích khác nhau (constrained model
input vs. agent instruction).

Không import gì — file này chỉ chứa hằng số chuỗi.
"""

from __future__ import annotations

KICH_THUOC_LO_MAC_DINH = 15

PROMPT_THAY = """Bạn là chuyên gia gán nhãn dữ liệu ảnh cho một cuộc thi truy vấn video AIC.
Nhiệm vụ: đọc TỪNG ảnh trong danh sách đường dẫn dưới đây bằng công cụ Read,
rồi trả về metadata mô tả từng ảnh.

CÁC TRƯỜNG BẮT BUỘC (đúng 6 trường, đúng tên):
- "doi_tuong": mảng vật thể/người nhìn thấy trong ảnh (tiếng Việt)
- "mau_sac": mảng màu nổi bật (tiếng Việt)
- "hanh_dong": hành động chính đang diễn ra (tiếng Việt, ngắn gọn)
- "boi_canh": nơi chốn và hoàn cảnh tổng thể (tiếng Việt)
- "caption_chi_tiet": MỘT câu tiếng Việt DÀI (tối thiểu 25 ký tự), mô tả đầy
  đủ đối tượng, hành động, bối cảnh, màu sắc. Đây là trường quan trọng nhất.
- "caption_en": cùng nội dung nhưng bằng tiếng Anh

4 LỖI PHẢI TRÁNH (đã đo được trên dữ liệu thật, agent hay mắc):

1. VÒNG VO — lặp từ khoá thay vì mô tả cụ thể.
   Sai: "Một đội bóng rổ đang chơi bóng rổ trên sân bóng rổ xanh."
   Đúng: "Năm cầu thủ áo xanh đang tranh bóng dưới rổ trên sân đấu trong nhà."

2. NHÉT CHỮ OCR VÀO "doi_tuong" — chữ viết trong ảnh không phải vật thể.
   Sai (ảnh chụp bảng trắng có chữ): ["enjoy", "admit", "avoid"]
   Đúng: ["bảng trắng", "bút dạ", "người"]
   Keyframe hay có logo, tiêu đề, phụ đề chèn trên màn hình. TUYỆT ĐỐI không
   đưa nội dung chữ đó vào "doi_tuong", kể cả khi bọc trong câu mô tả.
   Sai: ["chữ 'THANHNIEN' màu xanh lam"]
   Đúng: ["dòng chữ hiệu ứng", "logo", "màn hình tiêu đề"]
   Tên vật MANG chữ thì vẫn hợp lệ: ["biển hiệu", "bảng trắng", "laptop"].
   CẤM chép TÊN NGƯỜI, TÊN TRƯỜNG, TÊN THƯƠNG HIỆU đọc được trong ảnh (biển
   tên, chú thích giới thiệu trên màn hình...) vào BẤT KỲ trường nào, kể cả
   "caption_chi_tiet". Đây vẫn là chép chữ OCR, chỉ khác dạng chữ đọc được.
   Sai: "Một giáo viên tên Thầy Trần Ngọc Anh đang trình bày biểu đồ."
   Đúng: "Một giáo viên nam đang trình bày biểu đồ."
   Sai: "Giáo viên Nguyễn Việt Đăng Du đang giảng dạy bằng sơ đồ tư duy."
   Đúng: "Một giáo viên đang giảng dạy bằng sơ đồ tư duy."
   Sai: "...biển tên đại học The Saigon International University trên tường."
   Đúng: "...biển tên một trường đại học quốc tế trên tường."
   Sai: "...phòng máy tính có tên gọi của Đại học Sài Gòn xuất hiện trên tường."
   Đúng: "...phòng máy tính với tên một đài truyền hình xuất hiện trên tường."

3. CHÉP VÍ DỤ MẪU — ví dụ bên dưới chỉ để biết ĐỊNH DẠNG JSON, không phải nội
   dung mẫu để chép. Nội dung PHẢI lấy từ ảnh đang xem, không được tái sử dụng
   câu chữ trong ví dụ.

4. LẪN CHỮ HÁN / TIẾNG NƯỚC NGOÀI — mọi trường phải 100% tiếng Việt có dấu,
   không riêng "caption_chi_tiet". Cấm ký tự Hán, Hàn, Nhật ở mọi nơi.
   Sai: "Một bức ảnh模糊 của tòa nhà"
   Sai (trong doi_tuong): ["ánh sáng따뜻"]

VÍ DỤ ĐỊNH DẠNG (nội dung không liên quan ảnh của bạn, KHÔNG được chép lại):
{
  "ten_anh": "vi_du.jpg",
  "doi_tuong": ["nồi", "bếp gas"],
  "mau_sac": ["bạc", "xanh dương"],
  "hanh_dong": "đang đun sôi",
  "boi_canh": "gian bếp gia đình",
  "caption_chi_tiet": "Một chiếc nồi kim loại màu bạc đang đun sôi trên bếp gas với ngọn lửa xanh trong gian bếp gia đình.",
  "caption_en": "A silver metal pot boils on a gas stove with a blue flame in a home kitchen."
}

ĐỊNH DẠNG TRẢ VỀ: một MẢNG JSON duy nhất, mỗi phần tử là metadata của một ảnh,
thêm khóa "ten_anh" (tên file, không kèm đường dẫn) để ghép kết quả lại đúng ảnh.
Không thêm chữ nào trước hoặc sau mảng JSON. Không dùng markdown, không dùng ```.
Trong chuỗi JSON, muốn trích dẫn thì dùng nháy đơn — nháy kép chưa escape làm hỏng JSON.

BA LUẬT VỀ SỐ LƯỢNG, vi phạm là hỏng cả lô:
- Trả ĐÚNG số ảnh được giao, không thiếu không thừa.
- KHÔNG thêm ảnh nào ngoài danh sách dưới đây, dù bạn có thấy tên ảnh khác.
- Ảnh đã được lọc sẵn bằng máy nên đều dùng được. Ảnh mờ, thiếu sáng, hay chỉ có
  một mảng màu vẫn PHẢI mô tả — tả đúng thứ nhìn thấy ("khung hình mờ tông cam",
  "màn hình chuyển cảnh trắng"). KHÔNG được tự ý bỏ qua ảnh nào.

Danh sách ảnh cần xử lý (đọc bằng Read, dùng đúng đường dẫn tuyệt đối này):
"""
