"""
Bộ đo chất lượng caption — thước đo mới, độc lập với `scripts/metrics.py`.

`metrics.py` đo "có tuân thủ đề bài không" (JSON hợp lệ, đủ trường, đủ dài).
Bộ này đo "caption có dùng để TÌM ẢNH được không" — hai câu hỏi khác nhau,
một caption có thể đạt tối đa điểm bên kia mà vô dụng ở đây.
"""

from __future__ import annotations
