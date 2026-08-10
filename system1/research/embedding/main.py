"""
Module Kiểm thử Giao diện Lệnh (CLI Runner) cho Phân hệ Embedding.

Mô tả:
Kịch bản này cung cấp giao diện dòng lệnh cơ bản để khởi tạo và kiểm thử nhanh 
các mô hình Multimodal Embedding (mặc định là SigLIP Base). Nó phục vụ việc 
xác thực cấu trúc dữ liệu đầu ra (shape), độ chuẩn hóa (L2-norm) và đo lường 
độ trễ (latency) khi chạy cục bộ (local).

Đóng vai trò là Bước 3 (Hiện thực hóa Hàm Lõi) trong Lộ trình Nghiên cứu, 
đảm bảo hàm `get_vector()` hoạt động ổn định trước khi tích hợp vào hệ thống FAISS.
"""

import sys
import time
from pathlib import Path
import numpy as np

# Force UTF-8 stdout encoding for cross-platform compatibility
sys.stdout.reconfigure(encoding='utf-8')

from extractor import get_vector, SigLIPEmbeddingExtractor

def main():
    print("=== AIC 2026 Multimodal Embedding Research CLI Runner ===")
    
    # 1. Initialize SigLIP Extractor
    model_name = "google/siglip-base-patch16-224"
    print(f"[INFO] Testing Extractor with model: {model_name}")
    
    extractor = SigLIPEmbeddingExtractor(model_name=model_name)
    extractor._ensure_initialized()
    
    print(f"Device: {extractor.device}")
    
    # 2. Test Text Queries
    queries = [
        "cầu thủ mặc áo đỏ đang sút bóng",
        "a soccer player in a red jersey kicking the ball",
        "a red shirt football athlete shooting a goal inside stadium"
    ]
    
    print("\n--- Test Text Embeddings ---")
    start = time.time()
    for q in queries:
        vec = extractor.get_vector(q)
        print(f"Query: '{q}'")
        print(f"  - Vector shape: {vec.shape}")
        print(f"  - L2 norm: {np.linalg.norm(vec, ord=2):.6f}")
        print(f"  - Top 3 values: {np.round(vec[:3], 4)}")
        
    print(f"Total time: {(time.time() - start)*1000:.2f}ms")
    print("\n[SUCCESS] Embedding research pipeline test completed successfully.")

if __name__ == "__main__":
    main()
