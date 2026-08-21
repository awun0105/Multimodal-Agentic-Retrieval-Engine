# AIC26 — Trang chủ

Nguồn: `https://sotuyenaic.oj.io.vn/`  
Tiêu đề trang: **AIC26 — Trang chủ**  

---

# AIC26 — Cuộc thi AI

# Hướng dẫn nộp bài sơ tuyển

## Các loại truy vấn

Vòng sơ tuyển bao gồm 3 dạng truy vấn chính:

1. **Textual Known Item Search (Textual KIS)**: Tìm kiếm chính xác theo văn bản
2. **Visual Question Answering (Q&A)**: Truy vấn dạng Hỏi-Đáp
3. **Temporal Retrieval and Alignment of Key Events (TRAKE)**: Truy xuất và căn chỉnh sự kiện video theo thời gian

## Các gói truy vấn

Trong vòng sơ tuyển BTC sẽ cung cấp lần lượt các gói câu truy vấn theo nhiều đợt. Với mỗi gói câu truy vấn, đội thi cần trả về kết quả tương ứng và nộp trực tiếp trên hệ thống thi này bằng tài khoản BTC đã cấp.

Với mỗi gói câu truy vấn, BTC sẽ cung cấp một danh sách các câu truy vấn trong từng file text. Ví dụ trong đợt 1, BTC cung cấp gói gồm 4 câu truy vấn `query-1-kis`, `query-2-kis`, `query-3-qa`, `query-4-trake` tương ứng với nội dung trong 4 file `query-1-kis.txt`, `query-2-kis.txt`, `query-3-qa.txt`, `query-4-trake.txt`.

**Quy ước tên file truy vấn:**

- Hậu tố `"kis"`: Câu truy vấn dạng Textual KIS
- Hậu tố `"qa"`: Câu truy vấn dạng Q&A
- Hậu tố `"trake"`: Câu truy vấn dạng TRAKE

## Yêu cầu kết quả

Đối với mỗi câu truy vấn, đội thi cần nộp tương ứng một file `.csv` (comma-separated values file) với mỗi dòng tương ứng với một lần đội dự đoán kết quả. Đội thi có thể nộp file tối đa 100 dòng. Kết quả trên mỗi dòng của đội có format theo từng loại truy vấn:

### 1. Textual Known Item Search (Textual KIS)

**Format**: `<Tên file video>, <Frame Idx>`

**Ví dụ**:

```csv
L00_V000, 1234
L00_V055, 5555
L01_V028, 25300
```

### 2. Question Answering (Q&A)

**Format**: `<Tên file video>, <Frame Idx>, <Answer>`

**Quy định cho Answer**:

- Độ dài tối đa: **100 ký tự**
- Có thể bằng tiếng Việt hoặc tiếng Anh
- Được so sánh chính xác về mặt ngữ nghĩa với đáp án

**Ví dụ**:

```csv
L01_V028, 3450, "5"
L02_V011, 1200, "Năm người"
L03_V005, 2800, "Màu đỏ"
```

### 3. Temporal Retrieval and Alignment of Key Events (TRAKE)

**Format**: `<Tên file video>, <Frame ID_1>, <Frame ID_2>, ..., <Frame ID_N>`

Trong đó:

- `Frame ID_1, Frame ID_2, ..., Frame ID_N` là các keyframe tương ứng với N events trong chuỗi sự kiện
- Số lượng Frame ID phải khớp với số events được yêu cầu trong truy vấn
- Thứ tự các Frame ID phải tuân theo thứ tự thời gian của các events

**Ví dụ** (chuỗi 4 events):

```csv
L10_V001, 1200, 1850, 2100, 2450
L10_V001, 1180, 1820, 2080, 2420
L11_V003, 5100, 5700, 6200, 6800
```

## Quy chuẩn định dạng CSV

> **⚠️ Lưu Ý QUAN TRỌNG cho học sinh THPT**:
>
> **CSV ≠ Excel**: Đây là hai định dạng file hoàn toàn khác nhau!
>
> - **File CSV (.csv)**: Là file văn bản thuần túy, chỉ chứa dữ liệu được phân cách bằng dấu phẩy
> - **File Excel (.xlsx/.xls)**: Là file nhị phân phức tạp của Microsoft Excel
>
> **PHẢI NỘP FILE .CSV**, KHÔNG PHẢI FILE EXCEL!
>
> **Cách tạo file CSV đúng**:
>
> 1. **Từ Excel**: File → Save As → chọn `CSV (Comma delimited) (*.csv)`
> 2. **Từ Google Sheets**: File → Download → Comma Separated Values (.csv)
> 3. **Từ Notepad**: Gõ trực tiếp theo format và lưu với đuôi `.csv`
> 4. **Từ các text editor**: VS Code, Sublime Text, Notepad++
>
> **Kiểm tra file CSV**:
>
> - Có thể mở bằng Notepad và thấy dữ liệu dạng text thuần túy
> - Kích thước file nhỏ hơn nhiều so với Excel
> - Đuôi file phải là `.csv` (KHÔNG phải `.xlsx` hoặc `.xls`)

### Quy tắc chung

1. **Encoding**: UTF-8
2. **Delimiter**: Dấu phẩy (`,`)
3. **Line ending**: CRLF (`\r\n`) hoặc LF (`\n`)
4. **Không có header row**: File CSV bắt đầu trực tiếp bằng dữ liệu

### Xử lý ký tự đặc biệt

> **Lưu ý quan trọng**: Dấu ngoặc kép chỉ **BẮT BUỘC** khi answer chứa các ký tự đặc biệt. Nếu answer đơn giản không có ký tự đặc biệt, có thể bỏ qua dấu ngoặc kép.

1. **Dấu phẩy trong answer**: **BẮT BUỘC** bao quanh bằng dấu ngoặc kép

   ```csv
   L01_V028, 3450, "Có 3 người, bao gồm nam và nữ"
   ```

2. **Dấu ngoặc kép trong answer**: **BẮT BUỘC** escape bằng double quotes

   ```csv
   L01_V028, 3450, "Anh ấy nói ""Xin chào"""
   ```

3. **Xuống dòng trong answer**: **BẮT BUỘC** bao quanh bằng dấu ngoặc kép

   ```csv
   L01_V028, 3450, "Dòng 1
   Dòng 2"
   ```

4. **Answer đơn giản**: **KHÔNG BẮT BUỘC** dấu ngoặc kép

   ```csv
   L01_V028, 3450, 5
   L02_V011, 1200, Năm người
   L03_V005, 2800, Màu đỏ
   ```

5. **Khoảng trắng đầu/cuối**: Được giữ nguyên, không tự động trim

### Ví dụ CSV chuẩn cho từng loại

**Textual KIS** (`query-1-kis.csv`):

```csv
L00_V000,1234
L00_V055,5555
L01_V028,25300
```

**Q&A** (`query-2-qa.csv`) — **Cả hai cách đều đúng**:

```csv
L01_V028,3450,5
L02_V011,1200,Năm người
L03_V005,2800,"Màu đỏ, rất đẹp"
L04_V012,4100,"Anh ấy nói ""Tuyệt vời"""
```

**HOẶC** với dấu ngoặc kép cho tất cả:

```csv
L01_V028,3450,"5"
L02_V011,1200,"Năm người"
L03_V005,2800,"Màu đỏ, rất đẹp"
L04_V012,4100,"Anh ấy nói ""Tuyệt vời"""
```

**TRAKE** (`query-3-trake.csv` — 4 events):

```csv
L10_V001,1200,1850,2100,2450
L10_V001,1180,1820,2080,2420
L11_V003,5100,5700,6200,6800
```

### Quy tắc dấu ngoặc kép trong CSV

#### KHÔNG cần ngoặc kép

- Answer đơn giản: `5`, `Năm người`, `Màu đỏ`, `Ba`
- Chỉ chứa chữ cái, số, khoảng trắng thông thường
- Không có dấu phẩy, ngoặc kép, xuống dòng

#### BẮT BUỘC có ngoặc kép

- Answer có dấu phẩy: `"Có 3 người, bao gồm nam và nữ"`
- Answer có ngoặc kép: `"Anh ấy nói ""Xin chào"""`
- Answer có xuống dòng: `"Dòng 1\nDòng 2"`

#### An toàn nhất

Để tránh nhầm lẫn, có thể **luôn đặt dấu ngoặc kép** cho tất cả answer trong Q&A. Cả hai cách đều được hệ thống chấp nhận.

### Hướng dẫn tạo file CSV cho học sinh THPT

#### Phương pháp 1: Sử dụng Microsoft Excel

1. Mở Excel và nhập dữ liệu theo đúng format
2. **File** → **Save As**
3. Chọn vị trí lưu file
4. Trong mục **Save as type** → chọn **CSV (Comma delimited) (*.csv)**
5. Đặt tên file theo quy định (ví dụ: `query-1-kis.csv`)
6. Click **Save**
7. Nếu Excel hỏi về compatibility → click **Yes**

#### Phương pháp 2: Sử dụng Google Sheets

1. Mở Google Sheets và nhập dữ liệu
2. **File** → **Download** → **Comma Separated Values (.csv)**
3. File sẽ được tải về máy với đuôi `.csv`

#### Phương pháp 3: Sử dụng Notepad (cho người hiểu kỹ thuật)

1. Mở Notepad
2. Gõ dữ liệu theo đúng format (ví dụ: `L00_V000,1234`)
3. **File** → **Save As**
4. Trong mục **Save as type** → chọn **All Files (*.*)**
5. Đặt tên file với đuôi `.csv` (ví dụ: `query-1-kis.csv`)
6. Trong mục **Encoding** → chọn **UTF-8**

#### Kiểm tra file CSV đã đúng chưa

1. Click chuột phải vào file → **Open with** → **Notepad**
2. Nếu thấy dữ liệu dạng text thuần túy với dấu phẩy phân cách → ✅ ĐÚNG
3. Nếu thấy ký tự lạ hoặc không đọc được → ❌ SAI (có thể vẫn là Excel format)

#### Lỗi thường gặp

- **Lưu nhầm file Excel**: File có đuôi `.xlsx`/`.xls` thay vì `.csv`
- **Encoding sai**: File hiển thị ký tự lạ khi mở bằng Notepad
- **Delimiter sai**: Sử dụng dấu chấm phẩy (`;`) thay vì dấu phẩy (`,`)
- **Có header**: Dòng đầu chứa tiêu đề thay vì dữ liệu

## Nộp kết quả cho gói truy vấn

Mỗi đội thi đăng nhập bằng tài khoản BTC đã cấp (theo thông tin đội đã đăng ký trước đó với BTC), vào đúng vòng thi tương ứng và nộp file `.zip` trực tiếp trên hệ thống — không cần đăng ký thêm ở đâu khác.

### Cách chuẩn bị file nộp

**Bước 1**: Tạo thư mục có tên `submission`

**Bước 2**: Đặt tất cả file CSV kết quả vào trong thư mục `submission`

**Bước 3**: Nén thư mục `submission` thành file `.zip`

**Bước 4 (Tùy chọn)**: Đổi tên file zip thành tên phù hợp (ví dụ: `team_ABC_round1.zip`)

### Cấu trúc thư mục yêu cầu

```text
submission/
├── query-1-kis.csv
├── query-2-kis.csv
├── query-3-qa.csv
├── query-4-trake.csv
└── ... (các file CSV khác)
```

**Ví dụ file nộp cuối cùng**: `team_ABC_round1.zip` chứa:

```text
submission/
├── query-1-kis.csv
├── query-2-kis.csv
├── query-3-qa.csv
└── query-4-trake.csv
```

> **Lưu ý quan trọng:**
>
> - **PHẢI có thư mục `submission`** bên trong file zip
> - **KHÔNG nén trực tiếp các file CSV** — phải nén thư mục `submission`
> - Cách tính điểm được mô tả trong đề bài của từng vòng thi trên hệ thống
> - **Tên file video không có phần đuôi** (`.mp4`)
> - **Frame ID** sẽ được so sánh dưới dạng số nguyên
> - **Answer** (Q&A) sẽ được so sánh dưới dạng chuỗi chính xác
> - **Answer** (Q&A) có độ dài tối đa **100 ký tự**
> - Đối với **TRAKE**: Số lượng Frame ID phải khớp chính xác với số events yêu cầu
> - Chỉ chấp nhận file nén định dạng `.zip`
> - **Khuyến cáo**: Tên file zip chỉ nên bao gồm các ký tự chữ hoặc số

## Đánh giá và xếp hạng

Kết quả đánh giá trên **Public Leaderboard** chỉ tính dựa trên 50% đáp án của BTC. Kết quả cuối cùng của đội nộp sẽ được tính trên 100% đáp án và dùng để xếp hạng vòng sơ tuyển tại **Private Leaderboard**.

### Phương pháp tính điểm

Mỗi gói truy vấn, các đội được phép nộp kết quả tối đa **3 lần**. Kết quả được dùng để xếp hạng là kết quả đội nộp **lần cuối cùng**.

> **Lưu ý cuối cùng:**
>
> - Mỗi đội chỉ được dùng duy nhất một tài khoản để nộp bài
> - Khi nộp sai định dạng vẫn tính là 01 lần nộp
> - Đội cần lưu ý chọn lựa kết quả nào để nộp lần cuối cùng
> - Khuyến nghị kiểm tra kỹ format CSV trước khi nộp để tránh lỗi parse

---


## Bổ sung từ tài liệu “Thông tin vòng Sơ tuyển AIC2026”

Tài liệu bổ sung mô tả chi tiết hơn về **nội dung truy vấn**, **cách tính điểm** và **dữ liệu vòng sơ tuyển — đợt 1**.

---

# Thông tin vòng Sơ tuyển AIC2026

## 1. Nội dung các truy vấn vòng sơ tuyển

### 1.1. Textual Known Item Search — Textual KIS

Đây là nhiệm vụ **tìm kiếm sự kiện dựa trên mô tả bằng văn bản**.

**Nội dung truy vấn**:

- Ban giám khảo cung cấp một mô tả bằng ngôn ngữ tự nhiên về một sự kiện.
- Đội dự thi cần định vị chính xác đoạn video chứa sự kiện.
- Kết quả được xác định bằng cách chỉ ra **một khung hình bất kỳ thuộc đoạn video đó**.
- Ở vòng sơ tuyển, nội dung đoạn mô tả được cung cấp sẵn và trọn vẹn.

**Ví dụ**:

> Truy vấn: “Tìm video về một diễn giả mặc áo đỏ phát biểu tại một cuộc họp báo ngoài trời, phía sau có nhiều cây xanh.”  
> Kết quả nộp: `video_id = video_abc(.mp4)`, `frame_id = 1500`.

### 1.2. Q&A — Visual Question Answering

Đây là nhiệm vụ **tìm kiếm sự kiện và trích xuất thông tin cụ thể từ video**.

**Nội dung truy vấn**:

- Ban giám khảo cung cấp một mô tả bằng ngôn ngữ tự nhiên của một sự kiện.
- Kèm theo đó là một câu hỏi về thông tin trong sự kiện này.
- Đội dự thi cần tìm đúng khoảnh khắc liên quan và trả lời câu hỏi.
- Câu trả lời có thể bằng tiếng Việt hoặc tiếng Anh.

**Ví dụ**:

> Truy vấn: “Trong video về lễ trao giải thưởng âm nhạc, có bao nhiêu người lên sân khấu để nhận giải thưởng lớn nhất?”  
> Kết quả nộp: `video_id = video_xyz(.mp4)`, `frame_id = 3450`, `answer = "5"` hoặc `"Năm"`.

### 1.3. TRAKE — Temporal Retrieval and Alignment of Key Events

Đây là nhiệm vụ phức hợp, đòi hỏi độ chính xác cao trong cả **truy xuất video** và **căn chỉnh thời gian của các khoảnh khắc quan trọng**.

TRAKE đánh giá khả năng của hệ thống trong việc hiểu nội dung video một cách toàn diện: từ bối cảnh chung cho đến từng khoảnh khắc chi tiết. Hệ thống không chỉ cần tìm đúng video, mà còn phải xác định chính xác các **semantic keyframe** của một chuỗi sự kiện có cấu trúc bên trong video đó.

Nhiệm vụ TRAKE gồm 2 giai đoạn:

1. **Retrieval — Truy xuất**: từ thư viện video lớn, tìm ra **một video duy nhất** chứa chuỗi sự kiện khớp nhất với truy vấn.
2. **Alignment — Căn chỉnh**: trong video đã truy xuất, xác định chính xác **một khung hình ngữ nghĩa duy nhất** cho mỗi giai đoạn của chuỗi sự kiện.

**Lưu ý về semantic keyframe**:

> “Khung hình ngữ nghĩa” là khoảnh khắc mang ý nghĩa về nội dung, khác với “I-Frame” là khung hình kỹ thuật trong các thuật toán nén video đã được cung cấp cho các đội thi.

**Ví dụ hành động “Nhảy cao”** — chuỗi sự kiện gồm 4 khoảnh khắc:

1. **Event 1 — Chạy đà (Approach)**: khoảnh khắc bàn chân đầu tiên chạm đất và bước qua khỏi vạch xuất phát.
2. **Event 2 — Giậm nhảy (Take-off)**: khoảnh khắc đầu tiên bàn chân của chân giậm nhảy rời hoàn toàn khỏi mặt đất.
3. **Event 3 — Bay qua xà (Clearance)**: khoảnh khắc phần hông của vận động viên ở vị trí cao nhất so với xà ngang.
4. **Event 4 — Tiếp đất (Landing)**: khoảnh khắc đầu tiên bất kỳ bộ phận nào của lưng, từ vai đến hông, bắt đầu chạm vào đệm.

---

## 2. Phương pháp đánh giá vòng sơ tuyển

Đối với mỗi truy vấn, đội thi được gửi tối đa **100 câu trả lời**. Mỗi câu trả lời được chấm một điểm gọi là **Điểm Tương Quan (R-Score)**.

**R-Score** là thang đo độ chính xác từ `0` đến `1`:

- `1`: hoàn toàn chính xác.
- `0`: không chính xác.
- Giá trị trung gian, ví dụ `0.7`: chính xác một phần.

Điểm cuối cùng cho mỗi truy vấn không chỉ dựa trên một câu trả lời duy nhất, mà là trung bình của những câu trả lời tốt nhất ở nhiều vị trí xếp hạng khác nhau.

### 2.1. R-Score theo từng loại truy vấn

#### 2.1.1. R-Score cho Textual KIS

**Định dạng trả lời**:

```csv
<video_id>,<frame_id>
```

Câu trả lời được xem là chính xác nếu:

1. `video_id` nộp khớp với video đúng của BTC.
2. `frame_id` nằm trong khoảng frame đáp án đúng `[s, e]`.

Công thức:

```text
R-Score(r_i) = I(v_i = GT_v AND id_i ∈ [s, e])
```

Trong đó `I(...)` là hàm chỉ thị:

- Trả về `1` nếu điều kiện đúng.
- Trả về `0` nếu điều kiện sai.

**Ví dụ**:

Đáp án đúng của BTC: video `L01_V001`, khung hình từ `500` đến `510`.

| Câu trả lời | Kết quả | R-Score |
|---|---|---:|
| `L01_V001,505` | Đúng video, frame nằm trong `[500,510]` | `1` |
| `L01_V001,600` | Đúng video nhưng sai khoảng frame | `0` |
| `L02_V003,505` | Sai video | `0` |

#### 2.1.2. R-Score cho Q&A

**Định dạng trả lời**:

```csv
<video_id>,<frame_id>,<answer>
```

Câu trả lời được xem là chính xác nếu:

1. `video_id` nộp khớp với video đúng của BTC.
2. `frame_id` nằm trong khoảng frame đáp án đúng `[s, e]`.
3. `answer` khớp với đáp án về mặt ngữ nghĩa.

Công thức:

```text
R-Score(r_i) = I(v_i = GT_v AND id_i ∈ [s, e] AND a_i = GT_a)
```

**Ví dụ**:

Đáp án đúng của BTC: video `L05_V005`, khung hình `800` đến `900`, answer là `màu xanh`.

| Câu trả lời | Kết quả | R-Score |
|---|---|---:|
| `L05_V005,888,màu xanh` | Đúng video, đúng frame, đúng answer | `1` |
| `L05_V005,888,màu trắng` | Sai answer | `0` |
| `L06_V007,888,màu xanh` | Sai video | `0` |

#### 2.1.3. R-Score cho TRAKE

**Định dạng trả lời**:

```csv
<video_id>,<frame_id_1>,...,<frame_id_N>
```

Điều kiện tiên quyết:

- Nếu `video_id` nộp **không khớp** với video đáp án của BTC, câu trả lời nhận `0` điểm ngay lập tức.
- Nếu đúng video, điểm được tính bằng **tỉ lệ khung hình khớp với đáp án**.

Với `N` là tổng số khoảnh khắc trong truy vấn, công thức:

```text
Nếu v_i = GT_v:
R-Score(r_i) = (1 / N) * Σ[j=1..N] I(id_i,j ∈ [s_j, e_j])

Nếu v_i ≠ GT_v:
R-Score(r_i) = 0
```

Với mỗi khoảnh khắc thứ `j`, đáp án quy định một đoạn khung hình `[s_j, e_j]` tương ứng với khoảnh khắc ngữ nghĩa đó. Đoạn này thường rất ngắn, thông thường **dưới 10 frame**. Một frame nộp `id_i,j` được coi là khớp nếu nằm trong đoạn `[s_j, e_j]`.

**Ví dụ TRAKE 4 khoảnh khắc**:

Đáp án đúng của BTC: video `L10_V010`, với các đoạn frame:

| Khoảnh khắc | Đoạn đáp án |
|---|---|
| 1 — Giậm nhảy | `[95,105]` |
| 2 — Bay qua xà | `[145,155]` |
| 3 — Tiếp đất | `[195,205]` |
| 4 — Đứng dậy | `[245,255]` |

Câu trả lời của đội thi:

```csv
L10_V010,101,156,203,251
```

Đánh giá:

| Thành phần | Kết quả |
|---|---|
| Video | Đúng `L10_V010` |
| Khoảnh khắc 1 | `101 ∈ [95,105]` → Đúng |
| Khoảnh khắc 2 | `156 ∉ [145,155]` → Sai |
| Khoảnh khắc 3 | `203 ∈ [195,205]` → Đúng |
| Khoảnh khắc 4 | `251 ∈ [245,255]` → Đúng |

Kết quả: khớp `3/4` khoảnh khắc, nên:

```text
R-Score = 3/4 = 0.75
```

### 2.2. Final Score cho mỗi truy vấn

Điểm cuối cùng của mỗi truy vấn được tính dựa trên các câu trả lời tốt nhất ở các mốc xếp hạng khác nhau.

Với mỗi ngưỡng:

```text
k ∈ {1, 5, 20, 50, 100}
```

Hệ thống xác định **Top-k R-Score**, ký hiệu `R@k`, là điểm R-Score cao nhất trong `k` câu trả lời đầu tiên.

Công thức:

```text
R@k = max_{1 ≤ i ≤ k} R-Score(r_i)
```

Final Score là trung bình cộng của 5 giá trị `R@k`:

```text
Final Score = (R@1 + R@5 + R@20 + R@50 + R@100) / 5
```

hoặc:

```text
Final Score = (1/5) * Σ_{k ∈ {1,5,20,50,100}} R@k
```

**Ví dụ**:

Đội thi nộp 100 câu trả lời cho một truy vấn:

- Câu trả lời đầu tiên có `R-Score = 0.5`.
- Câu trả lời ở vị trí số 3 có `R-Score = 0.8`, là câu cao nhất trong 100 câu.
- Câu trả lời ở vị trí số 15 có `R-Score = 0.6`.
- Các câu còn lại thấp hơn.

Khi đó:

| Mốc | Giá trị |
|---|---:|
| `R@1` | `0.5` |
| `R@5` | `0.8` |
| `R@20` | `0.8` |
| `R@50` | `0.8` |
| `R@100` | `0.8` |

Final Score:

```text
Final Score = (0.5 + 0.8 + 0.8 + 0.8 + 0.8) / 5 = 0.74
```

Cách tính này khuyến khích đội thi không chỉ tìm ra câu trả lời đúng, mà còn phải **xếp nó ở những vị trí đầu tiên trong danh sách trả lời**.

### Ý nghĩa chiến thuật của cách tính điểm

Vì Final Score lấy trung bình ở các mốc `1`, `5`, `20`, `50`, `100`, thứ tự dòng trong file CSV rất quan trọng:

- Dòng 1 ảnh hưởng trực tiếp tới `R@1`.
- Top 5 ảnh hưởng tới `R@5`.
- Top 20 ảnh hưởng tới `R@20`.
- Top 50 ảnh hưởng tới `R@50`.
- Top 100 ảnh hưởng tới `R@100`.

Do đó không nên xuất kết quả ngẫu nhiên. Nên sắp xếp các dòng theo độ tin cậy giảm dần:

```text
rank 1    = kết quả tự tin nhất
rank 2-5  = nhóm rất mạnh
rank 6-20 = nhóm mở rộng có khả năng đúng
rank 21-50 = nhóm dự phòng
rank 51-100 = nhóm coverage rộng
```

---

## 3. Thông tin dữ liệu vòng sơ tuyển — Đợt 1

Dữ liệu cung cấp cho các đội thi để làm quen với bài toán là một phần dữ liệu từ cuộc thi AIC 2026, gồm các thành phần sau:

### 3.1. Videos

Chứa video được cung cấp.

### 3.2. Keyframes

Chứa tất cả keyframe được trích xuất từ video.

- Keyframe được lưu trong thư mục tương ứng với tên file video.
- Ví dụ: keyframe của video `L01_V001.mp4` được lưu trong thư mục `L01_V001`.
- Tên file keyframe được đặt theo thứ tự tăng dần.
- Vị trí `frame index` tương ứng của mỗi keyframe được ghi trong file metadata.

### 3.3. Objects

Chứa file JSON liệt kê tất cả vật thể được phát hiện từ mô hình **Faster R-CNN pretrained trên OpenImages V4**.

- Tên file JSON tương ứng với tên file keyframe.
- Ví dụ: keyframe `L01_V001/0000.jpg` sẽ có file JSON object là `L01_V001/0000.json`.

### 3.4. CLIP features

Chứa CLIP features được trích xuất từ mô hình **clip-ViT-B-32** của tất cả keyframe.

- Toàn bộ CLIP features của keyframe được lưu trong một file `.npy` duy nhất.
- Thứ tự vector feature tăng dần tương ứng với chỉ số của keyframe.

### 3.5. Metadata

Metadata là thông tin metadata của video lấy từ YouTube của kênh cung cấp dữ liệu.

- Metadata của mỗi video là một file JSON có tên tương ứng với tên file video.
- Ví dụ: video `L01_V001.mp4` có file metadata `L01_V001.json`.
- Một số video trong dữ liệu cung cấp có thể không có file metadata tương ứng.

### 3.6. Link download dữ liệu

```text
https://docs.google.com/spreadsheets/d/1rfn1fieTThS_Ki3SIoJ6uXOx2AhMq7wGCak6W4jZyZM/edit?usp=sharing
```

### 3.7. Lưu ý về dữ liệu

- **Dữ liệu thi chính thức là Video**.
- Các thành phần còn lại gồm **Keyframes, Objects, CLIP features, Metadata** chỉ nhằm mục đích cung cấp thêm thông tin hoặc hỗ trợ xây dựng giải pháp mẫu cho thí sinh.
- Đây cũng là dữ liệu **batch 1 của AIC 2025**.
- Dữ liệu đầy đủ của vòng sơ tuyển AIC 2026 sẽ bao gồm thêm **batch 2**, dự kiến được thông báo cho các đội thi trong thời gian tới.

---

## 📋 BẢNG TÓM TẮT — NHỮNG ĐIỀU QUAN TRỌNG NHẤT

| **TIÊU CHÍ** | **YÊU CẦU** | **VÍ DỤ** |
|---|---|---|
| **📁 Định dạng file nộp** | ✅ File `.csv` thuần túy<br>❌ KHÔNG phải Excel (`.xlsx`/`.xls`) | `query-1-kis.csv` |
| **📦 Cách đóng gói** | File `.zip` chứa tất cả file CSV | `submission.zip` |
| **🎯 Format KIS** | `<video_name>, <frame_id>` | `L01_V028, 25300` |
| **❓ Format Q&A** | `<video_name>, <frame_id>, "<answer>"` | `L01_V028, 3450, "5"` |
| **⏱️ Format TRAKE** | `<video_name>, <frame_1>, <frame_2>, ...` | `L10_V001, 1200, 1850, 2100` |
| **💬 Câu trả lời Q&A** | Tối đa **100 ký tự**, tiếng Việt/Anh | `"Năm người"` |
| **📊 Số dòng tối đa** | **100 dòng** cho mỗi file CSV | — |
| **🎫 Số lần nộp** | Tối đa **3 lần** cho mỗi gói truy vấn | — |
| **🏆 Kết quả xếp hạng** | Lần nộp **cuối cùng** được tính điểm | — |
| **📝 Tên file video** | **KHÔNG có đuôi** `.mp4` | `L01_V028` ✅<br>`L01_V028.mp4` ❌ |
| **🔢 Frame ID** | Số nguyên, không có khoảng trắng thừa | `25300` ✅<br>`25 300` ❌ |
| **Text Editor an toàn** | Notepad, VS Code, Google Sheets | Excel cần Save As → CSV |

### 🚨 5 LỖI THƯỜNG GẶP NHẤT

| **LỖI** | **NGUYÊN NHÂN** | **CÁCH SỬA** |
|---|---|---|
| **🔴 File không được chấp nhận** | Nộp file Excel thay vì CSV | Save As → CSV trong Excel |
| **🔴 Thiếu thư mục submission** | Nén trực tiếp file CSV thay vì thư mục | Tạo thư mục `submission` rồi nén |
| **🔴 Dữ liệu hiển thị lạ** | Encoding không phải UTF-8 | Chọn UTF-8 khi Save |
| **🔴 Answer bị cắt** | Answer có dấu phẩy nhưng thiếu ngoặc kép | `"Năm người, gồm nam và nữ"` |
| **🔴 TRAKE sai số frame** | Thiếu/thừa frame cho các events | Kiểm tra đúng N events |

### ✅ CHECKLIST TRƯỚC KHI NỘP

- [ ] File có đuôi `.csv` (không phải `.xlsx` hay `.xls`)
- [ ] Mở file bằng Notepad thấy dữ liệu text thuần túy
- [ ] Tên file khớp với tên truy vấn (ví dụ: `query-1-kis.csv`)
- [ ] Format đúng theo loại truy vấn (KIS/Q&A/TRAKE)
- [ ] Answer Q&A không quá 100 ký tự
- [ ] TRAKE có đúng số frame theo yêu cầu
- [ ] Tên video không có đuôi `.mp4`
- [ ] **Đã tạo thư mục `submission` và đặt tất cả CSV vào đó**
- [ ] **File được nén từ thư mục `submission`** (không nén trực tiếp CSV)
- [ ] Đã kiểm tra số lần nộp còn lại

### 📞 KHI GẶP VẤN ĐỀ

1. **Kiểm tra lại format CSV** bằng cách mở file bằng Notepad
2. **Xem lại ví dụ** trong tài liệu này
3. **Thử tạo file CSV mới** theo hướng dẫn
4. **Liên hệ BTC** nếu vẫn gặp khó khăn kỹ thuật

---

## Vòng gần nhất

**Thanh niên, sinh viên — Vòng thử nghiệm**

Thời gian đóng theo HTML: `2026-08-21T12:30:00+00:00`  
Tương đương giờ Việt Nam: **19:30 ngày 21/08/2026**

## Liên kết trên trang

- [Thể lệ cuộc thi](/rules/)
- [Lịch thi](/timeline/)
- [Câu hỏi thường gặp](/faq/)
- [Thông báo](/announcements/)
- [Bảng điều khiển](/app/)
- [Đội AIC2026-603](/app/team/)
