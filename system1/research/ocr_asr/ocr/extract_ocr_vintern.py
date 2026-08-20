import os
import sys
import sqlite3
import torch
import torchvision.transforms as T
from PIL import Image
from torchvision.transforms.functional import InterpolationMode
import numpy as np
import time
from pathlib import Path
from tqdm import tqdm
from transformers import AutoModel, AutoTokenizer

# Standard ImageNet normalization parameters
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)

def build_transform(input_size):
    return T.Compose([
        T.Lambda(lambda img: img.convert('RGB') if img.mode != 'RGB' else img),
        T.Resize((input_size, input_size), interpolation=InterpolationMode.BICUBIC),
        T.ToTensor(),
        T.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD)
    ])

def find_closest_aspect_ratio(aspect_ratio, target_ratios, width, height, image_size):
    best_ratio_diff = float('inf')
    best_ratio = (1, 1)
    area = width * height
    for ratio in target_ratios:
        target_aspect_ratio = ratio[0] / ratio[1]
        ratio_diff = abs(aspect_ratio - target_aspect_ratio)
        if ratio_diff < best_ratio_diff:
            best_ratio_diff = ratio_diff
            best_ratio = ratio
        elif ratio_diff == best_ratio_diff:
            if area > 0.5 * image_size * image_size * ratio[0] * ratio[1]:
                best_ratio = ratio
    return best_ratio

def dynamic_preprocess(image, min_num=1, max_num=6, image_size=448, use_thumbnail=False):
    orig_width, orig_height = image.size
    aspect_ratio = orig_width / orig_height
    target_ratios = set(
        (i, j) for n in range(min_num, max_num + 1)
        for i in range(1, n + 1) for j in range(1, n + 1)
        if i * j <= max_num and i * j >= min_num
    )
    target_ratios = sorted(list(target_ratios), key=lambda x: x[0] * x[1])
    target_aspect_ratio = find_closest_aspect_ratio(
        aspect_ratio, target_ratios, orig_width, orig_height, image_size
    )
    target_width = image_size * target_aspect_ratio[0]
    target_height = image_size * target_aspect_ratio[1]
    blocks = target_aspect_ratio[0] * target_aspect_ratio[1]
    
    resized_img = image.resize((target_width, target_height))
    processed_images = []
    for i in range(blocks):
        box = (
            (i % target_aspect_ratio[0]) * image_size,
            (i // target_aspect_ratio[0]) * image_size,
            ((i % target_aspect_ratio[0]) + 1) * image_size,
            ((i // target_aspect_ratio[0]) + 1) * image_size
        )
        processed_images.append(resized_img.crop(box))
    if use_thumbnail and len(processed_images) > 1:
        thumbnail_img = image.resize((image_size, image_size))
        processed_images.append(thumbnail_img)
    return processed_images

def load_image(image_file, input_size=448, max_num=6):
    image = Image.open(image_file).convert('RGB')
    transform = build_transform(input_size=input_size)
    images = dynamic_preprocess(image, image_size=input_size, use_thumbnail=True, max_num=max_num)
    pixel_values = [transform(img) for img in images]
    pixel_values = torch.stack(pixel_values)
    return pixel_values

def main():
    # Setup paths
    sqlite_file = Path("mvp-app/tmp/aiou-cache/aic25-b1-v1/runtime.sqlite")
    data_root = Path("mvp-app/data/releases/aic25-b1-v1")
    
    if not sqlite_file.exists():
        # Fallback to source release database if cache is missing
        sqlite_file = Path("mvp-app/data/releases/aic25-b1-v1/metadata/runtime.sqlite")
        
    if not sqlite_file.exists():
        print(f"Error: Database not found at {sqlite_file}")
        sys.exit(1)
        
    # Check GPU availability
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Running OCR extraction on device: {device.upper()}")
    
    # Load model
    print("Loading Vintern-1B-v3_5 model...")
    try:
        vintern_model = AutoModel.from_pretrained(
            "5CD-AI/Vintern-1B-v3_5",
            torch_dtype=torch.bfloat16 if device == "cuda" else torch.float32,
            low_cpu_mem_usage=True,
            trust_remote_code=True
        ).eval().to(device)
        vintern_tokenizer = AutoTokenizer.from_pretrained(
            "5CD-AI/Vintern-1B-v3_5", 
            trust_remote_code=True, 
            use_fast=False
        )
        print("Vintern-1B-v3_5 loaded successfully!")
    except Exception as e:
        print(f"Failed to load Vintern model: {e}")
        sys.exit(1)

    # Connect to SQLite and fetch keyframes
    conn = sqlite3.connect(sqlite_file)
    conn.row_factory = sqlite3.Row
    
    # Fetch keyframes that do not already have OCR processed (supports resuming)
    query_keyframes = """
        SELECT k.keyframe_id, k.video_id, k.image_relpath 
        FROM keyframes k
        LEFT JOIN ocr_texts o ON k.keyframe_id = o.keyframe_id
        WHERE o.keyframe_id IS NULL
    """
    keyframes = conn.execute(query_keyframes).fetchall()
    print(f"Found {len(keyframes)} keyframes to process.")
    
    if not keyframes:
        print("All keyframes are already processed. Exiting.")
        conn.close()
        return

    # Process keyframes
    inserted_count = 0
    start_time = time.time()
    
    try:
        for idx, kf in enumerate(tqdm(keyframes, desc="OCR processing")):
            kf_id = kf["keyframe_id"]
            video_id = kf["video_id"]
            img_path = data_root / kf["image_relpath"]
            
            if not img_path.exists():
                # Check absolute path fallback
                img_path = Path(kf["image_relpath"])
                
            if not img_path.exists():
                print(f"Warning: Image file not found: {img_path}")
                continue
                
            try:
                # Load and preprocess image
                pixel_values = load_image(str(img_path), max_num=6).to(
                    torch.bfloat16 if device == "cuda" else torch.float32
                ).to(device)
                
                # Chat inference
                question = "<image>\nHãy trích xuất toàn bộ văn bản xuất hiện trong hình ảnh này. Chỉ trả về văn bản thô nhận dạng được, không thêm bớt giải thích gì khác."
                generation_config = dict(max_new_tokens=512, do_sample=False, num_beams=1)
                
                with torch.no_grad():
                    response = vintern_model.chat(vintern_tokenizer, pixel_values, question, generation_config)
                
                extracted_text = response.strip()
                
                # Ghi dữ liệu vào SQLite
                if extracted_text:
                    conn.execute(
                        "INSERT OR REPLACE INTO ocr_texts (keyframe_id, video_id, full_text) VALUES (?, ?, ?)",
                        (kf_id, video_id, extracted_text)
                    )
                    conn.execute(
                        "INSERT OR REPLACE INTO ocr_fts (keyframe_id, full_text) VALUES (?, ?)",
                        (kf_id, extracted_text)
                    )
                    inserted_count += 1
                    
                    # Commit periodically every 50 insertions
                    if inserted_count % 50 == 0:
                        conn.commit()
                        
            except Exception as e:
                print(f"Error processing keyframe {kf_id}: {e}")
                continue
                
    finally:
        conn.commit()
        conn.close()
        
    duration = time.time() - start_time
    print(f"\nOCR extraction completed in {duration:.2f} seconds.")
    print(f"Successfully processed and saved OCR text for {inserted_count} keyframes.")

if __name__ == "__main__":
    main()
