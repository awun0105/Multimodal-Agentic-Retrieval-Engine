"""Phase01 model trial: ASR, image embeddings, text embeddings, OCR.

Runs as a Kaggle script kernel (GPU T4). Reads public Hugging Face data only and
writes results to the kernel output directory. Plan:
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

RAW_REPO = "1thesudden/AIOU26_raw"
RELEASE_REPO = "1thesudden/AIOU26_release"
VIDEOS = {
    "L30_V030": "canonical_release_v001/phase01_structure/artifacts/batch_002_gpu1/L30_V030_structure.zip",
    "L25_V085": "canonical_release_v001/phase01_structure/artifacts/batch_002_gpu0/L25_V085_structure.zip",
}

# Ground truth is a set of shot indexes; any keyframe in those shots counts.
QUERIES = [
    ("L30_V030", [4, 5, 8], "thầy giáo chỉ vào phép cộng 764 cộng 146 trên bảng xanh",
     "a teacher points at the addition 764 plus 146 on a green chalkboard"),
    ("L30_V030", [5, 21, 25, 26], "bé gái thắt nơ hồng viết lên bảng bên cạnh thầy giáo",
     "a girl with a pink hair bow writes on the board next to the teacher"),
    ("L30_V030", [10, 11, 12, 13], "hai em nhỏ mặc áo vàng cùng đọc truyện tranh ở bàn học",
     "two children in yellow shirts read a comic book together at a desk"),
    ("L30_V030", [6, 9, 14, 22, 27, 29, 33, 39, 47], "thầy giáo trẻ áo xanh đậm đeo dây thẻ trả lời phỏng vấn",
     "a young teacher in a dark blue shirt with a lanyard gives an interview"),
    ("L30_V030", [17], "cậu bé đeo kính mặc áo sọc vàng xanh đang cúi xuống viết bài",
     "a boy with glasses in a yellow and blue striped shirt writes at his desk"),
    ("L30_V030", [0], "logo Tuổi Trẻ TV trên nền trắng",
     "the Tuoi Tre TV logo on a white background"),
    ("L30_V030", [40, 42, 43], "nữ sinh đeo kính trả lời phỏng vấn, chú thích tên Phạm Thiên Kim",
     "a schoolgirl with glasses gives an interview, caption Pham Thien Kim"),
    ("L30_V030", [30, 37], "lớp học có bản đồ Việt Nam trên tường, học sinh ngồi quanh bàn dài",
     "a classroom with a map of Vietnam on the wall and students around a long table"),
    ("L25_V085", [1], "bìa bài giảng ôn tập vật lý dao động điều hòa con lắc lò xo",
     "title slide of a physics review lesson on harmonic oscillation and spring pendulum"),
    ("L25_V085", [4, 5], "tòa nhà trường đại học quốc tế Sài Gòn có cột cờ phía trước",
     "the Saigon International University building with flagpoles in front"),
    ("L25_V085", [10, 11], "robot màu cam trắng đứng cạnh sinh viên",
     "an orange and white robot standing next to students"),
    ("L25_V085", [25], "các đầu bếp đội mũ trắng đang nấu ăn trong bếp",
     "chefs in white hats cooking in a kitchen"),
    ("L25_V085", [28, 29], "người mặc áo choàng tốt nghiệp đỏ phát biểu sau bục có hoa vàng",
     "a person in a red graduation gown speaks at a podium with yellow flowers"),
    ("L25_V085", [36], "học sinh đang bơi trong hồ bơi",
     "students swimming in a pool"),
    ("L25_V085", [77, 78], "nữ sinh nhìn qua kính hiển vi trong phòng thí nghiệm",
     "a female student looks through a microscope in a laboratory"),
    ("L25_V085", [81, 83, 84], "học sinh chơi đàn violin và piano",
     "students playing violin and piano"),
    ("L25_V085", [45], "sinh viên tốt nghiệp tung mũ lên trời",
     "graduates throwing their caps into the air"),
    ("L25_V085", [71, 72], "bé gái mặc áo đỏ đang ăn bánh",
     "a girl in a red shirt eating a pastry"),
    ("L25_V085", [21, 40], "nhiều người đứng trên sân khấu giơ tập hồ sơ đỏ trong lễ ký kết",
     "several people on a stage hold up red folders at a signing ceremony"),
    ("L25_V085", [32], "trao tặng quỹ học bổng tài năng trẻ bằng tấm bảng lớn",
     "presenting a young talent scholarship fund with a large board"),
]

RESULTS: dict = {"timings_sec": {}, "errors": {}, "metrics": {}, "env": {}}


def save() -> None:
    (OUT / "results.json").write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2))


def stage(name):
    def wrap(fn):
        def run(*args, **kwargs):
            print(f"=== {name}", flush=True)
            start = time.time()
            try:
                return fn(*args, **kwargs)
            except Exception:
                RESULTS["errors"][name] = traceback.format_exc()[-4000:]
                print(RESULTS["errors"][name], flush=True)
                return None
            finally:
                RESULTS["timings_sec"][name] = round(time.time() - start, 1)
                save()
                free_gpu()
        return run
    return wrap


def pip(*packages: str) -> None:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *packages], check=True)


def free_gpu() -> None:
    gc.collect()
    try:
        import torch
        torch.cuda.empty_cache()
    except Exception:
        pass


def as_tensor(output):
    return output if hasattr(output, "shape") else output.pooler_output


@stage("setup")
def setup() -> None:
    pip("-U", "transformers", "sentence-transformers", "huggingface_hub", "chunkformer")
    import torch
    RESULTS["env"] = {
        "python": sys.version,
        "torch": torch.__version__,
        "cuda": torch.cuda.is_available(),
        "gpus": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())],
    }


@stage("download")
def download() -> dict:
    from huggingface_hub import hf_hub_download
    import pandas as pd

    data = {}
    for video_id, zip_path in VIDEOS.items():
        mp4 = hf_hub_download(RAW_REPO, f"canonical_raw_v001/raw_videos/{video_id}.mp4",
                              repo_type="dataset", local_dir=WORK)
        bundle = hf_hub_download(RELEASE_REPO, zip_path, repo_type="dataset", local_dir=WORK)
        with zipfile.ZipFile(bundle) as archive:
            archive.extractall(WORK / "structure")
        root = WORK / "structure" / video_id
        keyframes = pd.read_parquet(root / "keyframes.parquet").sort_values("timestamp_sec")
        keyframes["path"] = [str(root / "keyframes" / Path(ref).name) for ref in keyframes["keyframe_ref"]]
        wav = WORK / f"{video_id}.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp4, "-ac", "1", "-ar", "16000", str(wav)],
                       check=True)
        data[video_id] = {"root": root, "keyframes": keyframes, "wav": wav}
    return data


def ranking_metrics(scores, item_shots, queries) -> dict:
    import numpy as np

    ranks = []
    for row, (_, gt, *_rest) in zip(scores, queries):
        order = np.argsort(-row)
        hit = next(i for i, idx in enumerate(order) if item_shots[idx] in gt)
        ranks.append(hit + 1)
    ranks = np.array(ranks)
    return {"R@1": float((ranks <= 1).mean()), "R@5": float((ranks <= 5).mean()),
            "R@10": float((ranks <= 10).mean()), "MRR": float((1 / ranks).mean()),
            "ranks": ranks.tolist()}


def queries_for(video_id: str):
    return [(q[0], {f"{q[0]}_SH{i:05d}" for i in q[1]}, q[2], q[3]) for q in QUERIES if q[0] == video_id]


@stage("asr_chunkformer")
def asr_chunkformer(data) -> None:
    from chunkformer import ChunkFormerModel

    model = ChunkFormerModel.from_pretrained("khanhld/chunkformer-ctc-large-vie")
    out = {}
    for video_id, item in data.items():
        start = time.time()
        result = model.endless_decode(audio_path=str(item["wav"]), chunk_size=64, left_context_size=128,
                                      right_context_size=128, total_batch_duration=14400,
                                      return_timestamps=True)
        out[video_id] = {"seconds": round(time.time() - start, 1), "result": result}
    (OUT / "asr_chunkformer.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    del model


@stage("asr_phowhisper")
def asr_phowhisper(data) -> None:
    import torch
    from transformers import pipeline

    # Second T4: the first GPU still holds earlier trial models.
    asr = pipeline("automatic-speech-recognition", model="vinai/PhoWhisper-large",
                   torch_dtype=torch.float16, device=1 if torch.cuda.device_count() > 1 else 0)
    out = {}
    for video_id, item in data.items():
        start = time.time()
        result = asr(str(item["wav"]), chunk_length_s=30, batch_size=8, return_timestamps=True)
        out[video_id] = {"seconds": round(time.time() - start, 1), "result": result}
    (OUT / "asr_phowhisper.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    del asr


def evaluate_image_model(name, embed_images, embed_texts, data) -> None:
    import numpy as np

    report = {"per_video": {}}
    all_vecs, all_shots, all_queries = [], [], []
    start = time.time()
    count = 0
    for video_id, item in data.items():
        vectors = embed_images(list(item["keyframes"]["path"]))
        count += len(vectors)
        all_vecs.append(vectors)
        all_shots += list(item["keyframes"]["shot_id"])
        all_queries += queries_for(video_id)
    report["image_seconds_per_keyframe"] = round((time.time() - start) / count, 4)
    vecs = np.concatenate(all_vecs)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    for lang, column in (("vi", 2), ("en", 3)):
        start = time.time()
        q = embed_texts([query[column] for query in all_queries])
        report[f"text_seconds_per_query_{lang}"] = round((time.time() - start) / len(all_queries), 4)
        q /= np.linalg.norm(q, axis=1, keepdims=True)
        report[f"combined_{lang}"] = ranking_metrics(q @ vecs.T, all_shots, all_queries)
    RESULTS["metrics"][name] = report
    print(name, {k: v for k, v in report.items() if "combined" in k}, flush=True)


@stage("img_clip_multilingual")
def img_clip_multilingual(data) -> None:
    from PIL import Image
    from sentence_transformers import SentenceTransformer

    image_model = SentenceTransformer("clip-ViT-B-32", device="cuda")
    text_model = SentenceTransformer("sentence-transformers/clip-ViT-B-32-multilingual-v1", device="cuda")
    evaluate_image_model(
        "img_clip_multilingual",
        lambda paths: image_model.encode([Image.open(p).convert("RGB") for p in paths], batch_size=64),
        lambda texts: text_model.encode(texts),
        data,
    )


def siglip2(model_id: str, data) -> None:
    import numpy as np
    import torch
    from PIL import Image
    from transformers import AutoModel, AutoProcessor

    model = AutoModel.from_pretrained(model_id, torch_dtype=torch.float16).to("cuda").eval()
    processor = AutoProcessor.from_pretrained(model_id)

    def images(paths):
        out = []
        for i in range(0, len(paths), 32):
            batch = [Image.open(p).convert("RGB") for p in paths[i:i + 32]]
            inputs = processor(images=batch, return_tensors="pt").to("cuda")
            inputs["pixel_values"] = inputs["pixel_values"].half()
            with torch.no_grad():
                out.append(as_tensor(model.get_image_features(**inputs)).float().cpu().numpy())
        return np.concatenate(out)

    def texts(items):
        inputs = processor(text=items, padding="max_length", max_length=64, truncation=True,
                           return_tensors="pt").to("cuda")
        with torch.no_grad():
            return as_tensor(model.get_text_features(**inputs)).float().cpu().numpy()

    evaluate_image_model(f"img_{model_id.split('/')[-1]}", images, texts, data)
    del model


@stage("img_siglip2_base")
def img_siglip2_base(data) -> None:
    siglip2("google/siglip2-base-patch16-256", data)


@stage("img_siglip2_so400m")
def img_siglip2_so400m(data) -> None:
    siglip2("google/siglip2-so400m-patch14-384", data)


def caption_documents(data):
    import pandas as pd

    docs, shots, queries = [], [], []
    for video_id, item in data.items():
        captions = pd.read_parquet(item["root"] / "shot_captions.parquet")
        docs += list(captions["caption_vi"].fillna(""))
        shots += list(captions["shot_id"])
        queries += queries_for(video_id)
    return docs, shots, queries


def evaluate_text_model(name, encode_docs, encode_queries, data) -> None:
    import numpy as np

    docs, shots, queries = caption_documents(data)
    start = time.time()
    d = np.asarray(encode_docs(docs), dtype="float32")
    doc_seconds = time.time() - start
    start = time.time()
    q = np.asarray(encode_queries([query[2] for query in queries]), dtype="float32")
    query_seconds = time.time() - start
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    report = {"captions_vi": ranking_metrics(q @ d.T, shots, queries),
              "doc_seconds_per_item": round(doc_seconds / len(docs), 4),
              "query_seconds_per_item": round(query_seconds / len(queries), 4)}
    RESULTS["metrics"][name] = report
    print(name, report["captions_vi"], flush=True)


@stage("txt_bge_m3")
def txt_bge_m3(data) -> None:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("BAAI/bge-m3", device="cuda")
    evaluate_text_model("txt_bge_m3", model.encode, model.encode, data)
    del model


@stage("txt_multilingual_e5_large")
def txt_me5(data) -> None:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("intfloat/multilingual-e5-large", device="cuda")
    evaluate_text_model("txt_multilingual_e5_large",
                        lambda docs: model.encode([f"passage: {d}" for d in docs]),
                        lambda qs: model.encode([f"query: {q}" for q in qs]), data)
    del model


@stage("txt_qwen3_embedding_0_6b")
def txt_qwen3(data) -> None:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("Qwen/Qwen3-Embedding-0.6B", device="cuda")
    evaluate_text_model("txt_qwen3_embedding_0_6b", model.encode,
                        lambda qs: model.encode(qs, prompt_name="query"), data)
    del model


@stage("ocr_paddle")
def ocr_paddle(data) -> None:
    pip("paddlepaddle", "paddleocr")
    from paddleocr import PaddleOCR

    # oneDNN fails on the PIR executor in paddlepaddle 3.x CPU builds.
    ocr = PaddleOCR(lang="vi", use_doc_orientation_classify=False, use_doc_unwarping=False,
                    use_textline_orientation=False, enable_mkldnn=False)
    out = {}
    for video_id, item in data.items():
        rows = []
        start = time.time()
        for path in item["keyframes"]["path"]:
            texts = []
            for result in ocr.predict(path):
                texts += [t for t, s in zip(result["rec_texts"], result["rec_scores"]) if s >= 0.5]
            rows.append({"keyframe": Path(path).name, "text": " ".join(texts)})
        elapsed = time.time() - start
        counts: dict[str, int] = {}
        for row in rows:
            for line in set(row["text"].split("  ")):
                counts[line] = counts.get(line, 0) + 1
        out[video_id] = {
            "seconds_per_keyframe_cpu": round(elapsed / len(rows), 3),
            "non_empty": sum(bool(r["text"]) for r in rows),
            "keyframes": len(rows),
            "rows": rows,
        }
    (OUT / "ocr_paddle.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))


# Version 1 ran every trial; version 2 reruns the two that failed.
RUN_TRIALS = (asr_phowhisper, ocr_paddle)


def main() -> None:
    setup()
    data = download()
    if data is None:
        return
    for trial in RUN_TRIALS:
        trial(data)
    print(json.dumps({k: RESULTS[k] for k in ("timings_sec", "metrics")}, ensure_ascii=False)[:6000])
    print("errors:", list(RESULTS["errors"]))


if __name__ == "__main__":
    main()
