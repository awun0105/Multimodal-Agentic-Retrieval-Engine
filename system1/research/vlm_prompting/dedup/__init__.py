"""
Khử trùng lặp keyframe — giải pháp TẠM để giảm số ảnh phải caption.

⚠️ Đây KHÔNG phải phát hiện shot boundary chính thức. Repo hiện chưa có shot
boundary thật (`system1/src/system1/shots/builder.py` gán cả video = 1 shot).
Module này chỉ gom các keyframe LIỀN KỀ (theo thứ tự tên file) trông giống hệt
nhau bằng heuristic rẻ (pHash / histogram màu), để tránh caption lặp lại ảnh
gần như y hệt. Khi code lõi có shot boundary thật, module này nên bị thay thế.

Chỉ dùng Pillow + numpy — không import torch/transformers, chạy được CPU thuần.
"""

from __future__ import annotations

from .perceptual_dedup import NhomAnh, gom_nhom_lien_ke, khoang_cach_hamming, phash, histogram_mau

__all__ = [
    "NhomAnh",
    "gom_nhom_lien_ke",
    "khoang_cach_hamming",
    "phash",
    "histogram_mau",
]
