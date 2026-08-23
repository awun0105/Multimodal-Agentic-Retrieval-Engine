# %% [markdown]
# # Kaggle / Colab: Tự Động Sinh Semantic Ground Truth Bằng Vision-Language Model (VLM)
# 
# **Mục đích:**
# - Quét trực tiếp kho ảnh `cached_keyframes.blob` trên Kaggle/Colab mà không cần giải nén ra đĩa cứng.
# - Sử dụng các mô hình Vision-Language Model (VLM) hàng đầu (`Qwen/Qwen2-VL-2B-Instruct` và `microsoft/Florence-2-large`) để sinh mô tả chi tiết song ngữ:
#   - `caption_vi`: Mô tả khung cảnh bằng tiếng Việt tự nhiên, chuẩn văn phong đời sống và giao thông Việt Nam.
#   - `caption_en`: Mô tả chi tiết các thực thể, bối cảnh, màu sắc và hành động bằng tiếng Anh.
# - Xuất ra tệp `ground_truth_draft.json` và gói tệp `thumbnails_review.zip` (hoặc tệp JSON nhúng sẵn base64) để nạp vào giao diện Web kiểm duyệt trên màn hình lớn.

# %% [code]
# ==============================================================================
# BUOC 0: CAI DAT THU VIEN VLM CAN THIET
# ==============================================================================
!pip install -q transformers torch torchvision pillow numpy pandas tqdm accelerate
!pip install -q qwen-vl-utils einops timm flash-attn --no-build-isolation || true

# %% [code]
# ==============================================================================
# 1. HẰNG SỐ & THIẾT LẬP MÔI TRƯỜNG
# ==============================================================================
import os
import sys
import io
import json
import zipfile
import base64
import glob
import time
import torch
from PIL import Image
from tqdm import tqdm

# Cấu hình số lượng mẫu Ground Truth cần sinh
NUM_SAMPLES = 200  # Đề xuất: 200 - 500 mẫu cho benchmark chuẩn
IMAGE_SIZE_REVIEW = (384, 384)  # Kích thước thumbnail lưu trữ cho giao diện Web

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"[*] Thiet bi tinh toan: {DEVICE}")

# %% [code]
# ==============================================================================
# 2. TÌM KIẾM VIRTUAL CACHE (.BLOB)
# ==============================================================================
def find_kaggle_blob_path() -> str:
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

BLOB_PATH = find_kaggle_blob_path()
print(f"[*] Tim thay tep Virtual Cache: {BLOB_PATH}")

# %% [code]
# ==============================================================================
# 3. KHOI TAO MO HINH VLM GENERATOR (QWEN2-VL & FLORENCE-2)
# ==============================================================================
class VLMAutoCaptioner:
    def __init__(self, device: str = "cuda"):
        self.device = device
        self.qwen_model = None
        self.qwen_processor = None
        self.florence_model = None
        self.florence_processor = None
        self._init_models()

    def _init_models(self):
        print("[+] Dang khoi tao Qwen2-VL-2B-Instruct cho tieng Viet...")
        try:
            from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
            self.qwen_processor = AutoProcessor.from_pretrained("Qwen/Qwen2-VL-2B-Instruct")
            self.qwen_model = Qwen2VLForConditionalGeneration.from_pretrained(
                "Qwen/Qwen2-VL-2B-Instruct",
                torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
                device_map="auto" if torch.cuda.is_available() else None
            ).eval()
            print("[+] Khoi tao Qwen2-VL-2B-Instruct thanh cong.")
        except Exception as e:
            print(f"[!] Khong the khoi tao Qwen2-VL: {e}. Se su dung fallback.")

        print("[+] Dang khoi tao Florence-2-large cho tieng Anh...")
        try:
            from transformers import AutoModelForCausalLM, AutoProcessor
            self.florence_processor = AutoProcessor.from_pretrained("microsoft/Florence-2-large", trust_remote_code=True)
            self.florence_model = AutoModelForCausalLM.from_pretrained(
                "microsoft/Florence-2-large",
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                trust_remote_code=True
            ).to(self.device).eval()
            print("[+] Khoi tao Florence-2-large thanh cong.")
        except Exception as e:
            print(f"[!] Khong the khoi tao Florence-2: {e}.")

    @torch.no_grad()
    def generate_caption_vi(self, image: Image.Image) -> str:
        """Sinh mô tả tiếng Việt chi tiết từ Qwen2-VL."""
        if self.qwen_model is None:
            return "Khung cảnh trong video với các hoạt động và đối tượng chi tiết."
        try:
            from qwen_vl_utils import process_vision_info
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {
                            "type": "text",
                            "text": "Hãy miêu tả ngắn gọn nhưng đầy đủ các chi tiết thị giác trong bức ảnh này bằng một câu tiếng Việt tự nhiên (chú ý chủ thể chính, trang phục, hành động, bối cảnh xung quanh và màu sắc nổi bật):"
                        }
                    ]
                }
            ]
            text_prompt = self.qwen_processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            image_inputs, video_inputs = process_vision_info(messages)
            inputs = self.qwen_processor(
                text=[text_prompt],
                images=image_inputs,
                videos=video_inputs,
                padding=True,
                return_tensors="pt"
            ).to(self.device)
            
            generated_ids = self.qwen_model.generate(**inputs, max_new_tokens=128)
            generated_ids_trimmed = [
                out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
            ]
            output_text = self.qwen_processor.batch_decode(
                generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
            )[0].strip()
            return output_text
        except Exception as e:
            return f"Khung cảnh video tại khoảnh khắc sự kiện (Lỗi sinh VLM: {e})"

    @torch.no_grad()
    def generate_caption_en(self, image: Image.Image) -> str:
        """Sinh mô tả tiếng Anh chi tiết từ Florence-2 hoặc Qwen2-VL."""
        if self.florence_model is not None:
            try:
                prompt = "<MORE_DETAILED_CAPTION>"
                inputs = self.florence_processor(text=prompt, images=image, return_tensors="pt").to(self.device)
                if torch.cuda.is_available():
                    inputs["pixel_values"] = inputs["pixel_values"].to(torch.float16)
                generated_ids = self.florence_model.generate(
                    input_ids=inputs["input_ids"],
                    pixel_values=inputs["pixel_values"],
                    max_new_tokens=128,
                    num_beams=3
                )
                generated_text = self.florence_processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
                parsed_answer = self.florence_processor.post_process_generation(
                    generated_text, task=prompt, image_size=(image.width, image.height)
                )
                return parsed_answer.get("<MORE_DETAILED_CAPTION>", "").strip()
            except Exception as e_florence:
                pass
                
        # Fallback sang Qwen2-VL nếu Florence-2 gặp sự cố
        if self.qwen_model is not None:
            try:
                from qwen_vl_utils import process_vision_info
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image", "image": image},
                            {"type": "text", "text": "Describe the main visual content, entities, background and actions in this image in one detailed English sentence:"}
                        ]
                    }
                ]
                text_prompt = self.qwen_processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                image_inputs, video_inputs = process_vision_info(messages)
                inputs = self.qwen_processor(text=[text_prompt], images=image_inputs, padding=True, return_tensors="pt").to(self.device)
                generated_ids = self.qwen_model.generate(**inputs, max_new_tokens=128)
                generated_ids_trimmed = [out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)]
                return self.qwen_processor.batch_decode(generated_ids_trimmed, skip_special_tokens=True)[0].strip()
            except Exception:
                pass
                
        return "A detailed visual keyframe scene with people and surrounding background."

# %% [code]
# ==============================================================================
# 4. THỰC THI QUÉT .BLOB VÀ TẠO BỘ DỮ LIỆU GROUND TRUTH
# ==============================================================================
def run_vlm_ground_truth_pipeline(blob_path: str, num_samples: int = 200, output_dir: str = "/kaggle/working"):
    os.makedirs(output_dir, exist_ok=True)
    if not blob_path or not os.path.exists(blob_path):
        print(f"[!] Khong tim thay tep .blob hop le tai: {blob_path}")
        return
        
    captioner = VLMAutoCaptioner(device=DEVICE)
    
    print(f"[*] Dang mo Virtual Cache: {blob_path}...")
    zf = zipfile.ZipFile(blob_path, 'r')
    exts = ('.jpg', '.jpeg', '.png', '.webp')
    all_imgs = [info.filename for info in zf.infolist() if info.filename.lower().endswith(exts)]
    
    # Lấy mẫu phân bố đều theo toàn bộ danh sách keyframe
    step = max(1, len(all_imgs) // num_samples)
    sampled_names = all_imgs[::step][:num_samples]
    
    print(f"[*] Tong so keyframes: {len(all_imgs)} -> Lay mau: {len(sampled_names)} anh de sinh Semantic Ground Truth.")
    
    records = []
    thumbnails_zip_path = os.path.join(output_dir, "thumbnails_review.zip")
    
    with zipfile.ZipFile(thumbnails_zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zip_out:
        for idx, img_name in enumerate(tqdm(sampled_names, desc="VLM Generating Captions")):
            img_data = zf.read(img_name)
            img = Image.open(io.BytesIO(img_data)).convert("RGB")
            
            # 1. Sinh Caption ngữ nghĩa
            cap_vi = captioner.generate_caption_vi(img)
            cap_en = captioner.generate_caption_en(img)
            
            # 2. Tạo thumbnail nhỏ để nhúng trực tiếp hoặc lưu zip
            thumb = img.copy()
            thumb.thumbnail(IMAGE_SIZE_REVIEW)
            thumb_buffer = io.BytesIO()
            thumb.save(thumb_buffer, format="JPEG", quality=85)
            thumb_bytes = thumb_buffer.getvalue()
            
            thumb_rel_path = f"thumbnails/{os.path.basename(img_name)}"
            zip_out.writestr(thumb_rel_path, thumb_bytes)
            
            # Base64 thumbnail nhúng thẳng để xem trực tiếp không cần giải nén ảnh
            b64_str = f"data:image/jpeg;base64,{base64.b64encode(thumb_bytes).decode('utf-8')}"
            
            base_name = os.path.splitext(os.path.basename(img_name))[0]
            parts = base_name.split("_")
            vid_id = "_".join(parts[:2]) if len(parts) >= 2 else base_name
            k_id = parts[-1] if len(parts) >= 3 else f"{idx+1:05d}"
            
            record = {
                "id": idx + 1,
                "video_id": vid_id,
                "keyframe_id": k_id,
                "image_path": img_name,
                "caption_vi": cap_vi,
                "caption_en": cap_en,
                "thumbnail_b64": b64_str
            }
            records.append(record)
            
    zf.close()
    
    # 3. Xuất tệp JSON bản nháp
    draft_json_path = os.path.join(output_dir, "ground_truth_draft.json")
    with open(draft_json_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        
    print(f"\n[+] DA HOAN TAT SINH SEMANTIC GROUND TRUTH!")
    print(f"[*] File JSON ban nhap: {draft_json_path}")
    print(f"[*] File Zip Thumbnails: {thumbnails_zip_path}")
    print(f"[*] Hay tai tep 'ground_truth_draft.json' ve may va mo file 'ground_truth_curator.html' de kiem duyet!")

if __name__ == "__main__":
    out_dir = "/kaggle/working" if os.path.exists("/kaggle/working") else os.path.join("..", "..", "data")
    run_vlm_ground_truth_pipeline(BLOB_PATH, num_samples=NUM_SAMPLES, output_dir=out_dir)
