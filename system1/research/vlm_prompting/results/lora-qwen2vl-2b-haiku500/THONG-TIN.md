# Adapter LoRA — Qwen2-VL-2B học từ 290 caption chưng cất

**Train xong:** 16/08/2026 16:03 · Kaggle Tesla T4 · lượt thứ 15

> ⚠️ **`adapter_model.safetensors` (71 MB) KHÔNG commit** — vượt ngưỡng khuyến nghị GitHub.
> File này chỉ ghi cấu hình + số đo. Cách lấy lại ở mục cuối.

---

## Số đo

| Mục | Giá trị |
|---|---|
| Loss cuối train | **1,3623** |
| Loss cuối eval | **1,3169** |
| Thời gian train | 5.803 s ≈ **97 phút** (2 epoch, 66 bước) |
| Đỉnh bộ nhớ | 5,21 GB / 14,56 GB |
| Tham số train được | 18.464.768 = **0,83%** tổng |
| Kích thước | 73,9 MB |

**Eval loss thấp hơn train loss** — model học được, chưa học thuộc lòng.

## Cấu hình

```
base_model: Qwen/Qwen2-VL-2B-Instruct
r: 16 · lora_alpha: 32 · lora_dropout: 0.05
target_modules: q_proj k_proj v_proj o_proj gate_proj up_proj down_proj
task_type: CAUSAL_LM
```

Nén 4-bit NF4, tính toán ở float32 (fp16 tràn số trên QLoRA — xem mục dưới).

## Bằng chứng vision encoder đóng băng

Đọc header `safetensors`:

| Kiểm | Kết quả |
|---|---|
| Số tensor | 392 — khớp số tầng LoRA đo lúc train |
| Tensor dính `visual`/`vision` | **0** |
| Tên tensor | `base_model.model.model.**language_model**.layers.*` |

Tính tay để đối chiếu: LoRA r=16 trên 28 lớp LLM (hidden 1536, inter 8960, kv 256) phải ra
đúng **18.464.768** tham số. Log ghi đúng con số đó, lệch 0.

## Dữ liệu huấn luyện

- 261 mẫu train + 29 mẫu eval — `data/dataset_qlora/`
- Nguồn: 290 caption do agent Claude Haiku sinh (`results/checkpoint_haiku-teacher.json`)
- 60 ảnh holdout **giữ sạch** — `results/danh_sach_anh_holdout.txt`

⚠️ Đo trước/sau **phải dùng 60 ảnh holdout**. Đo trên ảnh đã train sẽ cho số đẹp giả tạo.

## Cách sinh lại

```powershell
$env:TMP="D:\aic-tmp"; $env:TEMP="D:\aic-tmp"; $env:PYTHONUTF8="1"
python scripts/kaggle/kaggle-day-notebook.py `
  --notebook scripts/kaggle/notebook-train-qlora.ipynb `
  --meta <kernel-metadata.json> --staging D:\aic-tmp\nb-staging --chay-luon
```

~97 phút trên T4. Notebook đã chứa cả 6 cấu hình bắt buộc.

## Sáu cấu hình bắt buộc — thiếu một cái là hỏng

Rút từ 15 lượt chạy. Chi tiết ở `docs/kaggle-huong-dan-va-bay.md` mục 5bis.

| # | Cấu hình | Thiếu thì |
|---|---|---|
| 1 | `CUDA_VISIBLE_DEVICES='0'` trước import torch | Trainer nhân bản model ra 2 card T4 → `illegal memory access` |
| 2 | `fp16=False`, `dtype=float32` | Loss thành `nan`, adapter vô dụng |
| 3 | `device_map={'': 0}` | OOM ở GPU 1 dù model chỉ 1,4 GB |
| 4 | `config.use_cache = False` | Model 1,4 GB mà 1 mẫu ngốn 13 GB |
| 5 | `enable_input_require_grads()` | Grad không về LoRA → **adapter rỗng**, không báo lỗi |
| 6 | `remove_unused_columns=False` | `KeyError: 'image'` trong collate |

## Cách dùng

```python
get_adapter("qwen2vl-2b", backend="transformers",
            lora_model_path="results/lora-qwen2vl-2b-haiku500")
```

Không truyền `lora_model_path` thì hành vi y hệt model gốc.
