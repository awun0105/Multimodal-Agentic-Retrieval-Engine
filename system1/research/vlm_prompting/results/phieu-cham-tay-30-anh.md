# Phiếu chấm tay — 30 ảnh × 4 model

Chọn ngẫu nhiên 30 ảnh trong 259 ảnh mà **cả 4 model đều sinh được caption** (seed cố định, tái lập được).

**Tên model được giấu, và thứ tự A/B/C/D xáo lại ở mỗi ảnh** — nhãn A ở ảnh 1 không phải model của nhãn A ở ảnh 2.

## Cách chấm

Mỗi caption cho điểm 0-2 ở ba tiêu chí, điền vào cột `Điểm`:

| Tiêu chí | 0 | 1 | 2 |
|---|---|---|---|
| **Đúng** — khớp nội dung ảnh | sai/bịa | đúng phần chính, sai chi tiết | đúng hết |
| **Tiếng Việt** — tự nhiên | lủng củng, sai ngữ pháp | đọc được nhưng gượng | trôi chảy |
| **Đủ** — đủ chi tiết để tìm lại cảnh | chung chung | thiếu một vài chi tiết | đủ dùng |

Ghi theo dạng `2/1/2` (Đúng/Tiếng Việt/Đủ). Tối đa 6 điểm mỗi caption.

Mở ảnh tại `data/keyframes_aic/<tên ảnh>`.

---

## 1. `012.jpg`

**A.** Một giáo viên nữ đang giảng bài trước bảng đen với nội dung về First Conditional trong một phòng học.

> đối tượng: `['giáo viên', 'bảng đen']` · bối cảnh: *phòng học*

> Điểm A: `___/___/___`

**B.** Giáo viên HỒNG NHUNG đang giảng dạy về First Conditional trong lớp học với bảng màu xanh lá cây và bàn học màu hồng.

> đối tượng: `['Giáo viên HỒNG NHUNG', 'bàn học']` · bối cảnh: *gian hàng học*

> Điểm B: `___/___/___`

**C.** Một giáo viên nữ đang giảng bài trên một bảng đen với chữ cái viết trên bảng là 'First Conditional' và 'If I see you tomorrow, I will tell you the story'.

> đối tượng: `['một giáo viên nữ đang giảng bài', 'một bảng đen']` · bối cảnh: *một giáo viên*

> Điểm C: `___/___/___`

**D.** Một giáo viên nữ mặc áo hồng đang giảng bài về cấu trúc câu điều kiện thứ nhất. Cô ấy đứng trước một bảng đen màu xanh lá cây, trên đó có ghi dòng chữ 'If I see you tomorrow, I will tell the story.' Bên cạnh bảng là một bàn học với sách vở và đồ dùng học tập.

> đối tượng: `['bảng đen', 'giáo viên Hồng Nhung']` · bối cảnh: *Bên trong lớp học, giáo viên đang đứng trước bảng đen*

> Điểm D: `___/___/___`

---

## 2. `013.jpg`

**A.** Một chứng chỉ của IACBE được trao cho chương trình quản lý kinh doanh của Đại học Quốc tế Sài Gòn.

> đối tượng: `[]` · bối cảnh: *trang giấy màu xanh dương với logo IACBE và văn bản về chứng chỉ*

> Điểm A: `___/___/___`

**B.** Một tấm bằng khen của The Saigon International University được trao cho chương trình đào tạo kinh doanh. Bằng khen có logo IACBE và chữ ký của hai người đại diện, một người là chủ tịch hội đồng và người còn lại là chủ tịch hội đồng. Bằng khen ghi rõ ngày cấp bằng là 23 tháng 12 năm 2023.

> đối tượng: `['một tấm bằng khen', 'người ký tên']` · bối cảnh: *một buổi lễ trao bằng khen*

> Điểm B: `___/___/___`

**C.** A certificate of accreditation awarded by the International Accreditation Council for Business Education

> đối tượng: `['Certificate of Accreditation', 'International Accreditation Council for Business Education']` · bối cảnh: *Bằng chứng chứng nhận*

> Điểm C: `___/___/___`

**D.** Một chứng nhận của IACBE (International Accreditation Council for Business Education) được trao cho chương trình kinh doanh của Đại học Quốc tế Sài Gòn.

> đối tượng: `[]` · bối cảnh: *một văn bản*

> Điểm D: `___/___/___`

---

## 3. `015.jpg`

**A.** Một người đàn ông đang đi bộ giữa hàng rào sách với một cuốn sách trong tay.

> đối tượng: `['người đi bộ', 'kho sách']` · bối cảnh: *kho sách*

> Điểm A: `___/___/___`

**B.** Một người đàn ông mặc áo sơ mi trắng và quần jeans đang đi giữa hai hàng kệ sách đầy sách trong một thư viện.

> đối tượng: `['người']` · bối cảnh: *sàn thư viện*

> Điểm B: `___/___/___`

**C.** Một người đàn ông đang đi bộ giữa một thư mục rộng lớn, đầy ắp sách vở. Anh ta cầm một cuốn sách mở ra, dường như đang tìm kiếm hoặc đọc sách. Ánh sáng dịu nhẹ chiếu vào từ trên cao, tạo nên không gian tĩnh lặng và trầm tư.

> đối tượng: `['người đàn ông', 'bút', 'thư mục']` · bối cảnh: *thư mục*

> Điểm C: `___/___/___`

**D.** Một người đàn ông mặc áo sơ mi trắng và quần jeans đang đi dạo trong một hành lang đầy sách màu sắc rực rỡ trong một thư viện.

> đối tượng: `['người']` · bối cảnh: *dòng sách màu sắc rực rỡ trong một thư viện*

> Điểm D: `___/___/___`

---

## 4. `021.jpg`

**A.** Một người đàn ông mặc áo sơ mi trắng và quần đen đang đi bộ trong một sảnh trong một tòa nhà.

> đối tượng: `['người']` · bối cảnh: *sảnh trong một tòa nhà*

> Điểm A: `___/___/___`

**B.** Một người đàn ông mặc áo sơ mi trắng đang đi giữa hai hàng kệ sách cao tầng trong sảnh thư viện.

> đối tượng: `['người']` · bối cảnh: *sảnh thư viện*

> Điểm B: `___/___/___`

**C.** Một người đi qua một cánh hàng sách trong một thư viện.

> đối tượng: `['bìa', 'bìa ảnh']` · bối cảnh: *bìa ảnh*

> Điểm C: `___/___/___`

**D.** Một người đàn ông đang đi bộ giữa lối đi hẹp giữa hai hàng kệ sách chứa đầy sách, tạo cảm giác như đang trong một thư viện hoặc cửa hàng sách lớn.

> đối tượng: `['người đàn ông', 'kệ sách']` · bối cảnh: *lối đi giữa các kệ sách*

> Điểm D: `___/___/___`

---

## 5. `040.jpg`

**A.** Một bức tranh nghệ thuật với màu sắc chủ đạo là màu be và trắng, không có đối tượng cụ thể nào.

> đối tượng: `[]` · bối cảnh: *một bức tranh nghệ thuật*

> Điểm A: `___/___/___`

**B.** Một chiếc nồi kim loại màu xanh dương đang đun sôi trên bếp gas với ngọn lửa xanh trong gian bếp gia đình.

> đối tượng: `['bếp gas']` · bối cảnh: *gian bếp gia đình*

> Điểm B: `___/___/___`

**C.** Một bức ảnh đen trắng chụp một người và một con mèo, không rõ chi tiết khuôn mặt. Bối cảnh không rõ ràng.

> đối tượng: `['một người', 'một con mèo']` · bối cảnh: *một bức ảnh đen trắng*

> Điểm C: `___/___/___`

**D.** Một bức tranh với nhiều hình dạng và màu sắc khác nhau, chủ yếu là màu trắng.

> đối tượng: `[]` · bối cảnh: *một bức tranh*

> Điểm D: `___/___/___`

---

## 6. `042.jpg`

**A.** Một người mặc vest đang trao một giấy chứng nhận cho một người mặc áo sơ mi trong một phòng họp.

> đối tượng: `['một người mặc vest', 'một người mặc áo sơ mi']` · bối cảnh: *một phòng họp*

> Điểm A: `___/___/___`

**B.** 2 người đang nhận bằng tốt nghiệp của Đại học Quốc tế Singapore (SIU).

> đối tượng: `['2 người đang nhận bằng tốt nghiệp']` · bối cảnh: *giường học tập*

> Điểm B: `___/___/___`

**C.** Hai người đang đứng trước một màn hình trắng, một người cầm một tấm bằng có logo của trường Đại học Sư phạm Quốc gia Thành phố Hồ Chí Minh (SIU), và người kia đang cầm một tấm bảng màu tím ghi rõ logo SIU. Bối cảnh là một không gian trong nhà, có vẻ như là một buổi lễ tốt nghiệp hoặc chứng nhận.

> đối tượng: `['hai nguoi', 'mang bo', 'boi canh']` · bối cảnh: *một toà nhà*

> Điểm C: `___/___/___`

**D.** Người đàn ông mặc áo khoác đỏ đang trao đổi với người phụ nữ mặc váy trắng trong một sàn hội trường.

> đối tượng: `['người đàn ông', 'người phụ nữ']` · bối cảnh: *sàn hội trường*

> Điểm D: `___/___/___`

---

## 7. `045.jpg`

**A.** Trợ lý viên nhạc đang chơi guitar trong một phòng âm thanh. Họ đang chơi một bản nhạc nhẹ nhàng và hòa hợp với nhau.

> đối tượng: `['trợ lý', 'viên nhạc', 'guitar']` · bối cảnh: *viên nhạc đang chơi guitar trong một phòng âm thanh*

> Điểm A: `___/___/___`

**B.** Bốn người đàn ông trẻ tuổi, mặc áo sơ mi trắng và quần dài, đang ngồi chơi guitar acoustic trong một căn phòng sáng màu vàng nhạt. Ánh sáng dịu nhẹ tạo ra hiệu ứng mờ ảo trên họa tiết rèn phía sau.

> đối tượng: `['bốn người đàn ông đang chơi guitar']` · bối cảnh: *một căn phòng*

> Điểm B: `___/___/___`

**C.** Ba người đàn ông đang chơi đàn guitar trong một nhà hát với ánh sáng màu trắng và đỏ.

> đối tượng: `['người']` · bối cảnh: *nhà hát*

> Điểm C: `___/___/___`

**D.** Hai nam thanh niên đang chơi guitar trong một phòng học với ánh sáng trắng và đen.

> đối tượng: `['hai nam thanh niên']` · bối cảnh: *một phòng học*

> Điểm D: `___/___/___`

---

## 8. `061.jpg`

**A.** Một nhóm sinh viên mặc đồng phục xanh đứng trên sân khấu trong phòng hòa nhạc, nghe một người đàn ông mặc vest đen đứng giữa họ, với màn hình lớn phía sau hiển thị thông tin về lễ công bố học bổng tại Đại học Sài Gòn Quốc tế.

> đối tượng: `['người', 'các sinh viên']` · bối cảnh: *sàn diễn trong phòng hòa nhạc*

> Điểm A: `___/___/___`

**B.** Trong một buổi lễ, một đội học sinh mặc áo màu xanh dương đứng trước sân khấu, một người đàn ông trong bộ đồ đen cầm cờ đỏ lên sân khấu và đưa lên phía trước.

> đối tượng: `['câu chuyện', 'vòng đời']` · bối cảnh: *trung tâm sự kiện*

> Điểm B: `___/___/___`

**C.** Một nhóm sinh viên mặc đồng phục xanh dương và đen đang đứng trên sân khấu, cùng một giáo viên nam mặc áo sơ mi trắng đứng giữa họ. Phông nền là màn hình lớn hiển thị logo trường Đại học Saigon International University và dòng chữ 'Lễ Công Bố Journey Scholarship'.  Hành động chính là sự kiện lễ công bố, với các sinh viên và giáo viên tham gia.  Màu sắc chủ đạo là xanh dương của đồng phục sinh viên và màu trắng của giáo viên.

> đối tượng: `['một nhóm sinh viên', 'một giáo viên', 'một người đàn ông']` · bối cảnh: *một hội trường lớn*

> Điểm C: `___/___/___`

**D.** Một nhóm sinh viên mặc đồng phục xanh dương và đen đang đứng trên sân khấu, trong khi một giáo viên nam mặc西装正在升旗。

> đối tượng: `['nhóm sinh viên', 'giáo viên']` · bối cảnh: *phòng họp lớn*

> Điểm D: `___/___/___`

---

## 9. `082.jpg`

**A.** Những người học bơi đang tập luyện dưới sự hướng dẫn của giáo viên trong bể bơi.

> đối tượng: `['những người học bơi', 'giáo viên']` · bối cảnh: *bể bơi*

> Điểm A: `___/___/___`

**B.** Một nhóm người đang bơi lội trong một bể bơi, họ mặc áo phao và đội mũ bảo hộ. Bể bơi có màu xanh dương sáng, và ánh sáng phản chiếu trên mặt nước tạo ra hiệu ứng lung linh.

> đối tượng: `['người', 'bơi lội']` · bối cảnh: *một bể bơi*

> Điểm B: `___/___/___`

**C.** Một nhóm người đang tập bơi tại hồ bơi. Họ đang sử dụng các côn tay bơi lội để tập luyện.

> đối tượng: `['bơi lội', 'các người đang tập bơi', 'bơi lội tại một hồ bơi']` · bối cảnh: *bơi lội*

> Điểm C: `___/___/___`

**D.** Một nhóm người đang tập luyện bơi lội trong bể bơi với các dụng cụ bơi như bọt biển và bơi lợn.

> đối tượng: `['người', 'bể bơi']` · bối cảnh: *bể bơi trong nhà*

> Điểm D: `___/___/___`

---

## 10. `089.jpg`

**A.** Một giáo viên nam đang giảng bài trên một màn hình trắng, với biểu đồ phân tích về các chủ đề chính trong chương trình trực tuyến thông tin học tập năm 2024: môn lịch sử - CD7: Trả tất cả các giải quyết từ sự kiện sau chiến tranh II - đến năm 2000.

> đối tượng: `['Thầy Nguyễn Việt Đăng Du', 'Chương trình trực tuyến thông tin học tập năm 2024: môn lịch sử - CD7: Trả tất cả các giải quyết từ sự kiện sau chiến tranh II - đến năm 2000']` · bối cảnh: *Bếp gas, Gian bếp gia đình*

> Điểm A: `___/___/___`

**B.** Một giáo viên nam đang giảng bài về Hội nghị Yalta trong chương trình ôn thi THPT 2024 môn Lịch sử.

> đối tượng: `['giáo viên nam', 'màn hình']` · bối cảnh: *một lớp học trực tuyến*

> Điểm B: `___/___/___`

**C.** Thầy NGUYỄN VIẾT ĐĂNG DU đang giảng dạy về chương trình ôn thi THPT 2024: Môn Lịch Sử - CD7: Trật tự thế giới từ sau Thế Chiến II đến năm 2000.

> đối tượng: `['Thầy NGUYỄN VIẾT ĐĂNG DU', 'người']` · bối cảnh: *gian hàng giảng dạy với màn hình hiển thị thông tin về chương trình ôn thi THPT 2024*

> Điểm C: `___/___/___`

**D.** Một người đàn ông mặc áo sơ mi trắng, đeo kính, đang ngồi trước máy tính xách tay màu đen, trên màn hình là sơ đồ tư duy với các vòng tròn chứa văn bản tiếng Việt. Phía dưới cùng bên trái có dòng chữ 'Thầy Nguyễn Viết Đăng Du' và 'Tổ trưởng sở lịch sử - Tháp Đồi, Thanh Hóa, 1957'. Phía dưới cùng bên phải có dòng chữ 'CHƯƠNG TRÌNH ÔN THI THPT 2024: MÔN LỊCH SỬ - CĐT: TRẬT TỰ THẾ GIỚI TỪ SAU THẾ CHIẾN I ĐẾN NĂM 2000'.

> đối tượng: `['thầy Nguyễn Viết Đăng Du', 'laptop']` · bối cảnh: *một người đàn ông đang ngồi trước máy tính xách tay*

> Điểm D: `___/___/___`

---

## 11. `096.jpg`

**A.** Một người đàn ông đang ngồi trước máy tính bảng, có vẻ như đang giảng bài. Bối cảnh là bên ngoài một tòa nhà, có thể là trường học. Hình ảnh tập trung vào người đàn ông và máy tính bảng.

> đối tượng: `['người đàn ông', 'máy tính bảng']` · bối cảnh: *bên ngoài trường học*

> Điểm A: `___/___/___`

**B.** Trợ lý đang giảng dạy về Luyện tập thực hành trong lĩnh vực quản lý nhân sự.

> đối tượng: `['Trợ lý', 'Học viên']` · bối cảnh: *Bảng trắng, Bảng đen*

> Điểm B: `___/___/___`

**C.** Thầy Đỗ Đức Anh đang giảng dạy về một bài giảng về việc thay đổi của người trẻ Việt Nam để trở thành công dân toàn cầu.

> đối tượng: `['thầy Đỗ Đức Anh', 'người đang giảng dạy']` · bối cảnh: *gian hàng sách với nhiều cuốn sách và một bảng thông tin về chương trình ôn thi THPT 2024*

> Điểm C: `___/___/___`

**D.** Một thầy giáo đang giảng bài về chủ đề 'Luyện viết đoạn văn nghị luận xã hội' cho học sinh lớp 12 tại một lớp học trực tuyến.

> đối tượng: `['Thầy Đỗ Đức Anh']` · bối cảnh: *một lớp học trực tuyến*

> Điểm D: `___/___/___`

---

## 12. `098.jpg`

**A.** Một người đàn ông đang ngồi trước máy tính, mặc áo sơ mi xám, đeo kính, đang viết đoạn văn trên màn hình. Bên cạnh là một bức ảnh của tác giả Nguyễn Tuân và đoạn văn trích dẫn từ tác phẩm "Người lái đò sông Đà".

> đối tượng: `['người đàn ông', 'mô tả', 'đoạn văn']` · bối cảnh: *bài giảng về tác phẩm văn học*

> Điểm A: `___/___/___`

**B.** Một chiếc nồi kim loại màu bạc đang đun sôi trên bếp gas với ngọn lửa xanh trong gian bếp gia đình.

> đối tượng: `['nồi', 'bếp gas']` · bối cảnh: *gian bếp gia đình*

> Điểm B: `___/___/___`

**C.** Một giáo viên nam đang giảng bài về tác phẩm 'Người lái đò sông Đà' với hình ảnh sóng biển và thác nước trong bài văn học.

> đối tượng: `['người', 'biển sóng', 'thác nước']` · bối cảnh: *một lớp học*

> Điểm C: `___/___/___`

**D.** Thầy Đỗ Đức Anh đang giảng dạy về văn học, với bài giảng về tác phẩm Người Lái Đò Sông Đà của Nguyễn Tuân.

> đối tượng: `['thầy Đỗ Đức Anh', 'người giảng dạy']` · bối cảnh: *gian hàng giảng dạy tại lớp học*

> Điểm D: `___/___/___`

---

## 13. `187.jpg`

**A.** Một người phụ nữ đang đứng trước bảng quảng cáo của Trường Đại Học Quốc tế AHS, với hình ảnh học sinh mặc áo đỏ và biểu ngữ GAIE Group of Asian International Education.

> đối tượng: `['banners', 'students', 'buildings', 'signboard', 'student_uniforms', 'AHS', 'GAIE', 'international education']` · bối cảnh: *outside*

> Điểm A: `___/___/___`

**B.** Người phụ nữ mặc áo màu tím đứng nhìn quảng cáo lớn về trường quốc tế ở một tòa nhà cao tầng với cây xanh xung quanh.

> đối tượng: `['bản quảng cáo', 'người phụ nữ']` · bối cảnh: *vườn cây xanh trước một tòa nhà cao tầng*

> Điểm B: `___/___/___`

**C.** Một người phụ nữ đang quay lưng lại với máy ảnh, nhìn vào một tấm biển quảng cáo của trường học. Biển quảng cáo có màu đỏ và trắng, với hình ảnh các em nhỏ mặc trang phục Giáng sinh.  Tấm biển quảng cáo có logo của trường học và tên trường là 'Group of Asian International Education'.  Toà nhà trường học cao tầng với nhiều cửa sổ kính xanh.

> đối tượng: `['người phụ nữ', 'biển quảng cáo trường học']` · bối cảnh: *toà nhà trường học, biển quảng cáo trường học*

> Điểm C: `___/___/___`

**D.** Một nhân viên nữ mặc áo tím đang đứng nhìn biển quảng cáo của GAIE Group of Asian International Education trên một tòa nhà cao tầng.

> đối tượng: `['nhân viên nữ', 'biển quảng cáo']` · bối cảnh: *một tòa nhà cao tầng*

> Điểm D: `___/___/___`

---

## 14. `189.jpg`

**A.** Những ống nghiệm và bình thí nghiệm với các màu sắc khác nhau đang được sử dụng trong một phòng thí nghiệm hóa học.

> đối tượng: `['các loại ống nghiệm', 'các loại bình thí nghiệm']` · bối cảnh: *laboratory*

> Điểm A: `___/___/___`

**B.** Một nhóm người đang thực hiện thí nghiệm hóa học trong phòng thí nghiệm. Họ sử dụng các bình thí nghiệm và ống nghiệm chứa chất lỏng màu sắc khác nhau, bao gồm xanh lá cây, đỏ, tím, hồng và xanh dương. Các dụng cụ được sắp xếp gọn gàng trên bàn làm việc.

> đối tượng: `['người', 'bình thí nghiệm', 'ống nghiệm']` · bối cảnh: *bộ bàn làm việc hóa học*

> Điểm B: `___/___/___`

**C.** Nhóm nghiên cứu đang thực hiện thí nghiệm hóa học với nhiều试管 và cốc chứa溶液 khác nhau trên bàn lab.

> đối tượng: `['người', 'người']` · bối cảnh: *bàn lab*

> Điểm C: `___/___/___`

**D.** Một nhóm nghiên cứu đang làm việc với các dụng cụ hóa học trong phòng thí nghiệm.

> đối tượng: `['lý thuyết hóa học', 'lý thuyết hóa học']` · bối cảnh: *lý thuyết hóa học*

> Điểm D: `___/___/___`

---

## 15. `220.jpg`

**A.** Một thầy giáo đang giảng bài về chủ đề 'Những điều người trẻ Việt cần thay đổi để trở thành công dân toàn cầu?' trong một lớp học.

> đối tượng: `['thầy giáo', 'ảnh']` · bối cảnh: *một lớp học*

> Điểm A: `___/___/___`

**B.** Thầy Đỗ Đức Anh đang giảng dạy về các vấn đề xã hội, bao gồm việc thay đổi của người trẻ Việt Nam để trở thành công dân toàn cầu.

> đối tượng: `['thầy Đỗ Đức Anh', 'người đang giảng dạy']` · bối cảnh: *gian hàng sách với nhiều cuốn sách và một bảng thông tin*

> Điểm B: `___/___/___`

**C.** Trợ lý đang giảng bài về Luyện tập văn nghệ luận xã hội.

> đối tượng: `['Trợ lý', 'Học viên', 'Bài giảng']` · bối cảnh: *Bài giảng*

> Điểm C: `___/___/___`

**D.** Một người đàn ông đang ngồi trước máy tính xách tay, giảng bài cho một lớp học trực tuyến. Bàn giáo có bảng trắng và bảng đen. Người đàn ông mặc áo sơ mi màu xanh dương và đeo kính. Anh ấy đang sử dụng micro để giảng bài. Hình ảnh được chụp từ góc nghiêng, cho thấy phần trên của người đàn ông và bàn giáo.

> đối tượng: `['người đàn ông', 'bàn giảng dạy', 'máy tính xách tay']` · bối cảnh: *một buổi học trực tuyến*

> Điểm D: `___/___/___`

---

## 16. `228.jpg`

**A.** Một người nam và một người nữ đang trò chuyện trong một phòng học với tông màu trang, đỏ và tím.

> đối tượng: `['nam', 'nu']` · bối cảnh: *một phòng học*

> Điểm A: `___/___/___`

**B.** Một người đàn ông đang làm việc trong một phòng bếp, một người phụ nữ đang giúp đỡ

> đối tượng: `['Một người đàn ông đang làm việc trong một phòng bếp', 'Một người phụ nữ đang giúp đỡ']` · bối cảnh: *Bếp gas*

> Điểm B: `___/___/___`

**C.** Một người đàn ông và một người phụ nữ đang nói chuyện trong một phòng học với hai người mặc đồng phục trắng và đỏ.

> đối tượng: `['người', 'người']` · bối cảnh: *gian phòng học*

> Điểm C: `___/___/___`

**D.** Một người đàn ông trẻ tuổi đeo kính và mặc áo sơ mi trắng, cà vạt đỏ đang ngồi lắng nghe một người phụ nữ trẻ mặc đồng phục học sinh màu trắng với viền xanh dương. Họ đang trò chuyện trong một không gian nội thất có vẻ như là phòng họp hoặc phòng làm việc của trường học, với các chi tiết trang trí đơn giản và màu sắc chủ đạo là màu trắng và xanh dương.

> đối tượng: `['một người đàn ông trẻ tuổi đang ngồi', 'một người phụ nữ trẻ đang đứng']` · bối cảnh: *một không gian nội thất có vẻ như là phòng họp hoặc phòng làm việc của trường học*

> Điểm D: `___/___/___`

---

## 17. `252.jpg`

**A.** Một nhóm học sinh nữ đang làm bài kiểm tra trên máy tính xách tay. Các em đều đeo tai nghe và mặc đồng phục màu đỏ, tập trung vào màn hình máy tính. Bàn làm việc có nhiều máy tính xách tay xếp hàng, tạo thành một khu vực làm bài kiểm tra nghiêm túc.

> đối tượng: `['bàn máy tính', 'máy tính xách tay', 'người', 'giấy']` · bối cảnh: *nhà máy tính*

> Điểm A: `___/___/___`

**B.** Một nhóm học sinh đang làm việc trên máy tính trong lớp học.

> đối tượng: `['làm việc', 'tham gia', 'sự kiện']` · bối cảnh: *lớp học*

> Điểm B: `___/___/___`

**C.** Một nhóm học sinh đang tập trung vào việc sử dụng máy tính trong lớp học, họ đều mặc đồng phục đỏ và có tai nghe.

> đối tượng: `['người', 'trẻ em']` · bối cảnh: *sàn gỗ, bàn học, máy tính*

> Điểm C: `___/___/___`

**D.** Những học sinh đang tập trung học tập trên máy tính trong phòng học máy tính với giáo viên hướng dẫn.

> đối tượng: `['những học sinh', 'giáo viên']` · bối cảnh: *phòng học máy tính*

> Điểm D: `___/___/___`

---

## 18. `253.jpg`

**A.** Trang giấy màu xanh lá cây với văn bản và biểu đồ về bài tập hóa học, bao gồm các lựa chọn đáp án và các ion hóa của các nguyên tố.

> đối tượng: `[]` · bối cảnh: *trang giấy màu xanh lá cây với văn bản và biểu đồ*

> Điểm A: `___/___/___`

**B.** Một bài tập về phản ứng giữa hợp chất Fe và Mg và dung dịch AgNO3.

> đối tượng: `['Fe', 'Mg', 'Ag']` · bối cảnh: *Bài tập áp dụng*

> Điểm B: `___/___/___`

**C.** Bài tập áp dụng về phản ứng hóa học giữa Fe và Mg với AgNO3

> đối tượng: `[]` · bối cảnh: *một bài tập hóa học*

> Điểm C: `___/___/___`

**D.** Bài tập hóa học yêu cầu xác định hai muối trong dung dịch X sau khi phản ứng AgNO3 với hỗn hợp Fe và Mg. Dung dịch X gồm hai muối và hai kim loại rắn Y. Bài tập có bốn đáp án A, B, C, D, mỗi đáp án là một cặp muối. Phân tích phản ứng hóa học để chọn ra đáp án đúng.

> đối tượng: `['một bài tập hóa học', 'người làm bài tập']` · bối cảnh: *một trang web hoặc tài liệu điện tử*

> Điểm D: `___/___/___`

---

## 19. `258.jpg`

**A.** Một cây đàn piano đặt trên sân khấu trong một nhà hát với ánh sáng màu xanh dương và xanh lá cây phát sáng từ đèn chiếu sáng.

> đối tượng: `['sàn', 'nhạc cụ']` · bối cảnh: *sàn nhạc trong một nhà hát*

> Điểm A: `___/___/___`

**B.** Một cây đàn piano đen đặt giữa sân khấu rạp chiếu phim với ánh sáng chiếu rọi từ trên xuống.

> đối tượng: `['đàn piano']` · bối cảnh: *rạp chiếu phim*

> Điểm B: `___/___/___`

**C.** Một người đàn ông đang chơi đàn piano trên sân khấu của một nhà hát, với ánh sáng xanh dương và vàng chiếu sáng. Bàn phím màu đen nổi bật trên nền trắng của sân khấu.

> đối tượng: `['bàn phím', 'người đàn ông']` · bối cảnh: *nhà hát*

> Điểm C: `___/___/___`

**D.** Trung tâm âm nhạc đang diễn với ánh sáng chiếu lên sân khấu và âm nhạc.

> đối tượng: `['trung tâm âm nhạc', 'trung tâm biểu diễn', 'trung tâm biểu diễn âm nhạc']` · bối cảnh: *trung tâm âm nhạc*

> Điểm D: `___/___/___`

---

## 20. `278.jpg`

**A.** Hai canh màu trắng và đỏ đang chua trên một chiếc màng, có vẻ như là một phần của một bức tranh hoặc ảnh chụp cận cảnh.

> đối tượng: `['hai canh', 'mang']` · bối cảnh: *mang*

> Điểm A: `___/___/___`

**B.** Chữ từ số hóa của các chất sau: CH3-CH3-CHO (I) ; CH3-CH2-CH3 (II) ; CH3-CH2-CH2-OH (III) ; CH3-CH2-COOH (IV)

> đối tượng: `[]` · bối cảnh: **

> Điểm B: `___/___/___`

**C.** Bài tập áp dụng về nhiệt độ sôi của các chất hữu cơ

> đối tượng: `[]` · bối cảnh: *một bài tập hóa học*

> Điểm C: `___/___/___`

**D.** Trang trắng với văn bản màu sắc, bao gồm các phân tử hóa học và câu hỏi về thứ tự sắp xếp nhiệt độ sôi.

> đối tượng: `[]` · bối cảnh: *trang trắng với văn bản màu sắc*

> Điểm D: `___/___/___`

---

## 21. `282.jpg`

**A.** Một giáo viên nam đang giảng bài trên bàn học tập với nhiều đồ học và bảng chữ cái.

> đối tượng: `['Trợ lý', 'Bài giảng']` · bối cảnh: *Bàn học tập*

> Điểm A: `___/___/___`

**B.** Thầy Đỗ Đức Anh đang giảng dạy trong một lớp học với màu sắc cam và xanh dương nổi bật.

> đối tượng: `['Thầy Đỗ Đức Anh', 'người']` · bối cảnh: *gian hàng giảng dạy*

> Điểm B: `___/___/___`

**C.** Một người đàn ông, có thể là giáo viên, đang đứng trước máy tính xách tay và giảng bài. Ông mặc áo sơ mi màu đen, quần tây màu xanh dương, đeo kính và tóc ngắn. Bối cảnh là một phòng học với bảng trắng và bảng đen. Bên cạnh ông là một chiếc máy tính xách tay màu vàng. Phía trên đầu ông là dòng chữ 'ĐOÀN HỌC SINH THPT' và 'Trường THPT Bùi Thi Xuân, TPHCM'.

> đối tượng: `['Thầy Đỗ Đức Anh', 'một người đàn ông']` · bối cảnh: *bên phải ảnh*

> Điểm C: `___/___/___`

**D.** Một thầy giáo đang giảng bài trong một lớp học với biển báo chương trình ôn thi THPT 2024 môn Ngữ văn CĐ6.

> đối tượng: `['Thầy ĐỖ ĐỨC ANH', 'biển báo']` · bối cảnh: *một lớp học*

> Điểm D: `___/___/___`

---

## 22. `299.jpg`

**A.** Một người đang bơi trong một hồ bơi xanh, đầu nổi lên khỏi mặt nước, tay giữ chặt vào hai bên. Nước hồ bơi có màu xanh đậm và tạo ra những gợn sóng nhẹ.

> đối tượng: `['người', 'mũi', 'tay']` · bối cảnh: *một hồ bơi*

> Điểm A: `___/___/___`

**B.** Một người đang bơi lội trên mặt nước trong một hồ bơi.

> đối tượng: `['bơi lội']` · bối cảnh: *bơi lội*

> Điểm B: `___/___/___`

**C.** Một người đang bơi trong bể bơi với nước xanh dương.

> đối tượng: `['người']` · bối cảnh: *bể bơi*

> Điểm C: `___/___/___`

**D.** Một người đang bơi trong bể bơi với nước xanh trong và ánh sáng mặt trời chiếu lên水面。

> đối tượng: `['người', 'bể bơi']` · bối cảnh: *bể bơi rộng lớn với nước xanh trong*

> Điểm D: `___/___/___`

---

## 23. `314.jpg`

**A.** Một giáo viên đang giảng dạy tại một lớp học hóa học.

> đối tượng: `['làm việc', 'giáo dục']` · bối cảnh: *làm việc*

> Điểm A: `___/___/___`

**B.** Một người đàn ông đang ngồi trước màn hình máy tính, anh ấy đang làm một bài tập toán học. Bài toán yêu cầu tìm tọa độ tâm của đường thẳng chứa hai điểm và biết tọa độ gốc O(0;0). Các đáp án được đưa ra là A(1;2), B(-1;-1), C(2;1) và D(1;1).

> đối tượng: `['người đàn ông', 'laptop', 'màn hình máy tính']` · bối cảnh: *một người đàn ông đang làm bài tập trên laptop*

> Điểm B: `___/___/___`

**C.** Một giáo viên nam đang giảng bài trong một lớp học với laptop trên bàn.

> đối tượng: `['giáo viên nam']` · bối cảnh: *một lớp học*

> Điểm C: `___/___/___`

**D.** Một người đàn ông mặc áo sơ mi trắng đang ngồi trước máy tính xách tay, giảng dạy trên một bảng đen với các biểu đồ và chữ.

> đối tượng: `['người']` · bối cảnh: *gian hàng học tập*

> Điểm D: `___/___/___`

---

## 24. `322.jpg`

**A.** Một giáo viên nữ đang giảng bài về cấu trúc câu điều kiện với một tấm bảng màu xanh lá cây phía sau.

> đối tượng: `['giáo viên', 'tấm bảng']` · bối cảnh: *phòng học*

> Điểm A: `___/___/___`

**B.** Trong ảnh, giáo viên Hồng Nhung, một người phụ nữ trẻ mặc áo hồng, đang đứng trước bảng đen màu xanh lá cây. Cô ấy đang giảng bài về điều kiện trong tiếng Anh. Bảng đen có dòng chữ 'PRACTICE 2' và câu hỏi 'Rewrite the following sentence using conditionals: Because he didn't prepare for the interview, he didn't get the job.'  Dưới đó là ví dụ minh họa cho câu trả lời: 'If he had prepared for the interview, he would have got the job.'  Phía dưới cùng bên phải của ảnh có ghi tên giáo viên Hồng Nhung và trường học của cô ấy.

> đối tượng: `['bảng đen', 'giáo viên Hồng Nhung', 'một người phụ nữ']` · bối cảnh: *một lớp học*

> Điểm B: `___/___/___`

**C.** Giáo viên Hồng Nhung đang giảng dạy tại một lớp học với bảng màu xanh lá cây và sách giáo trình trên bàn cô.

> đối tượng: `['giáo viên Hồng Nhung']` · bối cảnh: *sàn giáo dục quốc tế Á Châu*

> Điểm C: `___/___/___`

**D.** Một người đang nói chuyện với người khác.

> đối tượng: `['nói chuyện với người khác', 'vai trò của người khác']` · bối cảnh: *nói chuyện với người khác*

> Điểm D: `___/___/___`

---

## 25. `329.jpg`

**A.** Một nhóm sinh viên mặc đồng phục xanh đứng trên sân khấu, nghe giảng viên đọc bài phát biểu tại lễ công bố của Đại học Sài Gòn Quốc tế.

> đối tượng: `['người', 'các sinh viên']` · bối cảnh: *sàn diễn trong phòng hòa nhạc*

> Điểm A: `___/___/___`

**B.** Một nhóm sinh viên mặc đồng phục xanh dương và đen đứng trên sân khấu trong buổi lễ công bố Journey Scholarship tại The Saigon International University.

> đối tượng: `['nhóm sinh viên', 'giáo viên']` · bối cảnh: *phòng họp lớn*

> Điểm B: `___/___/___`

**C.** Trong một buổi lễ, một đội ngũ sinh viên mặc áo màu xanh dương đứng trên sân khấu, trong khi một người đàn ông trong bộ đồ đen đang cầm cờ đỏ lên sân khấu.

> đối tượng: `['câu chuyện', 'vòng đời']` · bối cảnh: *trung tâm sự kiện*

> Điểm C: `___/___/___`

**D.** Một nhóm sinh viên mặc đồng phục xanh dương và đen đang đứng trên sân khấu, hướng về phía một giáo viên nam đang đứng giữa họ. Phông nền là màn hình lớn hiển thị logo của trường Đại học Saigon International University và dòng chữ 'Lễ Công Bố Journey'.  Bầu không khí trang trọng và nghiêm túc.

> đối tượng: `['một nhóm sinh viên', 'một giáo viên nam']` · bối cảnh: *một hội trường lớn*

> Điểm D: `___/___/___`

---

## 26. `338.jpg`

**A.** Một dàn nhạc giao hưởng đang biểu diễn trên sân khấu nhà hát với đàn piano đặt giữa dàn nhạc.

> đối tượng: `['dàn nhạc giao hưởng', 'đàn piano']` · bối cảnh: *sân khấu nhà hát*

> Điểm A: `___/___/___`

**B.** Viola players and a pianist perform together in a grand concert hall.

> đối tượng: `['violinists', 'pianist', 'orchestra', 'concert hall']` · bối cảnh: *a large orchestra performing in a concert hall*

> Điểm B: `___/___/___`

**C.** Nhóm nhạc đang biểu diễn trên sân khấu với nhiều nhạc cụ như đàn violin, đàn cello và đàn piano, ánh sáng vàng và màu sắc của nhạc cụ tạo nên không khí sôi nổi.

> đối tượng: `['violinist', 'cellist', 'pianist']` · bối cảnh: *sàn biểu diễn hòa nhạc*

> Điểm C: `___/___/___`

**D.** Một nhóm nhạc sĩ đang tập trung vào việc chỉ đạo âm thanh của buổi biểu diễn. Nhạc trưởng đứng ở giữa, các nhạc sĩ ngồi xung quanh, tất cả đều mặc đồng phục tối màu và đang tập trung vào một chiếc đàn lớn đặt ở trung tâm sân khấu. Ánh sáng tập trung vào nhóm nhạc sĩ, tạo nên không khí nghiêm túc và chuyên nghiệp.

> đối tượng: `['nhạc trưởng', 'nhạc sĩ', 'viên nhạc']` · bối cảnh: *thời trang*

> Điểm D: `___/___/___`

---

## 27. `339.jpg`

**A.** Logo của Thanh Niên trên nền xám.

> đối tượng: `[]` · bối cảnh: *một logo trên nền xám*

> Điểm A: `___/___/___`

**B.** Logo màu xanh dương của 'THANHNIEN' được đóng dấu trên nền xám.

> đối tượng: `['logo', 'chữ']` · bối cảnh: *một nền xám đơn giản*

> Điểm B: `___/___/___`

**C.** Một logo của tờ báo Thanh Niên được hiển thị trên nền xám.

> đối tượng: `[]` · bối cảnh: *trang bị máy tính*

> Điểm C: `___/___/___`

**D.** Một logo màu xanh đang hiển thị trên nền màu xám.

> đối tượng: `['logo']` · bối cảnh: *no*

> Điểm D: `___/___/___`

---

## 28. `428.jpg`

**A.** Bốn người đàn ông trẻ tuổi, mặc áo sơ mi trắng và quần tây đen, đang ngồi chơi guitar acoustic trong một căn phòng sáng với ánh sáng vàng ấm áp. Họ có vẻ thư giãn và tận hưởng âm nhạc.

> đối tượng: `['bốn người đàn ông đang chơi guitar']` · bối cảnh: *một căn phòng sáng*

> Điểm A: `___/___/___`

**B.** Trong một buổi hòa nhạc, ba thanh niên đang chơi đàn guitar cùng nhau.

> đối tượng: `['trên một bức ảnh', 'trong một buổi hòa nhạc', 'trong một lớp học']` · bối cảnh: *trong một lớp học*

> Điểm B: `___/___/___`

**C.** Ba người đàn ông đang chơi guitar trong phòng tập thể dục với ánh sáng vàng chiếu qua rèm cửa.

> đối tượng: `['ba người chơi guitar']` · bối cảnh: *phòng tập thể dục*

> Điểm C: `___/___/___`

**D.** Ba người đàn ông đang chơi đàn guitar trong một gian hàng nhạc với ánh sáng vàng rực rỡ.

> đối tượng: `['người']` · bối cảnh: *gian hàng nhạc*

> Điểm D: `___/___/___`

---

## 29. `498.jpg`

**A.** Một người đàn ông đang ngồi làm việc trên laptop của mình. Anh ấy có vẻ đang trình bày hoặc ghi chép thông tin. Bối cảnh là một văn phòng với màu xanh dương chủ đạo.

> đối tượng: `['người đàn ông', 'laptop']` · bối cảnh: *một người đàn ông đang làm việc tại văn phòng*

> Điểm A: `___/___/___`

**B.** Một người đàn ông mặc áo sơ mi màu xanh đang giảng dạy trên một màn hình hiển thị thông tin trên mạng.

> đối tượng: `['người']` · bối cảnh: *gian hàng thông tin trên mạng*

> Điểm B: `___/___/___`

**C.** Một giáo viên nam đang giảng bài trong một lớp học trực tuyến với màn hình hiển thị bài toán toán học.

> đối tượng: `['giáo viên nam']` · bối cảnh: *một lớp học trực tuyến*

> Điểm C: `___/___/___`

**D.** Một giáo viên đang giảng bài tại khoang giảng dạy.

> đối tượng: `['thanh niên', 'câu 7']` · bối cảnh: *khoang giảng dạy*

> Điểm D: `___/___/___`

---

## 30. `595.jpg`

**A.** Hai người đàn ông đang đứng trước một bảng thông báo màu đen, trên đó có ghi rõ thông tin về việc trao tặng học bổng tài năng trẻ của Trường Đại học Quốc tế Sài Gòn. Bảng thông báo có màu đen và xanh dương, chữ viết màu trắng. Hai người đàn ông mặc vest lịch sự, đứng nghiêm chỉnh trước bảng thông báo. Bối cảnh là một không gian hiện đại, sang trọng.

> đối tượng: `['hai nguoi nam', 'bảng trắng']` · bối cảnh: *một toà nhà hiện đại với bảng thông báo*

> Điểm A: `___/___/___`

**B.** Những người đàn ông đang trao tặng một bảng quảng cáo với thông tin về chương trình học bổng tài năng trẻ tại Trường Đại học Quốc tế Sài Gòn.

> đối tượng: `['người đàn ông mặc áo sơ mi màu trắng', 'người đàn ông mặc vest đen và cà vạt đỏ']` · bối cảnh: *sàn diễn trong một buổi lễ công bố tại Trường Đại học Quốc tế Sài Gòn*

> Điểm B: `___/___/___`

**C.** 2 người đang cầm một bảng thông tin, bảng thông tin có hình ảnh của Trường Đại Học Quốc Tế Sài Gòn và các biểu tượng liên quan đến giáo dục

> đối tượng: `['2 người đang cầm một bảng thông tin', 'bảng thông tin có hình ảnh của Trường Đại Học Quốc Tế Sài Gòn và các biểu tượng liên quan đến giáo dục']` · bối cảnh: *Trường Đại Học Quốc Tế Sài Gòn*

> Điểm C: `___/___/___`

**D.** Một giáo viên nam và một sinh viên nam đang trao thưởng cho Quỹ Học bổng Tài năng trẻ tại Trường Đại học Quốc tế Sài Gòn.

> đối tượng: `['một giáo viên nam', 'một sinh viên nam']` · bối cảnh: *một lễ công bố tại Trường Đại học Quốc tế Sài Gòn*

> Điểm D: `___/___/___`

---
