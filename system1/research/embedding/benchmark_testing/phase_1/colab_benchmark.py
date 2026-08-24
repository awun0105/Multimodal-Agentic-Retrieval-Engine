# %% [markdown]
# # Template Dự phòng: Hệ thống Benchmark trên Google Colab
# 
# **Mô tả:**
# Kịch bản này được giữ lại như một **bản mẫu dự phòng (Fallback Template)** dành riêng cho môi trường Google Colab. 
# Hiện tại, do hạn chế chỉ được cấp phát 1 GPU (thường là dòng T4), tốc độ xử lý trên Colab sẽ chậm hơn 
# đáng kể so với kiến trúc Dual-GPU (2x T4) trên nền tảng Kaggle.
#
# **Chỉ định sử dụng:**
# Chỉ sử dụng kịch bản này trong trường hợp Kaggle hết hạn mức sử dụng (Quota) hoặc cần chạy kiểm thử, gỡ lỗi (debug) 
# nhanh các đoạn mã trên Colab. Hỗ trợ tự động khắc phục các lỗi đặc thù của Jina CLIP và ViCLIP-OT, 
# kết hợp cơ chế giải nén trực tiếp vào phân vùng SSD `/content/`.

# %% [code]
# ==============================================================================
# HẰNG SỐ & CẤU HÌNH TÙY CHỈNH (CẬP NHẬT TẠI ĐÂY)
# ==============================================================================

# Số lượng ảnh để benchmark tốc độ (mặc định 20)
BENCHMARK_IMAGE_COUNT = 20

# Danh sách 5 mô hình được lựa chọn để Benchmark (Anh & Việt)
CANDIDATE_MODELS = [
    "google/siglip-base-patch16-224",    # 1. SigLIP Base (Tiếng Anh - Siêu tốc độ, Cân bằng)
    "openai/clip-vit-base-patch32",      # 2. CLIP Base (Tiếng Anh - Baseline chuẩn mực của OpenAI)
    "jinaai/jina-clip-v2",               # 3. Jina CLIP v2 (SOTA Đa ngôn ngữ, hiểu Tiếng Việt xuất sắc)
    "openai/clip-vit-large-patch14",     # 4. CLIP Large (Thay thế ViCLIP bị lỗi code từ tác giả)
    "google/siglip-so400m-patch14-384",  # 5. SigLIP High-Res (Tiếng Anh - Độ phân giải cực cao, sắc nét nhất)
]

# Mô hình chốt hạ được sử dụng cho việc trích xuất toàn bộ 200,000 ảnh (Bước 5)
CANONICAL_MODEL = "jinaai/jina-clip-v2"  # Gợi ý: Chọn Jina để tối ưu cả Anh và Việt

# Bộ câu hỏi mẫu dùng để đánh giá tốc độ xử lý văn bản
TEST_QUERIES = [
    "người phụ nữ đang thái rau trong bếp",
    "a chef cooking in a modern kitchen",
    "biên tập viên thời sự đang đọc tin tức",
    "news anchor reporting in a broadcast studio"
]

# Tên file nén Cache lưu trên Google Drive
CACHE_TAR_NAME = "AIC_keyframes_cache.tar"

# Tên file FAISS Index lưu ra kết quả
FAISS_INDEX_NAME = "siglip.faiss"

# ==============================================================================

# %% [code]
# BƯỚC 1: Cài đặt Thư viện
# Khóa phiên bản transformers==4.40.0 để tương thích tốt với Jina CLIP v2.
!pip install -q transformers==4.40.0 torch sentencepiece pillow numpy protobuf faiss-cpu

# %% [code]
# BƯỚC 2: Khởi tạo Môi trường & Gắn kết Ổ cứng (Mount Drive)
import os
import glob
import shutil
import time
import json
import tarfile
import gc
import numpy as np
import torch
import faiss
from PIL import Image
from transformers import AutoProcessor, SiglipModel, CLIPModel, AutoModel

# Gắn kết Google Drive nếu đang chạy trên Google Colab
try:
    from google.colab import drive
    drive.mount('/content/drive')
    IS_COLAB = True
    print("[INFO] Đã kết nối Google Drive thành công.")
except ImportError:
    IS_COLAB = False
    print("[INFO] Đang chạy trong môi trường cục bộ (không phải Colab).")

# Cấu hình thiết bị phần cứng
device = "cuda" if torch.cuda.is_available() else "cpu"
batch_size = 64 if device == "cuda" else 4
print(f"[INFO] Chế độ xử lý: {device.upper()} | Kích thước lô (Batch Size): {batch_size}")

# Định nghĩa hệ thống đường dẫn lưu trữ
if IS_COLAB:
    base_drive = "/content/drive/MyDrive"
    source_aic2025_dir = os.path.join(base_drive, "AIC2025")
    if not os.path.exists(source_aic2025_dir):
        source_aic2025_dir = base_drive
    user_output_dir = os.path.join(base_drive, "AIC_Nhat")
else:
    source_aic2025_dir = os.path.join("..", "data")
    user_output_dir = os.path.join("..", "output_aic_nhat")

# Khởi tạo các thư mục đầu ra
sub_data_dir = os.path.join(user_output_dir, "sub_data")
embeddings_dir = os.path.join(user_output_dir, "embeddings")
reports_dir = os.path.join(user_output_dir, "reports")

for d in [sub_data_dir, embeddings_dir, reports_dir]:
    os.makedirs(d, exist_ok=True)

print("[INFO] Cấu hình đường dẫn hoàn tất.")
print(f"  - Thư mục nguồn (BTC): {source_aic2025_dir}")
print(f"  - Thư mục đích (Kết quả): {user_output_dir}")

# %% [markdown]
# ## BƯỚC 3: Giải Nén Dữ Liệu Tốc Độ Cao (Local SSD)
# 
# Nhằm tối ưu hóa tốc độ nhập/xuất dữ liệu (I/O) trên Colab, hệ thống sẽ bỏ qua việc truy xuất 
# trực tiếp từ Google Drive (có độ trễ mạng cao). Thay vào đó, dữ liệu sẽ được giải nén trực tiếp 
# vào ổ cứng thể rắn cục bộ tại `/content/extracted_keyframes`.
#
# **Cơ chế Lưu trữ đệm (Cache):**
# Hệ thống sẽ tìm kiếm tệp tin `AIC_keyframes_cache.tar`. Nếu tồn tại, quá trình xả nén sẽ được 
# rút ngắn xuống còn vài phút thay vì phải phân tích hàng trăm tệp ZIP riêng lẻ từ đầu.

# %% [code]
import zipfile

# Cấu hình thư mục giải nén trên SSD cục bộ
if IS_COLAB:
    extract_dir = "/content/extracted_keyframes"
else:
    extract_dir = os.path.join("..", "extracted_keyframes")
os.makedirs(extract_dir, exist_ok=True)

cache_tar_path = os.path.join(user_output_dir, CACHE_TAR_NAME)

# Kiểm tra sự tồn tại của file Cache
if os.path.exists(cache_tar_path):
    print(f"[INFO] Tìm thấy file Cache tại {cache_tar_path}. Đang tiến hành xả nén...")
    try:
        with tarfile.open(cache_tar_path, "r") as tar:
            tar.extractall(path=extract_dir)
        print("[SUCCESS] Đã xả nén hoàn tất từ file Cache.")
    except Exception as e:
        print(f"[ERROR] Lỗi trong quá trình xả nén Cache: {e}")
else:
    # Kịch bản dự phòng: Giải nén từ hàng loạt file ZIP gốc của BTC
    print("[INFO] Không tìm thấy Cache. Tiến hành giải nén từ file ZIP gốc.")
    zip_files = glob.glob(os.path.join(source_aic2025_dir, "**", "*.zip"), recursive=True)
    keyframe_zips = [z for z in zip_files if "keyframe" in os.path.basename(z).lower()]

    print(f"[INFO] Tổng số file ZIP Keyframes phát hiện: {len(keyframe_zips)}")

    for zf in keyframe_zips:
        folder_name = os.path.splitext(os.path.basename(zf))[0]
        target_dir = os.path.join(extract_dir, folder_name)
        if not os.path.exists(target_dir):
            print(f"  - Đang giải nén: {os.path.basename(zf)}...")
            os.makedirs(target_dir, exist_ok=True)
            try:
                with zipfile.ZipFile(zf, "r") as zip_ref:
                    zip_ref.extractall(target_dir)
            except Exception as e:
                print(f"    [ERROR] Thất bại khi giải nén {zf}: {e}")
        else:
            print(f"  - Đã tồn tại, bỏ qua: {os.path.basename(zf)}.")
    
    print("[SUCCESS] Hoàn tất xả nén toàn bộ từ file ZIP gốc.")

# %% [markdown]
# ## BƯỚC 3.5: Đóng Gói Bộ Nhớ Đệm (Cache Packaging)
# 
# Trong trường hợp tệp Cache chưa tồn tại (thường là lần khởi chạy đầu tiên), 
# hệ thống sẽ tự động liên kết toàn bộ hình ảnh trên SSD thành 1 tệp tin TAR duy nhất 
# và đồng bộ trở lại Google Drive. Tính năng này giúp giảm thiểu chi phí thời gian chuẩn bị 
# dữ liệu cho các phiên làm việc tiếp theo.

# %% [code]
if not os.path.exists(cache_tar_path):
    print("[INFO] Bắt đầu đóng gói toàn bộ ảnh thành 1 file Cache. Vui lòng đợi...")
    try:
        with tarfile.open(cache_tar_path, "w") as tar:
            for item in os.listdir(extract_dir):
                item_path = os.path.join(extract_dir, item)
                tar.add(item_path, arcname=item)
        cache_size_mb = os.path.getsize(cache_tar_path) / (1024 * 1024)
        print(f"[SUCCESS] Tạo file Cache thành công! (Dung lượng: {cache_size_mb:.2f} MB).")
    except Exception as e:
        print(f"[ERROR] Quá trình tạo Cache thất bại: {e}")
else:
    print("[INFO] File Cache đã tồn tại. Bỏ qua bước đóng gói.")

# %% [markdown]
# ## BƯỚC 4: Khởi Tạo Lớp Đóng Gói Đa Mô Hình (MultiModelBenchmark)
#
# Hàm này dùng kỹ thuật Duck-typing trong Python để xử lý hàng loạt các cấu trúc 
# mô hình (Architecture) khác nhau mà không cần viết riêng từng hàm.

# %% [code]
def scan_keyframes(root_dir):
    """
    Quét đệ quy toàn bộ thư mục để tìm ảnh JPG và PNG.
    """
    if not os.path.exists(root_dir):
        return []
    jpgs = glob.glob(os.path.join(root_dir, "**", "*.jpg"), recursive=True)
    pngs = glob.glob(os.path.join(root_dir, "**", "*.png"), recursive=True)
    return sorted(jpgs + pngs)

all_source_keyframes = scan_keyframes(extract_dir)
print(f"[INFO] Quét dữ liệu hoàn tất: Đã tìm thấy {len(all_source_keyframes)} ảnh Keyframes.")

def l2_normalize(vector: np.ndarray) -> np.ndarray:
    """
    Chuẩn hóa L2 cho Vector để tính toán Cosine Similarity chuẩn xác hơn 
    khi truy vấn (bắt buộc trước khi đưa vào FAISS IndexFlatIP).
    """
    norm = np.linalg.norm(vector, ord=2)
    return vector / norm if norm > 0 else vector

class MultiModelBenchmark:
    """
    Lớp đóng gói việc trích xuất đặc trưng hình ảnh và văn bản.
    Bao gồm các bản vá tự động cho Jina CLIP và ViCLIP.
    """
    def __init__(self, model_slug="google/siglip-base-patch16-224", device="cpu"):
        self.model_slug = model_slug
        self.device = device
        print(f"[INFO] Đang nạp mô hình '{model_slug}' vào bộ nhớ {device}...")
        
        # [Bản vá 0] Fix lỗi "Object of type dtype is not JSON serializable" của ViCLIP-OT
        # Tác giả ViCLIP-OT code nhầm phần parse config khiến config cache chứa torch.dtype
        import json
        _original_default = json.JSONEncoder.default
        def patched_default(self, obj):
            if isinstance(obj, torch.dtype):
                return str(obj)
            return _original_default(self, obj)
        json.JSONEncoder.default = patched_default
        
        self.processor = AutoProcessor.from_pretrained(model_slug, trust_remote_code=True)
        model_kwargs = {"trust_remote_code": True}
        
        # [Bản vá 1] Jina CLIP v2 mặc định dùng BFloat16, gây lỗi trên GPU đời cũ (T4).
        # Giải pháp: Ép kiểu dữ liệu về torch.float32.
        if "jina" in model_slug.lower():
            model_kwargs["torch_dtype"] = torch.float32
            
        # Kích hoạt mô hình tùy theo định dạng kiến trúc của tác giả
        # [Bản vá 2] ViCLIP sử dụng AutoModel chung thay vì CLIPModel. 
        # Việc dùng AutoModel sẽ kích hoạt đúng kiến trúc "viclip_ot" và gọi PhoBERT ra,
        # giải quyết dứt điểm lỗi CUDA Device-side assert (Index Out of Bounds).
        if "viclip" in model_slug.lower():
            self.model = AutoModel.from_pretrained(model_slug, **model_kwargs).to(device)
        elif "clip" in model_slug.lower() and "jina" not in model_slug.lower():
            self.model = CLIPModel.from_pretrained(model_slug, **model_kwargs).to(device)
        elif "siglip" in model_slug.lower():
            self.model = SiglipModel.from_pretrained(model_slug, **model_kwargs).to(device)
        else:
            self.model = AutoModel.from_pretrained(model_slug, **model_kwargs).to(device)
            
        self.model.eval()
        print(f"[SUCCESS] Nạp thành công mô hình {model_slug}.")

    def embed_image_paths(self, img_paths, bsize=64):
        """
        Trích xuất Vector Hình Ảnh theo lô (Batch).
        """
        all_vecs = []
        if not img_paths:
            return np.ascontiguousarray(all_vecs, dtype=np.float32)
            
        for i in range(0, len(img_paths), bsize):
            batch_paths = img_paths[i:i+bsize]
            batch_imgs = []
            
            # Xử lý ngoại lệ với các ảnh bị lỗi/corrupted
            for p in batch_paths:
                try:
                    img = Image.open(p).convert("RGB")
                    batch_imgs.append(img)
                except Exception:
                    batch_imgs.append(Image.new('RGB', (224, 224)))
            
            inputs = self.processor(images=batch_imgs, return_tensors="pt").to(self.device)
            
            with torch.no_grad():
                # Forward Pass sử dụng Duck-typing
                if hasattr(self.model, "get_image_features"):
                    outputs = self.model.get_image_features(**inputs)
                elif hasattr(self.model, "encode_image"):
                    outputs = self.model.encode_image(**inputs)
                else:
                    outputs = self.model(**inputs)
                    
                tensor = outputs.pooler_output if hasattr(outputs, "pooler_output") else outputs
                vecs = tensor.cpu().numpy()
                
            for v in vecs:
                all_vecs.append(l2_normalize(v))
                
            if (i + bsize) % (bsize * 10) == 0 or i + bsize >= len(img_paths):
                print(f"  Tiến độ: Đã trích xuất {min(i+bsize, len(img_paths))}/{len(img_paths)} ảnh.")
                
        return np.ascontiguousarray(all_vecs, dtype=np.float32)

    def embed_texts(self, texts):
        """
        Trích xuất Vector Văn Bản (cho truy vấn).
        """
        inputs = self.processor(text=texts, return_tensors="pt", padding=True).to(self.device)
        
        # [Bản vá 3] ViCLIP-OT có PhoBERT Tokenizer tạo ra dư biến `token_type_ids`.
        # Cần xóa key này khỏi Dictionary để mô hình không báo lỗi Unrecognized Argument.
        if "token_type_ids" in inputs and not hasattr(self.model.config, "type_vocab_size"):
            del inputs["token_type_ids"]
            
        with torch.no_grad():
            if hasattr(self.model, "get_text_features"):
                outputs = self.model.get_text_features(**inputs)
            elif hasattr(self.model, "encode_text"):
                outputs = self.model.encode_text(**inputs)
            else:
                outputs = self.model(**inputs)
                
            tensor = outputs.pooler_output if hasattr(outputs, "pooler_output") else outputs
            vecs = tensor.cpu().numpy()
            
        return np.ascontiguousarray([l2_normalize(v) for v in vecs], dtype=np.float32)

# %% [markdown]
# ## BƯỚC 4.1: Tiến hành Benchmark 5 Mô Hình SOTA
# 
# Chương trình sẽ chạy thử từng mô hình trong danh sách `CANDIDATE_MODELS` đã cấu hình ở trên 
# bằng một tập ảnh nhỏ để đo thời gian phản hồi (Latency) và kích thước Vector (Dimension).

# %% [code]
benchmark_eval_report = {}
# Chỉ trích xuất số lượng ảnh mẫu để benchmark tốc độ
target_bench_paths = all_source_keyframes[:BENCHMARK_IMAGE_COUNT] if all_source_keyframes else []

print("=== BẮT ĐẦU VÒNG LẮP BENCHMARK CÁC MÔ HÌNH ===")

for m_slug in CANDIDATE_MODELS:
    try:
        runner = MultiModelBenchmark(model_slug=m_slug, device=device)
        
        t0 = time.time()
        img_vecs = runner.embed_image_paths(target_bench_paths, bsize=batch_size)
        t_img = (time.time() - t0) * 1000
        
        t0 = time.time()
        txt_vecs = runner.embed_texts(TEST_QUERIES)
        t_txt = (time.time() - t0) * 1000
        
        benchmark_eval_report[m_slug] = {
            "dimension": int(img_vecs.shape[1]) if len(img_vecs) > 0 else 0,
            "img_batch_latency_ms": round(t_img, 2),
            "text_batch_latency_ms": round(t_txt, 2),
            "l2_norm_verified": True if len(img_vecs) > 0 and np.isclose(np.linalg.norm(img_vecs[0]), 1.0) else False
        }
        print(f"  [HOÀN TẤT] {m_slug} -> Chiều dài Vector: {img_vecs.shape[1] if len(img_vecs)>0 else 'N/A'} | Độ trễ Ảnh: {t_img:.1f}ms")
        
        # Dọn dẹp VRAM: Xóa triệt để biến lưu trữ mô hình và giải phóng GPU Cache
        # Tránh tình trạng tràn bộ nhớ (Out of Memory) khi tải liên tục 5 mô hình lớn.
        del runner
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            
    except Exception as e:
        print(f"  [LỖI] Benchmark thất bại cho mô hình {m_slug}: {e}")

# Xuất báo cáo kết quả dạng JSON
report_json_path = os.path.join(reports_dir, "embedding_comparison_results.json")
with open(report_json_path, "w", encoding="utf-8") as f:
    json.dump(benchmark_eval_report, f, ensure_ascii=False, indent=2)

print(f"\n[INFO] Đã xuất báo cáo Benchmark tại: '{report_json_path}'")
print(json.dumps(benchmark_eval_report, indent=2))

# %% [markdown]
# ## BƯỚC 4.5: Quét Sạch Bộ Nhớ Toàn Cục (RAM/VRAM)
# 
# Một bước kiểm tra và xả bộ nhớ bổ sung để đảm bảo môi trường hoàn toàn trống rỗng 
# và sẵn sàng tài nguyên tối đa cho pha trích xuất thực tế tốn kém VRAM.

# %% [code]
if 'img_vecs' in locals(): del img_vecs
if 'txt_vecs' in locals(): del txt_vecs
gc.collect()
if torch.cuda.is_available(): 
    torch.cuda.empty_cache()
print("[INFO] Dọn dẹp RAM/VRAM tổng quát hoàn tất. Đã sẵn sàng Trích Xuất Dữ Liệu Khủng.")

# %% [markdown]
# ## BƯỚC 5: Trích Xuất Toàn Bộ Dữ Liệu & Khởi Tạo FAISS Index
# 
# Chương trình sẽ sử dụng mô hình được chỉ định trong `CANONICAL_MODEL` để quét 
# qua toàn bộ 200,000 ảnh. Dữ liệu mảng vector thô sẽ được lưu vào ổ đĩa và sau đó 
# nạp vào cấu trúc dữ liệu tối ưu của thư viện FAISS để phục vụ tìm kiếm siêu tốc.

# %% [code]
print("=== BƯỚC 5: TIẾN HÀNH TRÍCH XUẤT THỰC TẾ & KHỞI TẠO FAISS INDEX ===")

if 'all_source_keyframes' not in locals() or len(all_source_keyframes) == 0:
    all_source_keyframes = scan_keyframes(extract_dir)

target_full_paths = all_source_keyframes
print(f"[INFO] Tổng số lượng ảnh cần trích xuất: {len(target_full_paths)}")

try:
    runner = MultiModelBenchmark(model_slug=CANONICAL_MODEL, device=device)
    
    t0 = time.time()
    print(f"[INFO] Đang bơm dữ liệu hình ảnh qua mô hình {CANONICAL_MODEL} (Quá trình này có thể rất lâu)...")
    all_vectors = runner.embed_image_paths(target_full_paths, bsize=batch_size)
    t_total = time.time() - t0
    
    print(f"\n[SUCCESS] Trích xuất Vector hoàn tất. Tổng thời gian xử lý: {t_total:.2f} giây")
    if len(target_full_paths) > 0:
        print(f"  -> Vận tốc xử lý trung bình: {(t_total/len(target_full_paths))*1000:.2f} mili-giây / 1 ảnh")
    
    # 1. Lưu kết quả nguyên gốc (Vector thô)
    npy_path = os.path.join(embeddings_dir, "siglip_full.npy")
    np.save(npy_path, all_vectors)
    print(f"[INFO] Đã kết xuất mảng Raw Vectors (.npy) tại: {npy_path}")
    
    # 2. Xây dựng và lưu cấu trúc tìm kiếm FAISS
    # IndexFlatIP rất hiệu quả khi kết hợp với Vector đã chuẩn hóa L2 (tương đương với Cosine Similarity)
    dim = all_vectors.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(all_vectors)
    
    faiss_path = os.path.join(embeddings_dir, FAISS_INDEX_NAME)
    faiss.write_index(index, faiss_path)
    print(f"[INFO] Bộ chỉ mục (FAISS Index) đã xuất tại: {faiss_path}")
    
    # 3. Kết xuất Metadata (Danh sách file ảnh tương ứng)
    meta_path = os.path.join(embeddings_dir, "vector_map.json")
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(target_full_paths, f, ensure_ascii=False, indent=2)
    print(f"[INFO] Tệp Metadata Map (Khớp Vector - Đường dẫn) đã xuất tại: {meta_path}")

    # Xả bộ nhớ cuối phiên
    del all_vectors
    del index
    del runner
    gc.collect()
    print("[INFO] Quá trình trích xuất và dọn dẹp hậu kỳ đã hoàn tất 100%.")

except Exception as e:
    print(f"[CRITICAL ERROR] Quá trình trích xuất gặp sự cố nghiêm trọng: {e}")
