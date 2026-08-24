# HỆ THỐNG QUẢN LÝ MÔ HÌNH AI TẬP TRUNG (UNIFIED MODEL REPOSITORY & REGISTRY)

Thư mục `models/` là trung tâm đăng ký, điều phối và nạp các mô hình Trí Tuệ Nhân Tạo đa phương thức trong toàn bộ hệ thống AIC 2026.

---

## 1. Bản Đồ Danh Mục Mô Hình AI (Model Catalog Matrix)

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       AIC 2026 UNIFIED MODEL ARCHITECTURE                                              │
├──────────────────────────┬──────────────────────────────┬──────────────┬────────────┬─────────────┬────────────────────┤
│ PHÂN HỆ MÔ HÌNH          │ TÊN MÔ HÌNH & HUGGINGFACE ID │ KIẾN TRÚC    │ THAM SỐ    │ ĐẶC TRƯNG   │ MÔI TRƯỜNG KHUYÊN  │
├──────────────────────────┼──────────────────────────────┼──────────────┼────────────┼─────────────┼────────────────────┤
│ 1. VISION EMBEDDING      │ SigLIP SO400M Patch14-384    │ ViT-SO400M   │ 400M       │ Vector 1152d│ Kaggle GPU / TPU   │
│                          │ ViSigLIP-OT (Vietnamese Bi)  │ ViT-768      │ 86M        │ Vector 768d │ Kaggle GPU / Local │
│                          │ SigLIP Base Patch16-224      │ ViT-Base     │ 86M        │ Vector 768d │ Local Live Stream  │
│                          │ CLIP ViT-Large/14            │ ViT-L/14     │ 304M       │ Vector 768d │ Fallback Search    │
├──────────────────────────┼──────────────────────────────┼──────────────┼────────────┼─────────────┼────────────────────┤
│ 2. OBJECT DETECTION      │ YOLOv8 Nano (yolov8n.pt)     │ CSPDarknet   │ 3.2M       │ BBox COCO   │ Local CPU Preview  │
│                          │ YOLOv8 Extra-Large (v8x.pt)  │ Deep CSP     │ 68.2M      │ BBox COCO   │ Kaggle Offline GPU │
│                          │ YOLO11 Extra-Large (11x.pt)  │ C3k2 Spatial │ 56.9M      │ BBox SOTA   │ Kaggle Offline GPU │
│                          │ YOLO-World v2 (ViT Text-BBox)│ Vision-Lang  │ 66.8M      │ Open-Vocab  │ Văn hóa bản địa VN │
├──────────────────────────┼──────────────────────────────┼──────────────┼────────────┼─────────────┼────────────────────┤
│ 3. OPTICAL CHAR RECOG    │ VietOCR (vgg_transformer)    │ ViT/Seq2Seq  │ 35M        │ Tiếng Việt  │ Kaggle GPU / Local │
│                          │ PaddleOCR v4 (2-Tier Fast)   │ DBNet+SVTR   │ 15M        │ Bóc Tách TV │ Local & Kaggle     │
├──────────────────────────┼──────────────────────────────┼──────────────┼────────────┼─────────────┼────────────────────┤
│ 4. AUDIO SPEECH-TO-TEXT  │ Whisper Large-v3 Turbo       │ Audio Transf │ 809M       │ Sub-Word TS │ Kaggle GPU / TPU   │
│                          │ PhoWhisper Base (Vietnamese) │ Whisper-Vi   │ 74M        │ Audio Text  │ Local Video QA     │
└──────────────────────────┴──────────────────────────────┴──────────────┴────────────┴─────────────┴────────────────────┘
```

---

## 2. Giải Thích Kiến Trúc: Tại Sao Local Dùng YOLOv8n Trong Khi Kaggle Dùng YOLOv8x / YOLO-World?

### 2.1. Đối với Môi Trường Local (Máy tính cá nhân / CPU Interactive Studio)
- **Ràng buộc phần cứng:** Máy local thường chạy CPU hoặc GPU rời hạn chế (VRAM 4-8GB).
- **Yêu cầu độ trễ (Latency < 200ms theo Rule 4):**
  * `yolov8n` chỉ có **3.2M tham số** (dung lượng 6MB). Tốc độ suy luận trên CPU chỉ mất **~15ms / frame**. Khi người dùng duyệt video trên Studio UI (15-20 frames), toàn bộ thao tác trích xuất và hiển thị hoàn tất tức thì (<0.3s).
  * Nếu chạy `yolov8x` (68M tham số) trên CPU, mỗi frame mất **~350 - 800ms**. Tải 20 frames sẽ làm đơ giao diện mất 10 - 15 giây, gây trải nghiệm rất chậm chạp khi thao tác tương tác người dùng.

### 2.2. Đối với Môi Trường Offline Preprocessing (Kaggle Dual T4 GPU / TPU v3-8)
- **Tận dụng tối đa tài nguyên Cloud:** Hệ thống chạy theo mẻ (Batch Size = 32 hoặc 64) trên GPU T4.
- **Mục tiêu tối đa hóa độ phủ (High Recall & Dense Multi-Object):**
  * Sử dụng **YOLOv8x / YOLO11x**: Bắt chuẩn xác các vật thể kích thước siêu nhỏ ở xa, đếm chính xác số người trong các khung cảnh đông đúc hoặc bị che khuất một phần.
  * Sử dụng **YOLO-World v2 (Open-Vocabulary ViT)**: Nhờ có bộ mã hóa văn bản Vision-Language kết hợp ViT, mô hình có thể phát hiện các vật thể văn hóa Việt Nam thông qua Prompting trực tiếp:
    * `"traditional Vietnamese dragon dance lion head"` (Đầu lân)
    * `"conical leaf hat"` (Nón lá)
    * `"Vietnamese traditional Ao Dai dress"` (Áo dài)
    * `"three-wheeled cyclopab rickshaw"` (Xe xích lô)
    * `"square sticky rice cake"` (Bánh chưng)

---

## 3. Kiến Trúc Mô Hình Thị Giác Nâng Cao (Vision Transformer - Dual ViT)

Trong hệ thống FAISS Indexing (System 2):
1. **SigLIP SO400M Patch14-384 (`google/siglip-so400m-patch14-384`):**
   - Không gian vector: **1152 chiều (1152d)**.
   - Độ phân giải đầu vào 384x384 pixel giúp đọc chi tiết các bảng hiệu, bối cảnh phức tạp và tương tác tinh tế giữa người và vật thể.
2. **ViSigLIP-OT (`bkai-foundation-models/vietnamese-bi-encoder`):**
   - Không gian vector: **768 chiều (768d)**.
   - Được huấn luyện trên hàng triệu cặp ảnh - văn bản tiếng Việt, giúp thấu hiểu sâu sắc các câu truy vấn có cấu trúc ngữ pháp thuần Việt mà các mô hình quốc tế thường dịch sai nghĩa.

---

## 4. Cách Sử Dụng Bộ Loader Tập Trung Trong Mã Nguồn

```python
from models.model_registry import get_model_info, get_available_models
from models.yolo_detector_loader import YOLODetectorLoader
from models.vision_embedding_loader import VisionEmbeddingLoader

# 1. Nạp YOLO theo cấp độ mong muốn (Tự động chuyển CUDA/CPU)
yolo_model = YOLODetectorLoader.get_model(model_name="yolov8x")  # Hoặc 'yolov8n' cho local

# 2. Nạp Vision Embedding SigLIP ViT
siglip_model, siglip_proc = VisionEmbeddingLoader.load_siglip_so400m()

# 3. Tra cứu thông số mô hình
info = get_model_info("siglip-so400m-384")
print(f"Model: {info.name} | Dims: {info.dimension} | Params: {info.parameters}")
```
