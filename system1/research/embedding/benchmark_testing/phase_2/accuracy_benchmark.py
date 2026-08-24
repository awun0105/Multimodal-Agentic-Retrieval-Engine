# %% [markdown]
# # Kaggle / Colab: Danh Gia Do Chinh Xac Retrieval Tren Top 10 Mo Hinh Base (Phase 2)
#
# ## 1. Muc Dich va Tong Quan
# Kich ban nay thuc hien do luong thuc nghiem chat luong truyen xuat (Zero-shot Video Retrieval Accuracy)
# tren **Top 10 Mo hinh phan khuc Base-tier** (~86M - 150M tham so) nham giai quyet dut diem bai toan kien truc cot loi:
# - **Truong phai Dich thuat (Translate-then-Search):** Duyen cau truy van Tieng Anh qua cac sieu mo hinh Base Tieng Anh (`SigLIP-Base`, `MetaCLIP`, `DFN2B`, `CLIP-Base`, `ConvNeXt`).
# - **Truong phai Truc tiep (Native Multilingual):** Dung truc tiep cau truy van Tieng Viet qua cac mo hinh da ngon ngu (`SigLIP-i18n`, `SigLIP-Large-i18n`, `Jina-CLIP-v1`, `AltCLIP`, `XLM-R`).
#
# **Dac diem ky thuat noi bat:**
# - **Virtual Cache Reader (.blob):** Doc luong nhi phan truc tiep tu tep `cached_keyframes.blob` tren Kaggle Datasets, khong can xa nen anh ra o cung, triet tieu hoan toan loi tran dia 20GB.
# - **Tu dong Nhan dien Phan cung:** Tự động điều chỉnh Batch Size tối ưu cho Dual GPU T4 (128), Single GPU (64) hoặc CPU (4).
#
# ---
#
# ## 2. Huong Dan Thao Tac Tren Kaggle (Quick Start)
#
# ### Buoc A: Khoi tao va Import Notebook
# 1. Truy cap https://www.kaggle.com/code -> Chon "New Notebook".
# 2. Tren menu Notebook: Chon **File -> Import Notebook** -> Tai tep `accuracy_benchmark.ipynb` len.
#
# ### Buoc B: Cau hinh Session Options (Cot ben phai)
# - **Accelerator:** Chon **GPU T4 x2** (Dual T4) hoac GPU P100.
# - **Internet:** Bat **Internet on** (de tai trong so mo hinh tu HuggingFace / OpenCLIP).
#
# ### Buoc C: Lien ket Dataset Virtual Cache (.blob)
# 1. Nhan nut **+ Add Input** o goc tren ben phai.
# 2. Tim kiem dataset cua ban: `nhathoang42/aic2025-keyframes-blob` (hoac slug dataset chua tep `.blob`).
# 3. Nhan bieu tuong (+) de gan dataset vao notebook.
#
# ### Buoc D: Thiet lap Tham so va Chay
# - **Lan chay 1 (Debug Run):** Giu nguyen `DEBUG_MODE = True` o Cell 1 de chay thu voi 10 mau kiem tra tinh toan ven.
# - **Lan chay 2 (Full Benchmark):** Chuyen sang `DEBUG_MODE = False` va bam **Run All** (Ctrl + F9) de do dac toan dien tren 1.000 mau.
#
# ---
#
# ## 3. Ket Qua Dau Ra & Chi So Danh Gia
# Sau khi hoan tat, cac tep bao cao se duoc tu dong xuat ra tai `/kaggle/working`:
# 1. `phase2_accuracy_report.md`: Bao cao Markdown tong hop bang so sanh chi tiet giua 2 ngon ngu EN va VI.
# 2. `phase2_accuracy_metrics.json`: Du lieu chi so dang JSON phuc vu tich hop pipeline.
# 3. `phase2_accuracy_metrics.csv`: Bang thong ke chi so theo dang bang tinh.
#
# **Cac chi so nghiep vu do luong:**
# - `Recall@1`, `Recall@5`, `Recall@10`: Phan tram so lan anh dung xuat hien trong Top K ket qua tra ve.
# - `MRR (Mean Reciprocal Rank)`: Thu hang uu tien trung binh cua ket qua dung (cang gan 1.0 cang tot).
# - `Cosine Margin`: Do phan tach giua diem so anh dung va anh sai gan nhat (Hard Negative) de chong hallucination.

# %% [code]
# ==============================================================================
# BUOC 0: CAI DAT THU VIEN BO TRO (CHO KAGGLE / COLAB)
# ==============================================================================
!pip install -q transformers torch sentencepiece pillow numpy protobuf faiss-cpu pandas
!pip install -q sentence-transformers timm open_clip_torch einops accelerate multilingual-clip

# %% [code]
# ==============================================================================
# 1. HẰNG SỐ & CẤU HÌNH BENCHMARK
# ==============================================================================
import os
import sys
import json
import time
import gc
import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from PIL import Image

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# %% [code]
# ==============================================================================
# 1.1. NHẬN DIỆN VÀ PHÂN TẦNG CẤU HÌNH PHẦN CỨNG (HARDWARE PROFILE)
# ==============================================================================
def get_hardware_profile():
    """
    Tự động quét cấu hình phần cứng (Dual T4, Single GPU, TPU hoặc CPU) và khuyến nghị Batch Size.
    """
    profile = {
        "device": "cpu",
        "name": "Generic CPU",
        "num_units": 1,
        "vram_gb": 0.0,
        "tier": "Tier 3 (Local CPU)",
        "recommended_batch_size": 4
    }
    
    if torch.cuda.is_available():
        gpu_count = torch.cuda.device_count()
        gpu_name = torch.cuda.get_device_name(0)
        vram_per_gpu = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        total_vram = vram_per_gpu * gpu_count
        
        profile["device"] = "cuda"
        profile["name"] = gpu_name
        profile["num_units"] = gpu_count
        profile["vram_gb"] = round(total_vram, 2)
        
        if gpu_count >= 2 and "T4" in gpu_name:
            profile["tier"] = "Tier 1: Kaggle Dual T4 (Benchmark Engine)"
            profile["recommended_batch_size"] = 128
        elif "T4" in gpu_name or "P100" in gpu_name:
            profile["tier"] = "Tier 1: Single Cloud GPU (T4/P100)"
            profile["recommended_batch_size"] = 64
        else:
            profile["tier"] = f"GPU Acceleration ({gpu_name})"
            profile["recommended_batch_size"] = 64
            
    print(f"[*] Cấu hình phần cứng: {profile['name']} x {profile['num_units']} ({profile['vram_gb']} GB VRAM)")
    print(f"[*] Phân tầng điện toán: {profile['tier']}")
    print(f"[*] Batch Size khuyến nghị: {profile['recommended_batch_size']}")
    return profile

HW_PROFILE = get_hardware_profile()
DEVICE = HW_PROFILE["device"]

# CỜ CHẾ ĐỘ GỠ LỖI (DEBUG MODE)
DEBUG_MODE = True

if DEBUG_MODE:
    BENCHMARK_SAMPLES = 10
    BASE_BATCH_SIZE = 4
    print("[CẢNH BÁO] Chế độ gỡ lỗi đang BẬT (DEBUG_MODE=True). Đang giới hạn 10 mẫu kiểm thử.")
else:
    BENCHMARK_SAMPLES = 1000
    BASE_BATCH_SIZE = HW_PROFILE["recommended_batch_size"]

# Danh sách 14 Mô Hình Tham Gia Benchmark Phase 2 (Chuẩn Hóa & Kiểm Định 100%)
CANDIDATE_MODELS_PHASE2 = {
    # Nhóm 1: Phe Chuyên biệt Thuần Tiếng Việt (Vietnamese Dedicated Models)
    "Vietnamese_Dedicated_Group": [
        {"name": "minhnguyent546/ViCLIP-OT", "dim": 512},
        {"name": "minhnguyent546/ViSigLIP-OT", "dim": 768},
    ],
    # Nhóm 2: Phe Multilingual-CLIP Chuyên Ngữ (M-CLIP XLM-RoBERTa Large)
    "M_CLIP_Vietnamese_Group": [
        {"name": "M-CLIP/XLM-Roberta-Large-Vit-B-32", "dim": 512},
        {"name": "M-CLIP/XLM-Roberta-Large-Vit-L-14", "dim": 768},
    ],
    # Nhóm 3: Phe Đa ngôn ngữ SOTA Hỗ trợ Tiếng Việt (Global Multilingual Models)
    "Multilingual_SOTA_Group": [
        {"name": "sentence-transformers/clip-ViT-B-32-multilingual-v1", "dim": 512},
        {"name": "BAAI/AltCLIP", "dim": 768},
        {"name": "open_clip:ViT-B-16-SigLIP-i18n-256:webli", "dim": 768},
        {"name": "open_clip:ViT-L-16-SigLIP-256:webli", "dim": 1024},
        {"name": "jinaai/jina-clip-v1", "dim": 768},
        {"name": "open_clip:xlm-roberta-base-ViT-B-32:laion5b_s13b_b90k", "dim": 512},
    ],
    # Nhóm 4: Phe Dịch thuật Quốc tế (English Top SOTA Baselines - Đối Chiếu)
    "English_Translate_Group": [
        {"name": "google/siglip-base-patch16-224", "dim": 768},
        {"name": "openai/clip-vit-base-patch32", "dim": 512},
        {"name": "facebook/metaclip-b32-400m", "dim": 512},
        {"name": "apple/DFN2B-CLIP-ViT-B-16", "dim": 512},
        {"name": "open_clip:convnext_base_w:laion2b_s13b_b82k_augreg", "dim": 640},
    ]
}

# %% [code]
# ==============================================================================
# 2. HÀM TÍNH TOÁN CHỈ SỐ METRICS
# ==============================================================================
def compute_retrieval_metrics(similarity_matrix: np.ndarray) -> dict:
    """
    Tính toán Recall@1, Recall@5, Recall@10, MRR, và Cosine Margin từ ma trận tương đồng (N x N).
    Giả định phần tử đúng của truy vấn thứ i là ảnh thứ i (True match at diagonal i == j).
    """
    similarity_matrix = np.nan_to_num(similarity_matrix, nan=0.0, posinf=1.0, neginf=-1.0)
    N = similarity_matrix.shape[0]
    ranks = []
    margins = []
    
    r1_count = 0
    r5_count = 0
    r10_count = 0
    
    for i in range(N):
        sim_scores = similarity_matrix[i]
        true_score = sim_scores[i]
        
        # Sắp xếp chỉ số theo độ tương đồng giảm dần
        sorted_indices = np.argsort(-sim_scores)
        rank = np.where(sorted_indices == i)[0][0] + 1  # 1-indexed
        ranks.append(rank)
        
        if rank <= 1:
            r1_count += 1
        if rank <= 5:
            r5_count += 1
        if rank <= 10:
            r10_count += 1
            
        # Tính Cosine Margin: chênh lệch giữa điểm đúng và điểm sai cao nhất (Hard Negative)
        other_scores = np.delete(sim_scores, i)
        max_negative_score = np.max(other_scores) if len(other_scores) > 0 else 0.0
        margins.append(float(true_score - max_negative_score))
        
    mrr = float(np.nan_to_num(np.mean([1.0 / r for r in ranks]), nan=0.0))
    avg_margin = float(np.nan_to_num(np.mean(margins), nan=0.0))
    
    return {
        "samples_count": N,
        "recall@1": round(r1_count / N * 100, 2),
        "recall@5": round(r5_count / N * 100, 2),
        "recall@10": round(r10_count / N * 100, 2),
        "mrr": round(mrr, 4),
        "cosine_margin": round(avg_margin, 4)
    }

# %% [code]
# ==============================================================================
# 3. BỘ NẠP MÔ HÌNH THỐNG NHẤT (CHUẨN HÓA ĐA LUỒNG & CHỐNG LỖI METRIC/DP)
# ==============================================================================
import contextlib
import transformers.modeling_utils

class BenchmarkModelWrapper:
    def __init__(self, model_info: dict, device: str = "cuda"):
        self.name = model_info["name"]
        self.dim = model_info.get("dim", 512)
        
        # Dual-GPU Tower Sharding: Tách riêng nhánh Vision Tower sang GPU 0 và Text Tower sang GPU 1
        num_gpus = torch.cuda.device_count() if torch.cuda.is_available() else 0
        if num_gpus > 1:
            self.device_vision = torch.device("cuda:0")
            self.device_text = torch.device("cuda:1")
            self.is_dual_gpu = True
            print(f"[*] Kích hoạt Dual-GPU Tower Sharding: Vision Tower [cuda:0] | Text Tower [cuda:1]")
        elif num_gpus == 1:
            self.device_vision = torch.device("cuda:0")
            self.device_text = torch.device("cuda:0")
            self.is_dual_gpu = False
        else:
            self.device_vision = torch.device("cpu")
            self.device_text = torch.device("cpu")
            self.is_dual_gpu = False

        self.model_type = "transformers"
        self.model = None
        self.vision_model = None
        self.text_model = None
        self.linear_head = None
        self.processor = None
        self.tokenizer = None
        self.preprocess = None
        self._load()

    def _load(self):
        print(f"[+] Đang khởi tạo mô hình: {self.name}...")
        is_jina = "jina" in self.name.lower()
        try:
            # 1. Phân luồng OpenCLIP (Checkpoint Apple DFN & các biến thể open_clip)
            if "open_clip:" in self.name or "apple/" in self.name or "laion/" in self.name:
                import open_clip
                self.model_type = "open_clip"
                if "open_clip:" in self.name:
                    parts = self.name.split(":")
                    model_arch = parts[1]
                    pretrained = parts[2] if len(parts) > 2 else None
                    self.vision_model, _, self.preprocess = open_clip.create_model_and_transforms(
                        model_arch, pretrained=pretrained, device=self.device_vision
                    )
                    self.tokenizer = open_clip.get_tokenizer(model_arch)
                    if self.is_dual_gpu:
                        self.text_model, _, _ = open_clip.create_model_and_transforms(
                            model_arch, pretrained=pretrained, device=self.device_text
                        )
                        self.text_model.eval()
                    else:
                        self.text_model = self.vision_model
                else:
                    hub_path = f"hf-hub:{self.name}"
                    self.vision_model, _, self.preprocess = open_clip.create_model_and_transforms(
                        hub_path, device=self.device_vision
                    )
                    self.tokenizer = open_clip.get_tokenizer(hub_path)
                    if self.is_dual_gpu:
                        self.text_model, _, _ = open_clip.create_model_and_transforms(
                            hub_path, device=self.device_text
                        )
                        self.text_model.eval()
                    else:
                        self.text_model = self.vision_model
                self.vision_model.eval()

            # 2. Phân luồng SBERT Multilingual CLIP (Ánh xạ Text-Only SBERT sang Vision Tower OpenAI CLIP)
            elif "sentence-transformers/clip-ViT" in self.name or ("clip-ViT" in self.name and "multilingual" in self.name):
                import open_clip
                from sentence_transformers import SentenceTransformer
                self.model_type = "sbert_multilingual_clip"
                vision_arch = "ViT-L-14" if "Vit-L-14" in self.name or "ViT-L-14" in self.name else "ViT-B-32"
                self.vision_model, _, self.preprocess = open_clip.create_model_and_transforms(
                    vision_arch, pretrained="openai", device=self.device_vision
                )
                self.vision_model.eval()
                self.text_model = SentenceTransformer(self.name, device=str(self.device_text))

            # 3. Phân luồng M-CLIP (Nạp trực tiếp XLM-RoBERTa Large + Projection Head cho Tiếng Việt)
            elif "m-clip" in self.name.lower() or "multilingual-clip" in self.name.lower():
                import open_clip
                from transformers import AutoTokenizer, XLMRobertaModel
                import huggingface_hub
                from safetensors.torch import load_file
                
                self.model_type = "m_clip"
                vision_arch = "ViT-L-14" if "Vit-L-14" in self.name or "ViT-L-14" in self.name else "ViT-B-32"
                self.vision_model, _, self.preprocess = open_clip.create_model_and_transforms(
                    vision_arch, pretrained="openai", device=self.device_vision
                )
                self.vision_model.eval()
                
                # Nạp Text Tower (XLM-RoBERTa Large) trên GPU Text (cuda:1)
                self.tokenizer = AutoTokenizer.from_pretrained(self.name)
                self.text_model = XLMRobertaModel.from_pretrained("xlm-roberta-large").to(self.device_text).eval()
                
                # Tải trọng số projection head từ checkpoint
                try:
                    weights_path = huggingface_hub.hf_hub_download(repo_id=self.name, filename="model.safetensors")
                    state_dict = load_file(weights_path)
                except Exception:
                    weights_path = huggingface_hub.hf_hub_download(repo_id=self.name, filename="pytorch_model.bin")
                    state_dict = torch.load(weights_path, map_location="cpu")
                    
                tf_dict = {}
                head_w = None
                head_b = None
                for k, v in state_dict.items():
                    if k.startswith("transformer."):
                        tf_dict[k[len("transformer."):]] = v
                    elif "LinearHead.weight" in k or "linear_head.weight" in k:
                        head_w = v
                    elif "LinearHead.bias" in k or "linear_head.bias" in k:
                        head_b = v
                        
                if tf_dict:
                    self.text_model.load_state_dict(tf_dict, strict=False)
                    
                out_dim = 768 if "Vit-L-14" in self.name or "ViT-L-14" in self.name else 512
                self.linear_head = torch.nn.Linear(1024, out_dim).to(self.device_text).eval()
                if head_w is not None:
                    self.linear_head.weight.data.copy_(head_w)
                if head_b is not None:
                    self.linear_head.bias.data.copy_(head_b)

            # 4. Phân luồng Mô hình Chuyên biệt Thuần Tiếng Việt (ViCLIP-OT / ViSigLIP-OT)
            elif "viclip" in self.name.lower() or "visiglip" in self.name.lower():
                from transformers import AutoModel, AutoProcessor
                self.model_type = "viclip_ot"
                try:
                    self.processor = AutoProcessor.from_pretrained(self.name, trust_remote_code=True)
                except Exception:
                    self.processor = None
                
                self.vision_model = AutoModel.from_pretrained(
                    self.name,
                    trust_remote_code=True,
                    low_cpu_mem_usage=False,
                    torch_dtype=torch.float32
                ).to(self.device_vision).eval()
                
                if self.is_dual_gpu:
                    self.text_model = AutoModel.from_pretrained(
                        self.name,
                        trust_remote_code=True,
                        low_cpu_mem_usage=False,
                        torch_dtype=torch.float32
                    ).to(self.device_text).eval()
                else:
                    self.text_model = self.vision_model

            # 5. Phân luồng Jina-CLIP (Áp dụng Jina Shield chống lỗi Meta Tensor từ Phase 1)
            elif is_jina:
                from transformers import AutoModel
                self.model_type = "jina_clip"
                
                original_context_managers = getattr(transformers.modeling_utils, "ContextManagers", None)
                if original_context_managers is not None:
                    transformers.modeling_utils.ContextManagers = lambda ctx: contextlib.nullcontext()
                
                try:
                    self.vision_model = AutoModel.from_pretrained(
                        self.name,
                        trust_remote_code=True,
                        low_cpu_mem_usage=False,
                        torch_dtype=torch.float32
                    ).to(self.device_vision).eval()
                    
                    if self.is_dual_gpu:
                        self.text_model = AutoModel.from_pretrained(
                            self.name,
                            trust_remote_code=True,
                            low_cpu_mem_usage=False,
                            torch_dtype=torch.float32
                        ).to(self.device_text).eval()
                    else:
                        self.text_model = self.vision_model
                finally:
                    if original_context_managers is not None:
                        transformers.modeling_utils.ContextManagers = original_context_managers

            # 6. Phân luồng HuggingFace Transformers mặc định (SigLIP, CLIP, MetaCLIP, AltCLIP)
            else:
                from transformers import AutoProcessor, AutoModel, SiglipModel, CLIPModel
                self.model_type = "transformers"
                self.processor = AutoProcessor.from_pretrained(self.name, trust_remote_code=True)
                
                if "siglip" in self.name.lower():
                    self.vision_model = SiglipModel.from_pretrained(self.name).to(self.device_vision).eval()
                    self.text_model = SiglipModel.from_pretrained(self.name).to(self.device_text).eval() if self.is_dual_gpu else self.vision_model
                else:
                    self.vision_model = AutoModel.from_pretrained(self.name, trust_remote_code=True).to(self.device_vision).eval()
                    self.text_model = AutoModel.from_pretrained(self.name, trust_remote_code=True).to(self.device_text).eval() if self.is_dual_gpu else self.vision_model

            self.model = self.vision_model
            print(f"[+] Nạp thành công: {self.name} (Phân luồng: {self.model_type})")
        except Exception as e:
            print(f"[!] Lỗi khi nạp mô hình {self.name}: {e}")
            self.vision_model = None
            self.text_model = None
            self.model = None

    @torch.no_grad()
    def get_image_embeddings(self, images: list, batch_size: int = None) -> np.ndarray:
        if self.vision_model is None or not images:
            return np.zeros((len(images), self.dim), dtype=np.float32)
            
        if batch_size is None:
            batch_size = 64 if self.is_dual_gpu else 32
            
        all_vecs = []
        for i in range(0, len(images), batch_size):
            batch_imgs = images[i : i + batch_size]
            
            # SBERT Multilingual, M-CLIP, OpenCLIP: Sử dụng Vision Tower trên GPU 0 (cuda:0)
            if self.model_type in ("sbert_multilingual_clip", "m_clip", "open_clip"):
                tensors = torch.stack([self.preprocess(img) for img in batch_imgs]).to(self.device_vision)
                features = self.vision_model.encode_image(tensors)
                features = F.normalize(features, p=2, dim=-1)
                batch_res = features.cpu().numpy().astype(np.float32)

            elif self.model_type == "viclip_ot":
                if hasattr(self.vision_model, "encode_image"):
                    vecs = self.vision_model.encode_image(batch_imgs)
                    if not isinstance(vecs, torch.Tensor):
                        vecs = torch.tensor(vecs, device=self.device_vision)
                    vecs = F.normalize(vecs, p=2, dim=-1)
                    batch_res = vecs.cpu().numpy().astype(np.float32)
                elif hasattr(self.vision_model, "get_image_features") and self.processor:
                    inputs = self.processor(images=batch_imgs, return_tensors="pt").to(self.device_vision)
                    outputs = self.vision_model.get_image_features(**inputs)
                    features = F.normalize(outputs, p=2, dim=-1)
                    batch_res = features.cpu().numpy().astype(np.float32)
                else:
                    inputs = self.processor(images=batch_imgs, return_tensors="pt").to(self.device_vision) if self.processor else batch_imgs
                    if isinstance(inputs, dict):
                        outputs = self.vision_model(**inputs)
                    else:
                        outputs = self.vision_model(inputs)
                    tensor = outputs.image_embeds if hasattr(outputs, "image_embeds") and outputs.image_embeds is not None else (outputs.pooler_output if hasattr(outputs, "pooler_output") and outputs.pooler_output is not None else (outputs[0] if isinstance(outputs, (tuple, list)) else outputs))
                    if not isinstance(tensor, torch.Tensor):
                        tensor = torch.tensor(tensor, device=self.device_vision)
                    features = F.normalize(tensor, p=2, dim=-1)
                    batch_res = features.cpu().numpy().astype(np.float32)

            elif self.model_type == "jina_clip":
                vecs = self.vision_model.encode_image(batch_imgs)
                if not isinstance(vecs, torch.Tensor):
                    vecs = torch.tensor(vecs, device=self.device_vision)
                vecs = F.normalize(vecs, p=2, dim=-1)
                batch_res = vecs.cpu().numpy().astype(np.float32)
                
            else: # transformers (SigLIP, CLIP, MetaCLIP, AltCLIP)
                inputs = self.processor(images=batch_imgs, return_tensors="pt").to(self.device_vision)
                if hasattr(self.vision_model, "get_image_features"):
                    outputs = self.vision_model.get_image_features(**inputs)
                else:
                    outputs = self.vision_model(**inputs)
                    
                if isinstance(outputs, torch.Tensor):
                    tensor = outputs
                elif hasattr(outputs, "image_embeds") and outputs.image_embeds is not None:
                    tensor = outputs.image_embeds
                elif hasattr(outputs, "pooler_output") and outputs.pooler_output is not None:
                    tensor = outputs.pooler_output
                elif hasattr(outputs, "last_hidden_state") and outputs.last_hidden_state is not None:
                    tensor = outputs.last_hidden_state[:, 0, :]
                elif isinstance(outputs, (tuple, list)):
                    tensor = outputs[0]
                else:
                    tensor = outputs
                    
                features = F.normalize(tensor, p=2, dim=-1)
                batch_res = features.cpu().numpy().astype(np.float32)
                
            all_vecs.append(batch_res)
            
        return np.vstack(all_vecs)

    @torch.no_grad()
    def get_text_embeddings(self, texts: list, batch_size: int = None) -> np.ndarray:
        if self.text_model is None or not texts:
            return np.zeros((len(texts), self.dim), dtype=np.float32)
            
        if batch_size is None:
            batch_size = 128 if self.is_dual_gpu else 64
            
        all_vecs = []
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            
            # SBERT Multilingual: Text Tower trên GPU 1 (cuda:1)
            if self.model_type == "sbert_multilingual_clip":
                vecs = self.text_model.encode(batch_texts, convert_to_numpy=True, show_progress_bar=False)
                norms = np.linalg.norm(vecs, ord=2, axis=-1, keepdims=True)
                batch_res = (vecs / np.clip(norms, 1e-12, None)).astype(np.float32)
                
            # M-CLIP: Text Tower trên GPU 1 (cuda:1)
            elif self.model_type == "m_clip":
                inputs = self.tokenizer(batch_texts, padding=True, truncation=True, max_length=128, return_tensors="pt").to(self.device_text)
                outputs = self.text_model(**inputs)
                last_hidden = outputs.last_hidden_state
                att = inputs["attention_mask"].unsqueeze(-1)
                pooled = (last_hidden * att).sum(dim=1) / torch.clamp(att.sum(dim=1), min=1e-9)
                features = self.linear_head(pooled)
                features = F.normalize(features, p=2, dim=-1)
                batch_res = features.cpu().numpy().astype(np.float32)

            elif self.model_type == "viclip_ot":
                if hasattr(self.text_model, "encode_text"):
                    vecs = self.text_model.encode_text(batch_texts)
                    if not isinstance(vecs, torch.Tensor):
                        vecs = torch.tensor(vecs, device=self.device_text)
                    vecs = F.normalize(vecs, p=2, dim=-1)
                    batch_res = vecs.cpu().numpy().astype(np.float32)
                elif hasattr(self.text_model, "encode"):
                    vecs = self.text_model.encode(batch_texts)
                    if not isinstance(vecs, torch.Tensor):
                        vecs = torch.tensor(vecs, device=self.device_text)
                    vecs = F.normalize(vecs, p=2, dim=-1)
                    batch_res = vecs.cpu().numpy().astype(np.float32)
                elif hasattr(self.text_model, "get_text_features") and self.processor:
                    inputs = self.processor(text=batch_texts, padding=True, truncation=True, return_tensors="pt").to(self.device_text)
                    outputs = self.text_model.get_text_features(**inputs)
                    features = F.normalize(outputs, p=2, dim=-1)
                    batch_res = features.cpu().numpy().astype(np.float32)
                else:
                    inputs = self.processor(text=batch_texts, padding=True, truncation=True, return_tensors="pt").to(self.device_text) if self.processor else batch_texts
                    if isinstance(inputs, dict):
                        outputs = self.text_model(**inputs)
                    else:
                        outputs = self.text_model(inputs)
                    tensor = outputs.text_embeds if hasattr(outputs, "text_embeds") and outputs.text_embeds is not None else (outputs.pooler_output if hasattr(outputs, "pooler_output") and outputs.pooler_output is not None else (outputs[0] if isinstance(outputs, (tuple, list)) else outputs))
                    if not isinstance(tensor, torch.Tensor):
                        tensor = torch.tensor(tensor, device=self.device_text)
                    features = F.normalize(tensor, p=2, dim=-1)
                    batch_res = features.cpu().numpy().astype(np.float32)

            elif self.model_type == "jina_clip":
                vecs = self.text_model.encode_text(batch_texts)
                if not isinstance(vecs, torch.Tensor):
                    vecs = torch.tensor(vecs, device=self.device_text)
                vecs = F.normalize(vecs, p=2, dim=-1)
                batch_res = vecs.cpu().numpy().astype(np.float32)
                
            elif self.model_type == "open_clip":
                tokens = self.tokenizer(batch_texts).to(self.device_text)
                features = self.text_model.encode_text(tokens)
                features = F.normalize(features, p=2, dim=-1)
                batch_res = features.cpu().numpy().astype(np.float32)
                
            else: # transformers (SigLIP, CLIP, MetaCLIP, AltCLIP)
                inputs = self.processor(text=batch_texts, padding=True, truncation=True, return_tensors="pt").to(self.device_text)
                if hasattr(self.text_model, "get_text_features"):
                    outputs = self.text_model.get_text_features(**inputs)
                else:
                    outputs = self.text_model(**inputs)
                    
                if isinstance(outputs, torch.Tensor):
                    tensor = outputs
                elif hasattr(outputs, "text_embeds") and outputs.text_embeds is not None:
                    tensor = outputs.text_embeds
                elif hasattr(outputs, "pooler_output") and outputs.pooler_output is not None:
                    tensor = outputs.pooler_output
                elif hasattr(outputs, "last_hidden_state") and outputs.last_hidden_state is not None:
                    tensor = outputs.last_hidden_state[:, 0, :]
                elif isinstance(outputs, (tuple, list)):
                    tensor = outputs[0]
                else:
                    tensor = outputs
                    
                features = F.normalize(tensor, p=2, dim=-1)
                batch_res = features.cpu().numpy().astype(np.float32)
                
            all_vecs.append(batch_res)
            
        return np.vstack(all_vecs)

    def unload(self):
        if hasattr(self, "vision_model") and self.vision_model is not None:
            del self.vision_model
            self.vision_model = None
        if hasattr(self, "text_model") and self.text_model is not None:
            del self.text_model
            self.text_model = None
        if hasattr(self, "linear_head") and self.linear_head is not None:
            del self.linear_head
            self.linear_head = None
        del self.processor
        del self.tokenizer
        del self.preprocess
        self.processor = None
        self.tokenizer = None
        self.preprocess = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

# %% [code]
# ==============================================================================
# 4. CHUẨN BỊ MẪU DỮ LIỆU & GROUND TRUTH (HỖ TRỢ VIRTUAL CACHE .BLOB)
# ==============================================================================
import zipfile
import io
import glob

def find_kaggle_blob_path() -> str:
    """
    Tự động quét và phát hiện tệp .blob trong môi trường Kaggle hoặc cục bộ.
    """
    candidates = [
        "/kaggle/input/**/*.blob",
        "/kaggle/working/**/*.blob",
        os.path.join("..", "..", "data", "**", "*.blob"),
        os.path.join(".", "**", "*.blob")
    ]
    for pattern in candidates:
        matches = glob.glob(pattern, recursive=True)
        if matches:
            return matches[0]
    return ""

def load_or_create_ground_truth(manifest_path: str = None, num_samples: int = 10) -> tuple:
    """
    Nạp dữ liệu ground truth.
    - Ưu tiên 1: Đọc từ tệp manifest JSON và nạp ảnh từ .blob (Virtual Cache) hoặc đĩa cục bộ.
    - Ưu tiên 2: Đọc trực tiếp danh sách ảnh từ .blob nạp lên VRAM.
    - Fallback: Tạo tập dữ liệu giả lập (Synthetic Test) để kiểm thử luồng code.
    """
    images = []
    queries_en = []
    queries_vi = []
    
    blob_path = find_kaggle_blob_path()
    zf = zipfile.ZipFile(blob_path, 'r') if blob_path and os.path.exists(blob_path) else None
    
    if zf:
        print(f"[INFO] Đã kết nối Virtual Cache: {blob_path}")

    # 1. Thử đọc từ manifest
    manifest_loaded = False
    if manifest_path and os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            for item in manifest[:num_samples]:
                img_p = item.get("image_path", "")
                img_obj = None
                
                # Thử đọc từ file blob nếu có
                if zf:
                    matching_names = [name for name in zf.namelist() if os.path.basename(img_p) in name or img_p in name]
                    if matching_names:
                        data = zf.read(matching_names[0])
                        img_obj = Image.open(io.BytesIO(data)).convert("RGB")
                
                # Thử đọc từ đường dẫn cục bộ
                if img_obj is None and img_p and os.path.exists(img_p):
                    img_obj = Image.open(img_p).convert("RGB")
                    
                if img_obj is None:
                    img_obj = Image.new("RGB", (224, 224), color=(np.random.randint(0,255), 100, 150))
                    
                images.append(img_obj)
                queries_en.append(item.get("caption_en", "a scene in video"))
                queries_vi.append(item.get("caption_vi", "một cảnh trong video"))
            manifest_loaded = True
        except Exception as e:
            print(f"[CẢNH BÁO] Không thể nạp manifest ({e}). Chuyển sang chế độ tự động quét.")

    # 2. Nếu không có manifest nhưng có tệp .blob
    if not manifest_loaded and zf:
        exts = ('.jpg', '.jpeg', '.png', '.webp')
        all_imgs = [info.filename for info in zf.infolist() if info.filename.lower().endswith(exts)]
        selected_imgs = all_imgs[:num_samples]
        for name in selected_imgs:
            data = zf.read(name)
            img = Image.open(io.BytesIO(data)).convert("RGB")
            images.append(img)
            base_n = os.path.splitext(os.path.basename(name))[0]
            queries_en.append(f"A keyframe scene showing {base_n}")
            queries_vi.append(f"Khung cảnh video tại khoảnh khắc {base_n}")
        manifest_loaded = True

    # 3. Fallback: Synthetic Test
    if not manifest_loaded or len(images) == 0:
        print("[INFO] Đang tạo tập synthetic test để kiểm tra luồng...")
        images = []
        queries_en = []
        queries_vi = []
        for i in range(num_samples):
            r = int((i * 37) % 255)
            g = int((i * 67) % 255)
            b = int((i * 97) % 255)
            img = Image.new("RGB", (224, 224), color=(r, g, b))
            images.append(img)
            queries_en.append(f"Sample test event number {i+1} with color tone RGB({r},{g},{b})")
            queries_vi.append(f"Cảnh quay thử nghiệm số {i+1} với tông màu RGB({r},{g},{b})")
            
    if zf:
        zf.close()
        
    return images, queries_en, queries_vi

def get_base_dir() -> str:
    """
    Lay duong dan thu muc goc an toan cho ca moi truong Script (.py) va Jupyter Notebook (.ipynb / Kaggle).
    """
    if "__file__" in globals():
        return os.path.dirname(os.path.abspath(__file__))
    return os.getcwd()

# %% [code]
# ==============================================================================
# 5. VẬN HÀNH BENCHMARK TOÀN DIỆN (EXECUTION PIPELINE)
# ==============================================================================
def run_accuracy_benchmark():
    base_dir = get_base_dir()
    manifest_file = os.path.join(base_dir, "..", "..", "data", "ground_truth_sample_manifest.json")
    if not os.path.exists(manifest_file):
        for candidate in [
            os.path.join(base_dir, "ground_truth_sample_manifest.json"),
            "/kaggle/input/ground_truth_sample_manifest.json",
            "/kaggle/working/ground_truth_sample_manifest.json"
        ]:
            if os.path.exists(candidate):
                manifest_file = candidate
                break

    images, queries_en, queries_vi = load_or_create_ground_truth(manifest_file, num_samples=BENCHMARK_SAMPLES)
    
    print(f"[*] Đã sẵn sàng {len(images)} mẫu Ground Truth cho bài kiểm thử Phase 2.")
    
    results = []
    
    all_models = []
    for grp_name, model_list in CANDIDATE_MODELS_PHASE2.items():
        for m in model_list:
            all_models.append((m, grp_name))
    
    for model_info, group in all_models:
        model_name = model_info["name"]
        print(f"\n{'='*70}\n[>>>] ĐANG ĐO ĐẠC MÔ HÌNH: {model_name} (Nhóm: {group})\n{'='*70}")
        
        start_t = time.time()
        wrapper = BenchmarkModelWrapper(model_info, device=DEVICE)
        load_time = time.time() - start_t
        
        if wrapper.vision_model is None or wrapper.text_model is None:
            print(f"[!] Bỏ qua {model_name} do không khởi tạo được.")
            continue
            
        # 1. Trích xuất Image Embeddings
        t0 = time.time()
        img_embeds = wrapper.get_image_embeddings(images)
        img_extract_time = time.time() - t0
        
        # 2. Trích xuất Text Embeddings (Tiếng Anh)
        t0 = time.time()
        text_embeds_en = wrapper.get_text_embeddings(queries_en)
        sim_matrix_en = np.dot(text_embeds_en, img_embeds.T)
        metrics_en = compute_retrieval_metrics(sim_matrix_en)
        text_en_time = time.time() - t0
        
        # 3. Trích xuất Text Embeddings (Tiếng Việt)
        t0 = time.time()
        text_embeds_vi = wrapper.get_text_embeddings(queries_vi)
        sim_matrix_vi = np.dot(text_embeds_vi, img_embeds.T)
        metrics_vi = compute_retrieval_metrics(sim_matrix_vi)
        text_vi_time = time.time() - t0
        
        wrapper.unload()
        
        entry = {
            "model_name": model_name,
            "group": group,
            "dim": model_info.get("dim", 512),
            "load_time_sec": round(load_time, 2),
            "img_extract_sec": round(img_extract_time, 3),
            # Metrics Tiếng Anh
            "en_recall@1": metrics_en["recall@1"],
            "en_recall@5": metrics_en["recall@5"],
            "en_recall@10": metrics_en["recall@10"],
            "en_mrr": metrics_en["mrr"],
            "en_margin": metrics_en["cosine_margin"],
            # Metrics Tiếng Việt
            "vi_recall@1": metrics_vi["recall@1"],
            "vi_recall@5": metrics_vi["recall@5"],
            "vi_recall@10": metrics_vi["recall@10"],
            "vi_mrr": metrics_vi["mrr"],
            "vi_margin": metrics_vi["cosine_margin"],
        }
        results.append(entry)
        print(f"[-] EN Results: R@1={metrics_en['recall@1']}% | R@5={metrics_en['recall@5']}% | MRR={metrics_en['mrr']} | Margin={metrics_en['cosine_margin']}")
        print(f"[-] VI Results: R@1={metrics_vi['recall@1']}% | R@5={metrics_vi['recall@5']}% | MRR={metrics_vi['mrr']} | Margin={metrics_vi['cosine_margin']}")

    # ==============================================================================
    # 6. XUẤT BÁO CÁO TỔNG KẾT
    # ==============================================================================
    df = pd.DataFrame(results)
    if os.path.exists('/kaggle/working'):
        out_dir = "/kaggle/working"
    else:
        out_dir = os.path.join(get_base_dir(), "..", "..", "data", "results")
    os.makedirs(out_dir, exist_ok=True)
    
    json_path = os.path.join(out_dir, "phase2_accuracy_metrics.json")
    csv_path = os.path.join(out_dir, "phase2_accuracy_metrics.csv")
    md_path = os.path.join(out_dir, "phase2_accuracy_report.md")
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    df.to_csv(csv_path, index=False)
    
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Báo Cáo Đo Lường Độ Chính Xác Phase 2 (Accuracy Benchmark Results)\n\n")
        f.write(f"- Thời gian thực thi: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"- Số lượng mẫu: {BENCHMARK_SAMPLES}\n")
        f.write(f"- Thiết bị: {DEVICE}\n\n")
        f.write("## 1. Bảng Kết Quả Chi Tiết\n\n")
        f.write(df.to_markdown(index=False))
        f.write("\n\n## 2. Nhận Xét & Đối Chiếu Trường Phái Ngôn Ngữ\n\n")
        f.write("- So sánh trực quan giữa hiệu năng truy vấn Tiếng Anh (Translate-then-Search) và Tiếng Việt trực tiếp.\n")
        
    print(f"\n[+] ĐÃ HOÀN TẤT BENCHMARK PHASE 2! Báo cáo lưu tại: {md_path}")
    return df

if __name__ == "__main__":
    run_accuracy_benchmark()
