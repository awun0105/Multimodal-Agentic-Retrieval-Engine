"""
Danh mục các VLM ứng viên và cấu hình nạp tương ứng.

Đổi model = đổi một dòng `model_key`, không sửa code ở chỗ khác. Đây là lý do
tách file này ra khỏi generate.py.

Số VRAM là ước tính ở chế độ 4-bit, đã trừ phần vision tower giữ nguyên FP16.
Con số thật phải đo bằng benchmark ở Phase 04 — đừng tin bảng này tuyệt đối.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelSpec:
    key: str
    hf_id: str
    ten_hien_thi: str
    vram_4bit_gb: float
    loader: str  # "qwen2vl" | "qwen25vl" | "auto_causal"
    ghi_chu: str = ""
    trust_remote_code: bool = False
    # Không lượng tử hóa các module này — vision tower ở 4-bit làm rơi ~10% chất lượng.
    skip_quant_modules: tuple[str, ...] = field(default=("visual", "vision_tower", "vision_model"))


MODEL_REGISTRY: dict[str, ModelSpec] = {
    "qwen25vl-3b": ModelSpec(
        key="qwen25vl-3b",
        hf_id="Qwen/Qwen2.5-VL-3B-Instruct",
        ten_hien_thi="Qwen2.5-VL 3B Instruct",
        vram_4bit_gb=3.0,
        loader="qwen25vl",
        ghi_chu="Cân bằng nhất cho GPU 8-16GB. Đa ngôn ngữ tốt.",
    ),
    "qwen25vl-7b": ModelSpec(
        key="qwen25vl-7b",
        hf_id="Qwen/Qwen2.5-VL-7B-Instruct",
        ten_hien_thi="Qwen2.5-VL 7B Instruct",
        vram_4bit_gb=5.5,
        loader="qwen25vl",
        ghi_chu="Chất lượng cao nhất nhóm <7B. Cần >=12GB VRAM để thoải mái.",
    ),
    "qwen2vl-2b": ModelSpec(
        key="qwen2vl-2b",
        hf_id="Qwen/Qwen2-VL-2B-Instruct",
        ten_hien_thi="Qwen2-VL 2B Instruct",
        vram_4bit_gb=2.0,
        loader="qwen2vl",
        ghi_chu="Nhẹ. Đồng đội Phần 2 đo ~1.25s/ảnh trên RTX 4060, đôi khi từ chối trả lời tiếng Việt.",
    ),
    "vintern-1b": ModelSpec(
        key="vintern-1b",
        hf_id="5CD-AI/Vintern-1B-v3_5",
        ten_hien_thi="Vintern 1B v3.5 (chuyên tiếng Việt)",
        vram_4bit_gb=1.5,
        loader="auto_causal",
        trust_remote_code=True,
        ghi_chu="VLM fine-tune riêng cho tiếng Việt. Mốc so sánh bắt buộc ở cổng kiểm Phase 04.",
    ),
    "minicpm-v-4": ModelSpec(
        key="minicpm-v-4",
        hf_id="openbmb/MiniCPM-V-4",
        ten_hien_thi="MiniCPM-V 4.0",
        vram_4bit_gb=3.0,
        loader="auto_causal",
        trust_remote_code=True,
        ghi_chu="Đường lui cho GPU yếu (<8GB).",
    ),
}

MODEL_MAC_DINH = "qwen25vl-3b"


def lay_spec(model_key: str) -> ModelSpec:
    if model_key not in MODEL_REGISTRY:
        co_san = ", ".join(sorted(MODEL_REGISTRY))
        raise KeyError(f"Không có model '{model_key}'. Các lựa chọn: {co_san}")
    return MODEL_REGISTRY[model_key]


def goi_y_theo_vram(vram_gb: float) -> list[str]:
    """
    Model nào chạy vừa với lượng VRAM cho trước, nhẹ nhất xếp trước.

    Trừ hao 1.5GB cho ảnh đầu vào, KV cache và phân mảnh bộ nhớ. Không trừ hao
    thì model 3GB sẽ được gợi ý cho GPU 4GB rồi tràn ngay lúc chạy thật.
    """
    vram_dung_duoc = vram_gb - 1.5
    vua = [s for s in MODEL_REGISTRY.values() if s.vram_4bit_gb <= vram_dung_duoc]
    return [s.key for s in sorted(vua, key=lambda s: s.vram_4bit_gb)]
