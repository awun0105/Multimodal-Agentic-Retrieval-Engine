# Hệ thống Benchmark Multimodal Embeddings (AIC 2025)

Thư mục này chứa các kịch bản (scripts/notebooks) phục vụ quá trình đo lường hiệu năng (Benchmark) cho 24 mô hình Multimodal Embedding tiên tiến nhất (SOTA) trong khuôn khổ bài toán Video Retrieval.

## Bối cảnh và Vấn đề (The Kaggle I/O Bottleneck)
Môi trường Kaggle Notebooks cung cấp tài nguyên điện toán rất mạnh (2x GPU T4) nhưng lại áp đặt giới hạn nghiêm ngặt về không gian lưu trữ: **tối đa 20GB cho phân vùng `/kaggle/working`**. Với các tập dữ liệu thực tế (chứa hàng trăm nghìn khung hình lẻ), việc xả nén trực tiếp lên đĩa cứng không chỉ làm hệ thống quá tải (Disk Quota Exceeded) mà còn gây nghẽn cổ chai (I/O Bottleneck) khiến GPU phải chờ dữ liệu từ ổ cứng.

Để giải quyết triệt để vấn đề này, chúng tôi cung cấp **hai hướng tiếp cận chính**:

---

## 1. Phương pháp Tiêu chuẩn (Kaggle Direct Benchmark)
**Sử dụng tệp:** `kaggle_benchmark.ipynb`

Đây là cách tiếp cận truyền thống, phù hợp khi bạn sử dụng các tập dữ liệu nhỏ (dưới 19.5GB) hoặc khi dữ liệu đã được xả nén sẵn trực tiếp trên Kaggle Datasets (phân vùng `/kaggle/input`). 

- **Ưu điểm:** Đơn giản, dễ thực thi, hoạt động ngay lập tức (Out-of-the-box).
- **Nhược điểm:** Phải sử dụng chiến lược "Đóng gói phân mảnh" (Chunking) ở Bước 6 để chia nhỏ dữ liệu đầu ra nhằm lách luật 20GB của Kaggle.

---

## 2. Phương pháp Tối ưu I/O (Virtual Cache Reader)
**Sử dụng cặp tệp:** `colab_data_prep.ipynb` + `kaggle_benchmark_blob.ipynb`

Đây là kiến trúc nâng cao giúp vượt qua hoàn toàn giới hạn đĩa cứng, tận dụng sự linh hoạt của Google Colab và sức mạnh đa GPU của Kaggle.

### Bước 2.1. Đóng gói dữ liệu (Trên Google Colab)
**Chạy tệp:** `colab_data_prep.ipynb`
1. Đẩy các tệp `.zip` gốc (từ BTC) lên Google Drive.
2. Chạy kịch bản trên Colab (sử dụng CPU). Colab sẽ xả nén các tệp zip vào ổ SSD cục bộ của nó, sau đó gom toàn bộ ảnh lại thành một tệp nhị phân duy nhất (`cached_keyframes.blob`).
3. Cấu trúc thư mục (Nguồn gốc khung hình) được bảo toàn tuyệt đối bên trong tệp `.blob`.
4. Sau khi hoàn tất, lấy tệp `.blob` từ Drive và đăng tải (Upload) lên Kaggle dưới dạng một Dataset mới.

### Bước 2.2. Trích xuất đa GPU (Trên Kaggle)
**Chạy tệp:** `kaggle_benchmark_blob.ipynb`
1. Liên kết Kaggle Dataset chứa tệp `.blob` vừa tạo vào Notebook.
2. Trình tải dữ liệu (`DataLoader`) sẽ định vị tệp `.blob`, thiết lập một luồng đọc ảo (Virtual Reader) trực tiếp vào bên trong cấu trúc tệp.
3. Hình ảnh được nạp thẳng lên VRAM của GPU dưới dạng hệ nhị phân (Binary Streams) mà không hề tồn tại trên ổ cứng `/kaggle/working`. Không còn cảnh báo tràn đĩa!

---

## Ghi chú về Môi trường Google Colab
Trong trường hợp Kaggle hết hạn mức sử dụng (Quota GPU), bạn có thể sử dụng kịch bản dự phòng **`colab_benchmark.py`**. 
Đây là bản thu gọn dành riêng cho nền tảng Colab (với thiết lập 1 GPU T4). Tuy nhiên, tốc độ xử lý sẽ chậm hơn đáng kể so với kiến trúc Dual-GPU trên Kaggle.
