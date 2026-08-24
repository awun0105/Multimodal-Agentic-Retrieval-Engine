# %% [markdown]
# # Hệ thống Benchmark Nâng cao qua Virtual Cache (.blob) (Kaggle Environment)
# 
# **Mô tả:**
# Kịch bản này là phiên bản nâng cấp hoàn toàn (Advanced) của Grand Benchmark. Nó được thiết kế 
# để vượt qua giới hạn thắt cổ chai về I/O (Input/Output bottleneck) và dung lượng lưu trữ cực kỳ 
# khắt khe của Kaggle (tối đa 20GB).
#
# **Cơ chế Dữ liệu (Phương pháp Virtual Cache):**
# Thay vì xả nén hàng ngàn tập tin ảnh rời rạc ra phân vùng đĩa cứng cục bộ, kiến trúc này 
# sử dụng một tệp lưu trữ duy nhất (`.blob`). Trình tải dữ liệu (`DataLoader`) sẽ truy cập ngẫu nhiên 
# vào bên trong cấu trúc ZIP này, đọc luồng nhị phân (binary stream) và truyền thẳng lên VRAM của GPU 
# mà không cần thông qua bước ghi/đọc tạm trên ổ đĩa mềm.
#
# **Hướng dẫn sử dụng:**
# 1. Đảm bảo bạn đã sử dụng kịch bản `colab_data_prep.ipynb` trên Google Colab để đóng gói tập dữ liệu gốc thành một tệp `.blob`.
# 2. Đăng tải tệp `.blob` này lên nền tảng Kaggle dưới dạng một Dataset mới.
# 3. Liên kết Dataset chứa tệp `.blob` vào Notebook này và khởi chạy toàn bộ quy trình.
# 4. Lưu ý: Do đặc thù tối ưu hóa này, bước đóng gói phân mảnh (Chunking - Bước 6) đã được vô hiệu hóa hoàn toàn vì không còn cần thiết.

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

# %% [code]
# %% [markdown]
# ## BƯỚC 3: Kiến trúc Đọc Dữ liệu Trực tiếp (Virtual Cache Reader)
# 
# Module này bỏ qua hoàn toàn cơ chế quét và xả nén `.zip` truyền thống.
# Thay vào đó, nó định vị tệp `.blob` được cung cấp trong Kaggle Dataset, thiết lập 
# luồng đọc ảo (Virtual Reader) và trích xuất lập chỉ mục các tệp hình ảnh được mã hóa bên trong.

# %% [code]
# BƯỚC 3: TÌM VÀ ĐỌC TỆP VIRTUAL CACHE (.blob) THAY VÌ XẢ NÉN
import zipfile
import io

blob_files = glob.glob(os.path.join(source_aic2025_dir, "**", "*.blob"), recursive=True)
if IS_KAGGLE:
    blob_files += glob.glob(os.path.join("/kaggle/working", "**", "*.blob"), recursive=True)
    blob_files += glob.glob(os.path.join("/kaggle/input", "**", "*.blob"), recursive=True)

if len(blob_files) == 0:
    print("[CẢNH BÁO] Không tìm thấy file .blob nào. Hãy upload dataset chứa file .blob lên Kaggle!")
    TARGET_BLOB_PATH = ""
    all_source_keyframes = []
else:
    TARGET_BLOB_PATH = blob_files[0]
    print(f"[INFO] BƯỚC 3: Phát hiện Virtual Cache: {TARGET_BLOB_PATH}")
    print("[INFO] Sẽ load ảnh TRỰC TIẾP từ file blob lên GPU, bỏ qua bước giải nén ổ cứng!")

    # Lấy danh sách ảnh bên trong file blob (không giải nén)
    all_source_keyframes = []
    try:
        with zipfile.ZipFile(TARGET_BLOB_PATH, 'r') as zf:
            # Lọc ra những file là ảnh (không lấy thư mục)
            exts = ('.jpg', '.jpeg', '.png', '.webp')
            all_source_keyframes = [info.filename for info in zf.infolist() if info.filename.lower().endswith(exts)]
    except Exception as e:
        print(f"[LỖI] Không thể đọc file blob: {e}")

    all_source_keyframes = sorted(all_source_keyframes)
    print(f"[INFO] Tổng số ảnh tìm thấy trong Blob: {len(all_source_keyframes)}")

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
        class BlobImageDataset(torch.utils.data.Dataset):
            def __init__(self, blob_path, image_names):
                self.blob_path = blob_path
                self.image_names = image_names
                self.zip_file = None
                
            def __len__(self):
                return len(self.image_names)
                
            def __getitem__(self, idx):
                if self.zip_file is None:
                    # Lazy loading: Khởi tạo zipfile reader độc lập cho mỗi Data Worker
                    self.zip_file = zipfile.ZipFile(self.blob_path, 'r')
                try:
                    # Đọc file nhị phân từ zip và ném thẳng lên RAM (không cần file tạm trên ổ cứng)
                    img_data = self.zip_file.read(self.image_names[idx])
                    with Image.open(io.BytesIO(img_data)) as img:
                        return img.convert("RGB")
                except Exception:
                    return Image.new('RGB', (224, 224))
                    
        def pil_collate(batch):
            return batch
            
        dataset = BlobImageDataset(TARGET_BLOB_PATH, img_paths)
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
# ## BƯỚC 6: Chiến lược Đóng gói Dữ liệu Phân mảnh (Đã Vô hiệu hóa)
# 
# Trong phiên bản Direct Benchmark truyền thống, bước này có nhiệm vụ chia nhỏ dữ liệu thành nhiều 
# phân mảnh dưới 20GB. Tuy nhiên, nhờ vào cơ chế Virtual Cache (.blob), giới hạn I/O đã được loại bỏ.
# Quy trình nén và lưu trữ lại dữ liệu không còn cần thiết.

# %% [code]
# ==============================================================================
# BƯỚC 6: TỰ ĐỘNG NÉN CACHE DỮ LIỆU ĐỂ LƯU TRỮ (ĐÃ VÔ HIỆU HÓA)
# ==============================================================================
print("\n[THÔNG TIN] BỎ QUA QUY TRÌNH NÉN CACHE DO HỆ THỐNG ĐANG SỬ DỤNG VIRTUAL CACHE (.BLOB)")
print("Cấu trúc lưu trữ đã đạt mức độ tối ưu cao nhất. Tiến trình Benchmark hoàn tất thành công!")

