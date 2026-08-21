"""Tien xu ly anh + nap model + chay OCR theo lo, tach khoi extract_ocr_vintern.py de giu <=200 LOC."""
import torch
import torchvision.transforms as T
from PIL import Image
from torchvision.transforms.functional import InterpolationMode
from transformers import AutoModel, AutoTokenizer

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)

QUESTION = ("<image>\nHãy trích xuất toàn bộ văn bản xuất hiện trong hình ảnh này. "
            "Chỉ trả về văn bản thô nhận dạng được, không thêm bớt giải thích gì khác.")
GENERATION_CONFIG = dict(max_new_tokens=512, do_sample=False, num_beams=1)


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


def load_model(device):
    print("Loading Vintern-1B-v3_5 model...")
    dtype = torch.float16 if device == "cuda" else torch.float32
    try:
        model = AutoModel.from_pretrained(
            "5CD-AI/Vintern-1B-v3_5",
            torch_dtype=dtype,
            low_cpu_mem_usage=True,
            trust_remote_code=True,
            attn_implementation="sdpa",
        ).eval().to(device)
        print("Loaded WITH attn_implementation='sdpa'")
    except TypeError as e:
        print(f"sdpa not supported ({e}) - reloading without it")
        model = AutoModel.from_pretrained(
            "5CD-AI/Vintern-1B-v3_5",
            torch_dtype=dtype,
            low_cpu_mem_usage=True,
            trust_remote_code=True,
        ).eval().to(device)
    tokenizer = AutoTokenizer.from_pretrained(
        "5CD-AI/Vintern-1B-v3_5", trust_remote_code=True, use_fast=False
    )
    return model, tokenizer


def chuan_bi_lo(keyframes, batch_size):
    """Sinh tung lo tu danh sach keyframe, lo cuoi co the it hon batch_size."""
    for i in range(0, len(keyframes), batch_size):
        yield keyframes[i:i + batch_size]


def chay_mot_lo(model, tokenizer, device, lo):
    """Nap anh, goi batch_chat; anh hong bi loai khoi lo (khong bo ca lo).

    Tra ve list (kf, text). Lo batch_chat loi thi ha ve chay tung anh de cuu phan lon.
    """
    dtype = torch.float16 if device == "cuda" else torch.float32
    hop_le = []
    pixel_values_list = []
    for kf in lo:
        try:
            pv = load_image(kf["img_path"], max_num=6).to(dtype).to(device)
        except Exception as e:
            print(f"Warning: khong doc duoc anh {kf['img_path']}: {e}")
            continue
        hop_le.append(kf)
        pixel_values_list.append(pv)

    if not hop_le:
        return []

    num_patches_list = [pv.size(0) for pv in pixel_values_list]
    pixel_values = torch.cat(pixel_values_list, dim=0)
    questions = [QUESTION] * len(hop_le)

    try:
        with torch.no_grad():
            responses = model.batch_chat(
                tokenizer, pixel_values,
                num_patches_list=num_patches_list,
                questions=questions,
                generation_config=GENERATION_CONFIG,
            )
        return list(zip(hop_le, responses))
    except Exception as e:
        print(f"Warning: batch_chat that bai cho lo {len(hop_le)} anh ({e}) - ha ve chay tung anh")
        ket_qua = []
        for kf, pv in zip(hop_le, pixel_values_list):
            try:
                with torch.no_grad():
                    text = model.chat(tokenizer, pv, QUESTION, GENERATION_CONFIG)
                ket_qua.append((kf, text))
            except Exception as e2:
                print(f"Error: OCR that bai cho keyframe {kf['keyframe_id']}: {e2}")
        return ket_qua
