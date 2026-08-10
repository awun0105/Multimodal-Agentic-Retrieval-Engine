# %% [markdown]
# # Hệ thống Benchmark Trực tiếp trên Kaggle (Direct Kaggle Benchmark)
# 
# **Mô tả:**
# Kịch bản này cung cấp một hệ thống đo lường hiệu năng (Benchmark) quy mô lớn dành cho 24 mô hình 
# Multimodal Embedding (Bao gồm LLM-based, SentenceTransformers, OpenCLIP và Transformers tiêu chuẩn).
# Nó được thiết kế đặc biệt để khai thác tối đa sức mạnh của hệ thống 2 GPU (Dual T4) trên Kaggle Notebooks.
#
# **Cơ chế dữ liệu (Phương pháp Trực tiếp):**
# Quy trình này giả định rằng dữ liệu đầu vào đã được xả nén sẵn, hoặc được cung cấp thông qua các tệp `.zip` 
# lưu trữ trực tiếp trên Kaggle Dataset. Hệ thống sẽ tự động quét, giải mã hình ảnh và đưa vào cấu trúc `DataLoader` 
# đa luồng để truyền dẫn lên GPU.
#
# **Hướng dẫn sử dụng:**
# 1. Liên kết Kaggle Dataset chứa dữ liệu ảnh gốc (đã xả nén) hoặc các tệp `.zip` vào Notebook.
# 2. Tuỳ chỉnh cờ `DEBUG_MODE` (chạy thử với lượng nhỏ dữ liệu) hoặc thiết lập `False` để chạy toàn bộ.
# 3. Kịch bản sẽ tự động đo đạc độ trễ (latency), xử lý lỗi OOM (Out-Of-Memory) và tổng hợp kết quả dưới dạng `.csv`.
# 4. Lưu ý: Ở bước cuối cùng (Bước 6), hệ thống sẽ tiến hành đóng gói dữ liệu thành các tệp zip nhỏ (~10GB) nhằm tránh vi phạm chính sách giới hạn 20GB không gian lưu trữ (Disk Quota) của Kaggle.

# %% [code]
# ==============================================================================
# HẰNG SỐ & CẤU HÌNH TÙY CHỈNH (CẬP NHẬT TẠI ĐÂY)
# ==============================================================================

# CỜ CHẾ ĐỘ GỠ LỖI (DEBUG MODE)
# Kích hoạt True để chạy thử nghiệm với mẫu dữ liệu nhỏ (xác thực luồng thực thi). 
# Đặt False để khởi chạy quy trình đo lường toàn diện (Full Benchmark).
DEBUG_MODE = True

if DEBUG_MODE:
    BENCHMARK_IMAGE_COUNT = 10
    BASE_BATCH_SIZE = 4
    print("[CẢNH BÁO] Hệ thống đang vận hành ở chế độ gỡ lỗi (DEBUG_MODE=True). Số lượng mẫu bị giới hạn: 10.")
else:
    BENCHMARK_IMAGE_COUNT = 1000
    BASE_BATCH_SIZE = 128  # Khai thác tối đa băng thông của 2 GPU T4

# Danh sách 24 mô hình phân chia theo các bảng (Groups)
CANDIDATE_MODELS = [
    # Bảng A: Đa Ngôn Ngữ / Tiếng Việt Tốt
    "jinaai/jina-clip-v2",
    "open_clip:xlm-roberta-base-ViT-B-32:laion5b_s13b_b90k",
    "open_clip:convnext_large_d_320:laion2b_s29b_b131k_ft_soup",
    "open_clip:convnext_base_w:laion2b_s13b_b82k_augreg",
    "open_clip:ViT-B-16-SigLIP-i18n-256:webli",
    "BAAI/AltCLIP",
    
    # Bảng B: Chuẩn Mực Tốc Độ & Cân Bằng
    "google/siglip-base-patch16-224",
    "openai/clip-vit-base-patch32",
    "openai/clip-vit-large-patch14",
    "google/siglip-large-patch16-384",
    "facebook/metaclip-b32-400m",
    "apple/DFN2B-CLIP-ViT-B-16",
    
    # Bảng C: Khổng Lồ & Độ Phân Giải Cao (OpenCLIP/Transformers)
    "google/siglip-so400m-patch14-384",
    "laion/CLIP-ViT-L-14-DataComp.XL-s13B-b90K",
    "open_clip:EVA02-E-14-plus:laion2b_s9b_b144k",
    "apple/DFN5B-CLIP-ViT-H-14",
    "open_clip:ViT-H-14-quickgelu:metaclip_fullcc",
    "laion/CLIP-ViT-g-14-laion2B-s12B-b42K",
    
    # Bảng D: Ứng Cử Viên Mở Rộng
    "wkcn/TinyCLIP-ViT-61M-32-Text-29M-LAION400M",
    "jinaai/jina-clip-v1",
    "open_clip:ViT-L-16-SigLIP-256:webli",  # Đã sửa lỗi dư chữ i18n
    "sentence-transformers/clip-ViT-L-14",
    "Bingsu/clip-vit-base-patch32-ko",
    "wkcn/TinyCLIP-ViT-40M-32-Text-19M-LAION400M",
]

TEST_QUERIES = [
    "người phụ nữ đang thái rau trong bếp",
    "a chef cooking in a modern kitchen",
    "biên tập viên thời sự đang đọc tin tức",
    "news anchor reporting in a broadcast studio"
]

# ==============================================================================

# %% [code]
# Khởi tạo phiên bản transformers mới nhất để tương thích với PyTorch mới trên Kaggle
!pip install -q transformers torch sentencepiece pillow numpy protobuf faiss-cpu pandas
!pip install -q sentence-transformers timm open_clip_torch einops accelerate

# %% [code]
# BƯỚC 2: Khởi tạo Môi trường
import os
import glob
import time
import json
import tarfile
import gc
import numpy as np
import pandas as pd
import torch
import faiss
import shutil
from PIL import Image

IS_KAGGLE = os.path.exists('/kaggle/working')

if IS_KAGGLE:
    print("[INFO] Môi trường hoạt động: Kaggle Notebooks.")
    if os.path.exists("/kaggle/input/aic2025-keyframes"):
        source_aic2025_dir = "/kaggle/input/aic2025-keyframes"
    else:
        source_aic2025_dir = "/kaggle/input" 
    user_output_dir = "/kaggle/working/AIC_Nhat"
else:
    print("[INFO] Đang chạy trong môi trường cục bộ.")
    source_aic2025_dir = os.path.join("..", "data")
    user_output_dir = os.path.join("..", "output_aic_nhat")

device = "cuda" if torch.cuda.is_available() else "cpu"
num_gpus = torch.cuda.device_count() if device == "cuda" else 0
batch_size = BASE_BATCH_SIZE if device == "cuda" else 4
print(f"[INFO] Chế độ xử lý: {device.upper()} ({num_gpus} GPUs) | Kích thước lô (Batch Size): {batch_size}")

reports_dir = os.path.join(user_output_dir, "reports_grand_benchmark")
os.makedirs(reports_dir, exist_ok=True)
extract_dir = "/kaggle/working/extracted_keyframes" if IS_KAGGLE else os.path.join("..", "extracted_keyframes")
os.makedirs(extract_dir, exist_ok=True)

# %% [markdown]
# ## BƯỚC 3: Xử lý I/O và Xả nén Dữ liệu
# 
# Module này chịu trách nhiệm quét đệ quy hệ thống tập tin để tìm kiếm hình ảnh.
# Nếu phát hiện dữ liệu đang ở định dạng nén (`.zip`), nó sẽ tự động xả nén vào phân vùng 
# `/kaggle/working/extracted_keyframes` và xóa tệp gốc để giải phóng không gian lưu trữ.

# %% [code]
# BƯỚC 3: Xử lý và xả nén hình ảnh
import zipfile

def scan_keyframes(root_dir):
    if not os.path.exists(root_dir): return []
    # Quét tất cả các định dạng ảnh phổ biến (bao gồm cả chữ in hoa và in thường)
    exts = ['*.jpg', '*.jpeg', '*.png', '*.webp', '*.JPG', '*.JPEG', '*.PNG']
    files = []
    for ext in exts:
        files.extend(glob.glob(os.path.join(root_dir, "**", ext), recursive=True))
    return sorted(files)

all_source_keyframes = scan_keyframes(extract_dir)
using_cache_needs_zip = False

if len(all_source_keyframes) > 0:
    print(f"[INFO] BƯỚC 3: Dữ liệu Dạng 1 (Cache). Phát hiện ảnh đã giải nén sẵn tại {extract_dir}.")
    print(f"       Bỏ qua quét file ZIP. Sử dụng trực tiếp ảnh từ Cache.")
else:
    zip_files = glob.glob(os.path.join(source_aic2025_dir, "**", "*.zip"), recursive=True)
    if IS_KAGGLE:
        zip_files += glob.glob(os.path.join("/kaggle/working", "**", "*.zip"), recursive=True)
        
    keyframe_zips = [z for z in zip_files if "keyframe" in os.path.basename(z).lower()]

    if len(keyframe_zips) > 0:
        print(f"[INFO] BƯỚC 3: Dữ liệu Dạng 2 (Zips). Phát hiện {len(keyframe_zips)} file ZIP Keyframes.")
        for zf in keyframe_zips:
            folder_name = os.path.splitext(os.path.basename(zf))[0]
            target_dir = os.path.join(extract_dir, folder_name)
            if not os.path.exists(target_dir):
                print(f"  - Đang giải nén: {os.path.basename(zf)}...")
                try:
                    with zipfile.ZipFile(zf, "r") as zip_ref:
                        zip_ref.extractall(target_dir)
                    if IS_KAGGLE and "/kaggle/working" in zf:
                        os.remove(zf)
                except Exception as e:
                    print(f"    [ERROR] Lỗi giải nén {zf}: {e}")
        all_source_keyframes = scan_keyframes(extract_dir)
        using_cache_needs_zip = True
    else:
        print(f"[INFO] BƯỚC 3: Dữ liệu Dạng 1 (Gốc). Kaggle đã giải nén sẵn. Không cần bung zip.")
        all_source_keyframes = scan_keyframes(source_aic2025_dir)
print(f"[INFO] Tổng số ảnh tìm thấy: {len(all_source_keyframes)}")

def l2_normalize(vector: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vector, ord=2)
    return vector / norm if norm > 0 else vector

# %% [code]
# BƯỚC 4: Khởi Tạo Lớp Đóng Gói (ExtendedModelBenchmark)
from transformers import AutoProcessor, AutoModel, CLIPModel, SiglipModel
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    pass
try:
    import open_clip
except ImportError:
    pass

class OpenCLIPImageWrapper(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model
    def forward(self, images):
        return self.model.encode_image(images)

class OpenCLIPTextWrapper(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model
    def forward(self, texts):
        return self.model.encode_text(texts)

class HFImageWrapper(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model
    def forward(self, pixel_values=None, **kwargs):
        if hasattr(self.model, "get_image_features"):
            return self.model.get_image_features(pixel_values=pixel_values, **kwargs)
        elif hasattr(self.model, "encode_image"):
            return self.model.encode_image(pixel_values)
        else:
            return self.model(pixel_values=pixel_values, **kwargs)

class HFTextWrapper(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model
    def forward(self, input_ids=None, attention_mask=None, **kwargs):
        if hasattr(self.model, "get_text_features"):
            return self.model.get_text_features(input_ids=input_ids, attention_mask=attention_mask, **kwargs)
        else:
            return self.model(input_ids=input_ids, attention_mask=attention_mask, **kwargs)

class ExtendedModelBenchmark:
    def __init__(self, model_slug, device="cpu"):
        self.model_slug = model_slug
        self.device = device
        self.model_type = "transformers"
        
        # 1. Phân luồng OpenCLIP
        if "open_clip:" in model_slug or "apple/" in model_slug or "laion/" in model_slug or "eva02" in model_slug or ("metaclip" in model_slug and "b32-400m" not in model_slug):
            self.model_type = "open_clip"
            if "open_clip:" in model_slug:
                parts = model_slug.split(":")
                model_name = parts[1]
                pretrained_tag = parts[2] if len(parts) > 2 else None
                # Ép fp16 cho các model EVA02 khổng lồ để tránh OOM
                prec = "fp16" if "EVA02" in model_name else "fp32"
                self.model, _, self.preprocess = open_clip.create_model_and_transforms(model_name, pretrained=pretrained_tag, precision=prec)
                self.model = self.model.to(device)
                self.tokenizer = open_clip.get_tokenizer(model_name)
            else:
                try:
                    # Tải trực tiếp từ HuggingFace Hub qua OpenCLIP
                    hub_path = f"hf-hub:{model_slug}"
                    prec = "fp16" if "EVA02" in hub_path else "fp32"
                    self.model, _, self.preprocess = open_clip.create_model_and_transforms(hub_path, precision=prec)
                    self.model = self.model.to(device)
                    self.tokenizer = open_clip.get_tokenizer(hub_path)
                except Exception as e:
                    print(f"[WARNING] hf-hub load failed. Fallback to model name. Error: {e}")
                    model_name = model_slug.split("/")[-1]
                    prec = "fp16" if "EVA02" in model_name else "fp32"
                    self.model, _, self.preprocess = open_clip.create_model_and_transforms(model_name, precision=prec)
                    self.model = self.model.to(device)
                    self.tokenizer = open_clip.get_tokenizer(model_name)
            
            if device == "cuda" and torch.cuda.device_count() > 1:
                # Bọc OpenCLIP bằng custom wrapper để ép qua hàm forward(), kích hoạt DataParallel
                self.dp_image_model = torch.nn.DataParallel(OpenCLIPImageWrapper(self.model))
                self.dp_text_model = torch.nn.DataParallel(OpenCLIPTextWrapper(self.model))
            else:
                self.dp_image_model = None
                self.dp_text_model = None
                
        # 2. Phân luồng SentenceTransformers
        elif "sentence-transformers" in model_slug or "VLM2Vec" in model_slug or "M-CLIP" in model_slug or "AltCLIP" in model_slug or "Taiyi" in model_slug:
            self.model_type = "sentence_transformers"
            model_kwargs = {"trust_remote_code": True, "device": self.device}
            self.model = SentenceTransformer(model_slug, **model_kwargs)
            
        # 3. Phân luồng HuggingFace Transformers mặc định
        else:
            self.model_type = "transformers"
            self.processor = AutoProcessor.from_pretrained(model_slug, trust_remote_code=True)
            
            model_kwargs = {"trust_remote_code": True}
            is_jina = "jina" in model_slug.lower()
            
            if is_jina:
                # [JINA SHIELD 1] Tắt Pipeline Parallelism & DataParallel cho Jina-CLIP
                # Khôi phục cấu hình an toàn trên 1 GPU để tránh lỗi mismatch thiết bị (cuda:1 vs cuda:0)
                model_kwargs["torch_dtype"] = torch.bfloat16
                model_kwargs["low_cpu_mem_usage"] = False
                model_kwargs["device_map"] = None
                
                print(f"    [INFO] Khôi phục Jina-CLIP về 1 GPU + ContextManagers + Safe dot_natural_key")
                import contextlib
                import sys
                import transformers.modeling_utils
                import transformers.utils.import_utils
                
                try:
                    import transformers.core_model_loading
                except ImportError:
                    pass
                
                original_context_managers = getattr(transformers.modeling_utils, "ContextManagers", None)
                
                # Bỏ hack chặn accelerate vì Jina không còn bọc DataParallel nữa, tránh lỗi vòng lặp import (circular import)
                
                # [JINA SHIELD 2] Sửa lỗi '< not supported between str and int'
                def safe_dot_natural_key(name):
                    return name
                
                original_dnk_mu = getattr(transformers.modeling_utils, "dot_natural_key", None)
                if original_dnk_mu is not None:
                    transformers.modeling_utils.dot_natural_key = safe_dot_natural_key
                
                original_dnk_cml = None
                if 'transformers.core_model_loading' in sys.modules:
                    original_dnk_cml = getattr(sys.modules['transformers.core_model_loading'], "dot_natural_key", None)
                    if original_dnk_cml is not None:
                        sys.modules['transformers.core_model_loading'].dot_natural_key = safe_dot_natural_key
                
                if original_context_managers is not None:
                    transformers.modeling_utils.ContextManagers = lambda ctx: contextlib.nullcontext()
                
                try:
                    self.model = AutoModel.from_pretrained(model_slug, **model_kwargs)
                finally:
                    if original_context_managers is not None:
                        transformers.modeling_utils.ContextManagers = original_context_managers
                    if original_dnk_mu is not None:
                        transformers.modeling_utils.dot_natural_key = original_dnk_mu
                    if original_dnk_cml is not None:
                        sys.modules['transformers.core_model_loading'].dot_natural_key = original_dnk_cml
            else:
                model_kwargs["low_cpu_mem_usage"] = True
                if "siglip" in model_slug.lower():
                    self.model = SiglipModel.from_pretrained(model_slug, **model_kwargs)
                elif "clip" in model_slug.lower():
                    self.model = CLIPModel.from_pretrained(model_slug, **model_kwargs)
                else:
                    self.model = AutoModel.from_pretrained(model_slug, **model_kwargs)
            
            if self.device == "cuda" and not hasattr(self.model, "hf_device_map"):
                self.model = self.model.to(self.device)
                
            # Đóng gói Multi-GPU cho HuggingFace
            self.image_model = HFImageWrapper(self.model)
            self.text_model = HFTextWrapper(self.model)
            
            if self.device == "cuda" and torch.cuda.device_count() > 1 and not is_jina:
                # [JINA SHIELD 3] Không bọc DataParallel cho Jina-CLIP để tránh xung đột với Pipeline Parallelism
                self.image_model = torch.nn.DataParallel(self.image_model)
                self.text_model = torch.nn.DataParallel(self.text_model)
        
        if hasattr(self.model, "eval"):
            self.model.eval()

    def embed_image_paths(self, img_paths, bsize=32):
        all_vecs = []
        if not img_paths: return np.array([])
        
        # [TỐI ƯU CẤP 3] Sử dụng DataLoader để đọc ảnh đa luồng dưới nền (Async I/O)
        # Giúp CPU đọc ảnh trước, không để GPU phải chờ đợi.
        class ImageDataset(torch.utils.data.Dataset):
            def __init__(self, paths):
                self.paths = paths
            def __len__(self):
                return len(self.paths)
            def __getitem__(self, idx):
                try:
                    with Image.open(self.paths[idx]) as img:
                        return img.convert("RGB")
                except Exception:
                    return Image.new('RGB', (224, 224))
                    
        def pil_collate(batch):
            return batch
            
        dataset = ImageDataset(img_paths)
        num_workers = 2 if self.device == "cuda" else 0
        dataloader = torch.utils.data.DataLoader(
            dataset, batch_size=bsize, num_workers=num_workers, collate_fn=pil_collate, pin_memory=False
        )
            
        for batch_imgs in dataloader:
            with torch.no_grad():
                if self.model_type == "sentence_transformers":
                    vecs = self.model.encode(batch_imgs, convert_to_numpy=True)
                elif self.model_type == "open_clip":
                    processed_imgs = torch.stack([self.preprocess(img) for img in batch_imgs]).to(self.device)
                    actual_model = self.model
                    
                    # [EVA02 SHIELD] Ép kiểu ảnh về cùng dtype với model (fp16)
                    try:
                        model_dtype = next(actual_model.parameters()).dtype
                        processed_imgs = processed_imgs.to(dtype=model_dtype)
                    except StopIteration:
                        pass
                        
                    if getattr(self, "dp_image_model", None) is not None:
                        vecs = self.dp_image_model(processed_imgs).cpu().float().numpy()
                    else:
                        vecs = actual_model.encode_image(processed_imgs).cpu().float().numpy()
                else:
                    target_device = self.model.module.device if hasattr(self.model, "module") and hasattr(self.model.module, "device") else (self.model.device if hasattr(self.model, "device") else self.device)
                    inputs = self.processor(images=batch_imgs, return_tensors="pt").to(target_device)
                    
                    outputs = self.image_model(**inputs)
                    
                    if isinstance(outputs, torch.Tensor):
                        tensor = outputs
                    else:
                        tensor = outputs.pooler_output if hasattr(outputs, "pooler_output") else (outputs[0] if isinstance(outputs, tuple) or isinstance(outputs, list) or hasattr(outputs, 'keys') else outputs)
                    
                    # Handle some models that return a dict where we want text_embeds/image_embeds
                    if hasattr(outputs, 'image_embeds') and outputs.image_embeds is not None:
                        tensor = outputs.image_embeds
                        
                    vecs = tensor.cpu().float().numpy()
                
            for v in vecs:
                all_vecs.append(l2_normalize(v))
                
        return np.ascontiguousarray(all_vecs, dtype=np.float32)

    def embed_texts(self, texts):
        with torch.no_grad():
            if self.model_type == "sentence_transformers":
                vecs = self.model.encode(texts, convert_to_numpy=True)
            elif self.model_type == "open_clip":
                text_tokens = self.tokenizer(texts).to(self.device)
                actual_model = self.model
                
                if getattr(self, "dp_text_model", None) is not None:
                    vecs = self.dp_text_model(text_tokens).cpu().float().numpy()
                else:
                    vecs = actual_model.encode_text(text_tokens).cpu().numpy()
            else:
                target_device = self.model.module.device if hasattr(self.model, "module") and hasattr(self.model.module, "device") else (self.model.device if hasattr(self.model, "device") else self.device)
                inputs = self.processor(text=texts, return_tensors="pt", padding=True, truncation=True).to(target_device)
                
                outputs = self.text_model(**inputs)
                
                if isinstance(outputs, torch.Tensor):
                    tensor = outputs
                else:
                    tensor = outputs.pooler_output if hasattr(outputs, "pooler_output") else (outputs[0] if isinstance(outputs, tuple) or isinstance(outputs, list) or hasattr(outputs, 'keys') else outputs)
                    
                if hasattr(outputs, 'text_embeds') and outputs.text_embeds is not None:
                    tensor = outputs.text_embeds
                    
                vecs = tensor.cpu().float().numpy()
                
        return np.ascontiguousarray([l2_normalize(v) for v in vecs], dtype=np.float32)

# %% [code]
# BƯỚC 5: Thực thi Benchmark và Xuất CSV
results = []
target_bench_paths = all_source_keyframes[:BENCHMARK_IMAGE_COUNT] if all_source_keyframes else []

print(f"=== BẮT ĐẦU GRAND BENCHMARK ({len(CANDIDATE_MODELS)} MÔ HÌNH) ===")

for idx, m_slug in enumerate(CANDIDATE_MODELS):
    print(f"\n[{idx+1}/{len(CANDIDATE_MODELS)}] Đang xử lý: {m_slug}")
    try:
        runner = ExtendedModelBenchmark(model_slug=m_slug, device=device)
        
        # Điều chỉnh batch_size cho các model khổng lồ để tránh OOM
        current_bsize = batch_size
        if "EVA02-E" in m_slug:
            current_bsize = 16
            print(f"    [INFO] Giảm batch_size = {current_bsize} cho EVA02-E để tránh OOM.")
        elif "jina-clip-v2" in m_slug.lower():
            current_bsize = 16
            print(f"    [INFO] Giảm batch_size = {current_bsize} cho Jina-CLIP v2 (model này rất lớn).")
            
        # Đo tốc độ Image
        t0 = time.time()
        img_vecs = runner.embed_image_paths(target_bench_paths, bsize=current_bsize)
        t_img = (time.time() - t0) * 1000
        
        # Đo tốc độ Text
        t0 = time.time()
        txt_vecs = runner.embed_texts(TEST_QUERIES)
        t_txt = (time.time() - t0) * 1000
        
        dim = int(img_vecs.shape[1]) if len(img_vecs) > 0 else 0
        
        results.append({
            "Model": m_slug,
            "Architecture": runner.model_type,
            "Dimension": dim,
            "Image Batch (ms)": round(t_img, 2),
            "Text Batch (ms)": round(t_txt, 2),
            "Status": "Success"
        })
        print(f"  [HOÀN TẤT] Kích thước Vector: {dim} | Image: {t_img:.1f}ms | Text: {t_txt:.1f}ms")
        
        # Clean up
        if hasattr(runner, 'model'):
            runner.model = runner.model.cpu()
            del runner.model
        del runner
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            
    except Exception as e:
        print(f"  [LỖI NGHIÊM TRỌNG] {e}")
        results.append({
            "Model": m_slug,
            "Architecture": "Error",
            "Dimension": 0,
            "Image Batch (ms)": 0,
            "Text Batch (ms)": 0,
            "Status": f"Failed: {str(e)[:50]}..."
        })
        if 'runner' in locals():
            if hasattr(runner, 'model'):
                runner.model = runner.model.cpu()
                del runner.model
            del runner
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

df_results = pd.DataFrame(results)
csv_path = os.path.join(reports_dir, "grand_benchmark_results.csv")
df_results.to_csv(csv_path, index=False)

print(f"\n[INFO] Đã xuất báo cáo CSV tại: '{csv_path}'")
display(df_results) if 'display' in globals() else print(df_results)

# %% [markdown]
# ## BƯỚC 6: Chiến lược Đóng gói Dữ liệu Phân mảnh (Chunking Strategy)
# 
# Do chính sách bảo vệ tài nguyên của Kaggle giới hạn phân vùng `/kaggle/working` ở mức 20GB, 
# việc lưu trữ toàn bộ tập dữ liệu (có thể lên tới 40GB) sẽ dẫn đến lỗi `Disk Quota Exceeded`.
# Module này áp dụng chiến lược "Chia để trị", chia nhỏ tập dữ liệu thành nhiều phân mảnh (`NUM_CHUNKS`), 
# mỗi phân mảnh đảm bảo duy trì dung lượng dưới ngưỡng 19.5GB.
#
# **Quy trình:** Người dùng chạy kịch bản này nhiều lần, mỗi lần thay đổi biến `ZIP_CHUNK_INDEX` 
# tương ứng để kết xuất và tải xuống tuần tự từng phân mảnh dữ liệu.

# %% [code]
# ==============================================================================
# BƯỚC 6: TỰ ĐỘNG NÉN CACHE DỮ LIỆU ĐỂ LƯU TRỮ (CHIẾN LƯỢC PHÂN MẢNH TRÁNH QUÁ TẢI KAGGLE)
# ==============================================================================
import zipfile
import math

# CẤU HÌNH PHÂN MẢNH DỮ LIỆU NHẰM TUÂN THỦ GIỚI HẠN 20GB CỦA KAGGLE
FORCE_CREATE_ZIP_CACHE = True
NUM_CHUNKS = 2       # Phân tách tập dữ liệu thành 2 luồng (Mỗi luồng ~10GB - Đảm bảo an toàn bộ nhớ)
ZIP_CHUNK_INDEX = 0  # CHU KỲ 1: Đặt 0 để kết xuất Phân mảnh 1. CHU KỲ 2: Đặt 1 để kết xuất Phân mảnh 2.

print(f"\n[TIẾN TRÌNH] Đang tiến hành đóng gói dữ liệu (Phân mảnh {ZIP_CHUNK_INDEX+1}/{NUM_CHUNKS}) nhằm tối ưu hóa giới hạn ổ cứng.")
if FORCE_CREATE_ZIP_CACHE and len(all_source_keyframes) > 0:
    chunk_size = math.ceil(len(all_source_keyframes) / NUM_CHUNKS)
    start_idx = ZIP_CHUNK_INDEX * chunk_size
    end_idx = min((ZIP_CHUNK_INDEX + 1) * chunk_size, len(all_source_keyframes))
    
    images_to_zip = all_source_keyframes[start_idx:end_idx]
    
    cache_zip_path = f"/kaggle/working/cached_keyframes_part{ZIP_CHUNK_INDEX+1}.zip" if IS_KAGGLE else os.path.join(user_output_dir, f"cached_keyframes_part{ZIP_CHUNK_INDEX+1}.zip")
    
    print(f"[INFO] Tổng số ảnh: {len(all_source_keyframes)} | Đang nén từ ảnh số {start_idx} đến {end_idx} ({len(images_to_zip)} ảnh)")
    print(f"[INFO] File đầu ra sẽ lưu tại: {cache_zip_path}")
    
    try:
        # Sử dụng thư viện zipfile để kiểm soát từng file ảnh
        with zipfile.ZipFile(cache_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for img_path in images_to_zip:
                # Lưu vào file zip với cấu trúc: <Tên Thư Mục Cha>/<Tên File Ảnh>
                parent_dir_name = os.path.basename(os.path.dirname(img_path))
                img_name = os.path.basename(img_path)
                arcname = f"{parent_dir_name}/{img_name}"
                zipf.write(img_path, arcname)
                
        print(f"[HOÀN TẤT] Đã tạo file cache thành công: {cache_zip_path}")
        print(f"👉 [MẸO KAGGLE]: Hãy tải file này về hoặc Save Version (New Dataset). Sau đó sửa ZIP_CHUNK_INDEX = 1 và chạy lại để lấy nửa còn lại!")
    except Exception as e:
        print(f"[LỖI NGHIÊM TRỌNG] Không thể tạo file zip cache: {e}")
else:
    print(f"[LƯU Ý] Không có ảnh nào để nén hoặc tính năng Force Zip bị tắt.")
