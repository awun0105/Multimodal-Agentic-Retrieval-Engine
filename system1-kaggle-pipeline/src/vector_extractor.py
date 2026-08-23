"""
Phase 02: Multimodal Dense Embedding & L2 Normalization
Module trích xuất Vector nhúng đa phương thức sử dụng mô hình SigLIP Base.

Chức năng:
1. Tự động nhận diện phần cứng: Kaggle TPU v3-8 (PyTorch/XLA), Dual GPU (CUDA / DataParallel) hoặc CPU.
2. Batch inference hình ảnh và câu truy vấn văn bản quy mô lớn.
3. Chuẩn hóa Euclidean L2-Norm = 1.0 phục vụ tìm kiếm tích vô hướng Inner Product trong FAISS.

Hợp đồng dữ liệu đầu vào (Input):
- image_paths: Danh sách đường dẫn ảnh keyframe (List[Path | str]).
- text_query: Chuỗi văn bản truy vấn tiếng Anh hoặc tiếng Việt.

Hợp đồng dữ liệu đầu ra (Output):
- Ma trận vector NumPy shape (N, 768) kiểu float32 chuẩn hóa L2 = 1.0.
"""

from __future__ import annotations
import torch
import numpy as np
from pathlib import Path
from PIL import Image
from typing import Any
from transformers import AutoProcessor, AutoModel


def detect_optimal_device() -> tuple[str, Any]:
    """Tự động phát hiện thiết bị tối ưu (TPU -> GPU -> CPU)."""
    # 1. Thử nghiệm TPU (PyTorch/XLA)
    try:
        import torch_xla.core.xla_model as xm
        device = xm.xla_device()
        print("[HARDWARE] Đã kích hoạt Kaggle TPU v3-8 (PyTorch/XLA)!")
        return "xla", device
    except Exception:
        pass

    # 2. Thử nghiệm GPU (CUDA)
    if torch.cuda.is_available():
        num_gpus = torch.cuda.device_count()
        print(f"[HARDWARE] Đã kích hoạt {num_gpus}x NVIDIA GPU (CUDA)!")
        return "cuda", torch.device("cuda")

    # 3. Fallback CPU
    print("[HARDWARE] Đang sử dụng CPU chuẩn.")
    return "cpu", torch.device("cpu")


class SigLIPVectorExtractor:
    def __init__(
        self,
        model_name: str = "google/siglip-base-patch16-224",
        device: str | None = None,
        batch_size: int = 64
    ):
        self.model_name = model_name
        self.device_type, self.device = (detect_optimal_device() if device is None else (device, torch.device(device)))
        
        # Nếu là TPU hoặc Multi-GPU, tăng batch_size để tối đa hóa thông lượng
        if self.device_type == "xla":
            self.batch_size = max(batch_size, 128)
        elif self.device_type == "cuda" and torch.cuda.device_count() > 1:
            self.batch_size = max(batch_size, 128)
        else:
            self.batch_size = batch_size

        self.model = None
        self.processor = None

    def _load_model(self):
        if self.model is None:
            self.processor = AutoProcessor.from_pretrained(self.model_name)
            base_model = AutoModel.from_pretrained(self.model_name)

            if self.device_type == "cuda" and torch.cuda.device_count() > 1:
                self.model = torch.nn.DataParallel(base_model).to(self.device)
            else:
                self.model = base_model.to(self.device)

            self.model.eval()

    def extract_image_vectors(
        self,
        image_paths: list[Path | str],
        normalize_l2: bool = True
    ) -> np.ndarray:
        """
        Trích xuất ma trận vector cho danh sách ảnh.
        Trả về mảng NumPy shape (N, dim) với kiểu dữ liệu float32.
        """
        self._load_model()
        all_vectors = []

        for i in range(0, len(image_paths), self.batch_size):
            batch_paths = image_paths[i : i + self.batch_size]
            images = []
            for p in batch_paths:
                try:
                    img = Image.open(str(p)).convert("RGB")
                    images.append(img)
                except Exception:
                    images.append(Image.new("RGB", (224, 224), (0, 0, 0)))

            inputs = self.processor(images=images, return_tensors="pt").to(self.device)
            with torch.no_grad():
                # Xử lý tương thích cho DataParallel hoặc Single-device
                if hasattr(self.model, "module"):
                    image_features = self.model.module.get_image_features(**inputs)
                else:
                    image_features = self.model.get_image_features(**inputs)

                if normalize_l2:
                    image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                all_vectors.append(image_features.cpu().numpy())

        if not all_vectors:
            return np.empty((0, 768), dtype=np.float32)

        return np.vstack(all_vectors).astype(np.float32)

    def extract_text_vector(
        self,
        text_query: str,
        normalize_l2: bool = True
    ) -> np.ndarray:
        """
        Trích xuất vector 1D cho câu truy vấn văn bản.
        """
        self._load_model()
        inputs = self.processor(text=[text_query], return_tensors="pt", padding=True).to(self.device)
        with torch.no_grad():
            if hasattr(self.model, "module"):
                text_features = self.model.module.get_text_features(**inputs)
            else:
                text_features = self.model.get_text_features(**inputs)

            if normalize_l2:
                text_features = text_features / text_features.norm(dim=-1, keepdim=True)
            return text_features.cpu().numpy()[0].astype(np.float32)
