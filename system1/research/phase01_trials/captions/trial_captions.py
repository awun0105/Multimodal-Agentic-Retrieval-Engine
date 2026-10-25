"""Phase01 model trial: one constrained caption call per shot.

Runs as a Kaggle script kernel (GPU T4). Compares Qwen3-VL-4B and 2B with
JSON-schema constrained decoding (xgrammar) against prompt-only JSON. Reads
public Hugging Face data only. Plan:
docs/plans/active/system1-pipeline-simplification.md, Step 3.
"""

from __future__ import annotations

import gc
import json
import os
import subprocess
import sys
import time
import traceback
import zipfile
from pathlib import Path

OUT = Path(os.environ.get("TRIAL_OUT", "/kaggle/working"))
WORK = Path(os.environ.get("TRIAL_WORK", "/kaggle/temp/trial"))
OUT.mkdir(parents=True, exist_ok=True)
WORK.mkdir(parents=True, exist_ok=True)

RELEASE_REPO = "1thesudden/AIOU26_release"
VIDEOS = {
    "L30_V030": "canonical_release_v001/phase01_structure/artifacts/batch_002_gpu1/L30_V030_structure.zip",
    "L25_V085": "canonical_release_v001/phase01_structure/artifacts/batch_002_gpu0/L25_V085_structure.zip",
}
SHOTS_PER_VIDEO = 20
MAX_IMAGE_SIDE = 768

SCHEMA = {
    "type": "object",
    "properties": {
        "caption": {"type": "string", "minLength": 20, "maxLength": 400},
        "objects": {"type": "array", "items": {"type": "string", "maxLength": 40}, "maxItems": 12},
        "actions": {"type": "array", "items": {"type": "string", "maxLength": 60}, "maxItems": 6},
        "visible_text": {"type": "string", "maxLength": 300},
    },
    "required": ["caption", "objects", "actions", "visible_text"],
    "additionalProperties": False,
}

PROMPT = """Describe this video frame for a search index. Answer in Vietnamese.

Return one JSON object with these keys:
- caption: one or two sentences about who is visible, what they do, where, and notable details (clothing, colors, objects).
- objects: short names of the main visible objects.
- actions: short phrases for visible actions.
- visible_text: text that is clearly readable in the frame, or an empty string.

Describe only what is visible. Do not guess names, intentions, or events outside the frame.

Example:
{"caption": "Một người đàn ông mặc áo sơ mi trắng đứng trước bảng xanh, tay chỉ vào phép tính viết bằng phấn.", "objects": ["bảng xanh", "phấn", "áo sơ mi trắng"], "actions": ["chỉ vào bảng"], "visible_text": "764 + 146"}"""

# Version 1: batch size 1, constrained vs prompt-only. Version 2: batched throughput.
MODELS = [
    ("Qwen/Qwen3-VL-2B-Instruct", True, 8),
    ("Qwen/Qwen3-VL-4B-Instruct", True, 8),
]

RESULTS: dict = {"timings_sec": {}, "errors": {}, "metrics": {}, "env": {}}


def save() -> None:
    (OUT / "results.json").write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2))


def free_gpu() -> None:
    gc.collect()
    try:
        import torch
        torch.cuda.empty_cache()
    except Exception:
        pass


def setup() -> None:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "transformers", "accelerate",
                    "xgrammar", "huggingface_hub"], check=True)
    import torch
    RESULTS["env"] = {"python": sys.version, "torch": torch.__version__,
                      "gpus": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]}


def shots() -> list[dict]:
    import pandas as pd
    from huggingface_hub import hf_hub_download

    items = []
    for video_id, zip_path in VIDEOS.items():
        bundle = hf_hub_download(RELEASE_REPO, zip_path, repo_type="dataset", local_dir=WORK)
        with zipfile.ZipFile(bundle) as archive:
            archive.extractall(WORK / "structure")
        root = WORK / "structure" / video_id
        keyframes = pd.read_parquet(root / "keyframes.parquet")
        middle = keyframes[keyframes["keyframe_role"] == "middle"].sort_values("timestamp_sec")
        old = pd.read_parquet(root / "shot_captions.parquet").set_index("shot_id")["caption_vi"]
        for row in middle.head(SHOTS_PER_VIDEO).itertuples():
            items.append({"shot_id": row.shot_id,
                          "path": str(root / "keyframes" / Path(row.keyframe_ref).name),
                          "old_caption_vi": old.get(row.shot_id)})
    return items


def check_content(payload: dict) -> list[str]:
    problems = []
    caption = payload.get("caption", "")
    if "<" in caption or "caption" in caption.lower():
        problems.append("prompt_echo")
    if caption.startswith(("Hình ảnh hiển thị", "Bức ảnh", "Hình ảnh cho thấy")):
        problems.append("generic_opening")
    if len(caption) < 20:
        problems.append("too_short")
    return problems


def run_model(model_id: str, constrained: bool, items: list[dict], batch_size: int = 1) -> None:
    import torch
    from PIL import Image
    from transformers import AutoModelForImageTextToText, AutoProcessor

    name = f"{model_id.split('/')[-1]}_{'constrained' if constrained else 'prompt_only'}_b{batch_size}"
    print("===", name, flush=True)
    start_load = time.time()
    model = AutoModelForImageTextToText.from_pretrained(model_id, dtype=torch.float16, device_map="cuda")
    processor = AutoProcessor.from_pretrained(model_id)
    processor.tokenizer.padding_side = "left"
    load_seconds = time.time() - start_load

    compiled = None
    if constrained:
        import xgrammar as xgr
        vocab_size = model.get_output_embeddings().weight.shape[0]
        info = xgr.TokenizerInfo.from_huggingface(processor.tokenizer, vocab_size=vocab_size)
        compiled = xgr.GrammarCompiler(info).compile_json_schema(json.dumps(SCHEMA))

    rows, elapsed = [], 0.0
    for offset in range(0, len(items), batch_size):
        batch = items[offset:offset + batch_size]
        conversations = []
        for item in batch:
            image = Image.open(item["path"]).convert("RGB")
            image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
            conversations.append([{"role": "user", "content": [{"type": "image", "image": image},
                                                               {"type": "text", "text": PROMPT}]}])
        inputs = processor.apply_chat_template(conversations, tokenize=True, add_generation_prompt=True,
                                               padding=True, return_dict=True,
                                               return_tensors="pt").to(model.device)
        kwargs = {"max_new_tokens": 700, "do_sample": False}
        if compiled is not None:
            import xgrammar as xgr
            kwargs["logits_processor"] = [xgr.contrib.hf.LogitsProcessor(compiled)]
        start = time.time()
        with torch.no_grad():
            output = model.generate(**inputs, **kwargs)
        elapsed += time.time() - start
        texts = processor.batch_decode(output[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        for item, text in zip(batch, texts):
            try:
                payload = json.loads(text)
                valid = all(key in payload for key in SCHEMA["required"])
            except json.JSONDecodeError:
                payload, valid = {}, False
            rows.append({**item, "raw": text, "valid": valid, "payload": payload,
                         "problems": check_content(payload) if valid else ["invalid_json"]})

    RESULTS["metrics"][name] = {
        "load_seconds": round(load_seconds, 1),
        "seconds_per_shot": round(elapsed / len(items), 2),
        "valid_json_rate": sum(r["valid"] for r in rows) / len(rows),
        "problem_counts": {p: sum(p in r["problems"] for r in rows)
                           for p in ("invalid_json", "prompt_echo", "generic_opening", "too_short")},
        "gpu_peak_gb": round(torch.cuda.max_memory_allocated() / 1e9, 2),
    }
    (OUT / f"captions_{name}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    print(name, RESULTS["metrics"][name], flush=True)
    del model
    torch.cuda.reset_peak_memory_stats()


def main() -> None:
    try:
        setup()
        items = shots()
    except Exception:
        RESULTS["errors"]["setup"] = traceback.format_exc()[-4000:]
        save()
        raise
    for model_id, constrained, batch_size in MODELS:
        start = time.time()
        key = f"{model_id}:{constrained}:b{batch_size}"
        try:
            run_model(model_id, constrained, items, batch_size)
        except Exception:
            RESULTS["errors"][key] = traceback.format_exc()[-4000:]
            print(RESULTS["errors"][key], flush=True)
        RESULTS["timings_sec"][key] = round(time.time() - start, 1)
        save()
        free_gpu()
    print(json.dumps(RESULTS["metrics"], ensure_ascii=False))
    print("errors:", list(RESULTS["errors"]))


if __name__ == "__main__":
    main()
