# ==========================================
# BƯỚC 1: CÀI ĐẶT THƯ VIỆN & THIẾT LẬP MÔI TRƯỜNG
# ==========================================
try:
    import nemo.collections.asr as nemo_asr
    print("NVIDIA NeMo đã được cài đặt sẵn. Bỏ qua!")
except ImportError:
    print("Đang cài đặt các thư viện bổ trợ...")
    import subprocess
    subprocess.run(["pip", "install", "-q", "huggingface_hub", "soundfile", "pandas", "pyarrow"], check=True)
    subprocess.run(["pip", "install", "-q", "nemo_toolkit[asr]"], check=True)
    print("Cài đặt xong!")

import os
import gc
import json
import wave
import shutil
import bisect
import subprocess
from pathlib import Path
from queue import Queue
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import torch
from huggingface_hub import HfApi, hf_hub_download
from kaggle_secrets import UserSecretsClient
import nemo.collections.asr as nemo_asr

# ==========================================
# BƯỚC 2: CẤU HÌNH THÔNG SỐ
# ==========================================
user_secrets = UserSecretsClient()
HF_TOKEN = user_secrets.get_secret("HF_TOKEN")

INPUT_REPO_ID = "1thesudden/AIOU26_raw"
VIDEO_FOLDER_PREFIX = "canonical_raw_v001/raw_videos/"
TIMELINE_FOLDER_PREFIX = "canonical_raw_v001/frame_timeline/"

# Repo cá nhân của bạn để lưu kết quả (HÃY THAY "YOUR_USERNAME" BẰNG USERNAME HF CỦA BẠN)
OUTPUT_REPO_ID = "pintee0106/aiou26-asr-results" 

# Khôi phục đúng prefix cũ để đồng bộ chung một thư mục
ASR_RESULTS_HF_PREFIX = "canonical_raw_v001/asr_segments/"

# Thư mục lưu kết quả cục bộ và tạm trên Kaggle
OUTPUT_DIR = Path("/kaggle/working/asr_results")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR = Path("/kaggle/tmp/temp_processing")
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# ==========================================
# BƯỚC 3: CÁC HÀM PHỤ TRỢ (Tối ưu RAM)
# ==========================================

def has_audio_stream(video_path) -> bool:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "a",
                "-show_entries", "stream=index", "-of", "json", str(video_path)
            ],
            check=True, capture_output=True, text=True
        )
        payload = json.loads(result.stdout or "{}")
        return bool(payload.get("streams"))
    except Exception:
        return False

def segment_audio_on_disk(video_path, output_pattern):
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-f", "segment", "-segment_time", "30",
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        str(output_pattern)
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

def get_wav_duration(wav_path) -> float:
    with wave.open(str(wav_path), 'rb') as w:
        frames = w.getnframes()
        rate = w.getframerate()
        return frames / float(rate)

def time_range_to_frames(start: float, end: float, timeline: list) -> tuple:
    if not timeline:
        return None, None
    ordered = sorted(timeline, key=lambda row: int(row["frame_id"]))
    timestamps = [float(row["pts_time"]) for row in ordered]
    start_position = max(0, bisect.bisect_right(timestamps, start) - 1)
    end_position = bisect.bisect_left(timestamps, end)
    end_position = min(len(ordered), max(start_position + 1, end_position))
    exclusive_end = (
        int(ordered[end_position]["frame_id"])
        if end_position < len(ordered)
        else int(ordered[-1]["frame_id"]) + 1
    )
    return int(ordered[start_position]["frame_id"]), exclusive_end

# ==========================================
# BƯỚC 4: KHỞI TẠO MÔ HÌNH (1 GPU)
# ==========================================
device = "cuda:0" if torch.cuda.is_available() else "cpu"
print(f"Đang tải NeMo model lên {device}...")
model = nemo_asr.models.ASRModel.from_pretrained("nvidia/parakeet-ctc-0.6b-vi").to(device)
model.eval()

# ==========================================
# BƯỚC 5: ĐỒNG BỘ THÔNG MINH (HỖ TRỢ CẢ 2 ĐƯỜNG DẪN CŨ VÀ MỚI)
# ==========================================
api = HfApi()
api.create_repo(repo_id=OUTPUT_REPO_ID, repo_type="dataset", private=True, exist_ok=True, token=HF_TOKEN)

print("Đang quét danh sách file đầu vào...")
all_input_files = api.list_repo_files(repo_id=INPUT_REPO_ID, repo_type="dataset", token=HF_TOKEN)

print("Đang quét danh sách kết quả trên Repo cá nhân...")
all_completed_files = api.list_repo_files(repo_id=OUTPUT_REPO_ID, repo_type="dataset", token=HF_TOKEN)

# Lọc tất cả các file parquet kết quả cũ (bất kể nằm ở "canonical_raw_v001/asr_segments/" hay "asr_segments/")
completed_parquet_files = [f for f in all_completed_files if f.endswith(".parquet") and "asr_segments/" in f]

print("Đang tải dữ liệu cũ về máy ảo Kaggle làm cache để Skip...")
for f in completed_parquet_files:
    video_id = Path(f).stem
    local_path = OUTPUT_DIR / f"{video_id}.parquet"
    if not local_path.exists():
        try:
            # Tải file từ cache HF và lưu trực tiếp vào thư mục asr_results cục bộ
            downloaded_file = hf_hub_download(
                repo_id=OUTPUT_REPO_ID, filename=f, repo_type="dataset", token=HF_TOKEN
            )
            shutil.copy2(downloaded_file, local_path)
        except Exception as e:
            print(f"Lỗi đồng bộ file {f}: {e}")
            
print(f"Đã đồng bộ {len(list(OUTPUT_DIR.glob('*.parquet')))} file kết quả cũ về Kaggle thành công.")

# ==========================================
# BƯỚC 6: XỬ LÝ TUẦN TỰ
# ==========================================
video_files = [
    f for f in all_input_files 
    if f.startswith(VIDEO_FOLDER_PREFIX) and f.lower().endswith(('.mp4', '.avi', '.wav', '.mkv'))
]
print(f"Bắt đầu quét xử lý {len(video_files)} videos...")

ASR_COLUMNS = [
    "asr_segment_id", "video_id", "start_sec", "end_sec", "start_frame", "end_frame",
    "text", "language", "confidence", "avg_logprob", "no_speech_prob", "provider",
    "model_name", "model_version", "status"
]

SYNC_INTERVAL = 30
newly_processed_count = 0

with torch.inference_mode():
    for idx, f in enumerate(video_files):
        video_id = Path(f).stem
        local_parquet_path = OUTPUT_DIR / f"{video_id}.parquet"
        
        # Kiểm tra nếu file đã có (sau khi tải từ HF về) -> Bỏ qua
        if local_parquet_path.exists():
            print(f"[{idx+1}/{len(video_files)}] Đã có kết quả của {video_id}. Bỏ qua (Skip).")
            continue
            
        print(f"[{idx+1}/{len(video_files)}] Đang xử lý: {video_id}...")
        
        try:
            # 1. Tải video
            local_video_path = hf_hub_download(
                repo_id=INPUT_REPO_ID, filename=f, repo_type="dataset", 
                local_dir=str(TEMP_DIR), token=HF_TOKEN
            )
            
            # Kiểm tra âm thanh
            if not has_audio_stream(local_video_path):
                print(f"-> Video {video_id} không có âm thanh. Đánh dấu hoàn thành rỗng.")
                pd.DataFrame([], columns=ASR_COLUMNS).to_parquet(local_parquet_path, index=False)
                newly_processed_count += 1
                continue
                
            temp_audio_path = TEMP_DIR / f"{video_id}.wav"
            
            # 2. Tải timeline
            timeline_filename = f"{TIMELINE_FOLDER_PREFIX}{video_id}.parquet"
            timeline_rows = []
            if timeline_filename in all_input_files:
                try:
                    local_timeline_path = hf_hub_download(
                        repo_id=INPUT_REPO_ID, filename=timeline_filename, repo_type="dataset", 
                        local_dir=str(TEMP_DIR), token=HF_TOKEN
                    )
                    timeline_df = pd.read_parquet(local_timeline_path)
                    timeline_rows = timeline_df.to_dict("records")
                except Exception:
                    pass
            
            # 3. Cắt âm thanh trên đĩa
            output_pattern = TEMP_DIR / "chunk_%03d.wav"
            segment_audio_on_disk(local_video_path, output_pattern)
            
            chunk_files = sorted(list(TEMP_DIR.glob("chunk_*.wav")))
            chunk_time_ranges = []
            current_start = 0.0
            
            for chunk_path in chunk_files:
                duration = get_wav_duration(chunk_path)
                end_time = current_start + duration
                seg_idx = int(chunk_path.stem.split("_")[-1])
                chunk_time_ranges.append((current_start, end_time, seg_idx))
                current_start = end_time
            
            segments_rows = []
            if chunk_files:
                # 4. Chạy ASR
                with torch.cuda.amp.autocast():
                    transcriptions = model.transcribe([str(p) for p in chunk_files], batch_size=16)
                
                # 5. Ánh xạ kết quả
                for text_res, (start_time, end_time, seg_idx) in zip(transcriptions, chunk_time_ranges):
                    text = text_res if isinstance(text_res, str) else text_res.text
                    text = text.strip()
                    if text:
                        start_frame, end_frame = time_range_to_frames(start_time, end_time, timeline_rows)
                        segments_rows.append({
                            "asr_segment_id": f"{video_id}_ASR{seg_idx:05d}",
                            "video_id": video_id,
                            "start_sec": float(start_time),
                            "end_sec": float(end_time),
                            "start_frame": start_frame,
                            "end_frame": end_frame,
                            "text": text,
                            "language": "vi",
                            "confidence": None,
                            "avg_logprob": None,
                            "no_speech_prob": None,
                            "provider": "nemo",
                            "model_name": "nvidia/parakeet-ctc-0.6b-vi",
                            "model_version": "0.6b",
                            "status": "pass"
                        })
            
            # Ghi file Parquet cục bộ
            pd.DataFrame(segments_rows, columns=ASR_COLUMNS).to_parquet(local_parquet_path, index=False)
            newly_processed_count += 1
            print("-> Thành công!")
            
            # Đồng bộ thư mục định kỳ lên HF
            if newly_processed_count % SYNC_INTERVAL == 0:
                print(f"\n[SYNC] Đang đồng bộ thư mục lẻ lên HF...")
                api.upload_folder(
                    folder_path=str(OUTPUT_DIR), path_in_repo=ASR_RESULTS_HF_PREFIX,
                    repo_id=OUTPUT_REPO_ID, repo_type="dataset", token=HF_TOKEN,
                    commit_message=f"Sync batch - {newly_processed_count} videos"
                )
                print("[SYNC] Thành công!\n")
                
        except Exception as e:
            print(f"❌ LỖI tạm thời xử lý {video_id}: {e}")
            
        finally:
            shutil.rmtree(TEMP_DIR)
            TEMP_DIR.mkdir(parents=True, exist_ok=True)
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

# Đồng bộ đợt cuối
print("\n[SYNC] Đồng bộ đợt cuối lên HF...")
try:
    api.upload_folder(
        folder_path=str(OUTPUT_DIR), path_in_repo=ASR_RESULTS_HF_PREFIX,
        repo_id=OUTPUT_REPO_ID, repo_type="dataset", token=HF_TOKEN,
        commit_message="Final sync before merge"
    )
    print("[SYNC] Đồng bộ thành công!")
except Exception as e:
    print(f"[SYNC] Lỗi đồng bộ đợt cuối: {e}")

# ==========================================
# BƯỚC 7: GỘP KẾT QUẢ CUỐI CÙNG VÀ UPLOAD
# ==========================================
print("\nBắt đầu gộp tất cả các file kết quả lẻ...")
parquet_files = list(OUTPUT_DIR.glob("*.parquet"))
dfs = []
for p in parquet_files:
    try:
        df = pd.read_parquet(p)
        if not df.empty:
            dfs.append(df)
    except Exception:
        pass

if dfs:
    merged_df = pd.concat(dfs, ignore_index=True)
    local_merged_path = Path("/kaggle/working/asr_segments.parquet")
    merged_df.to_parquet(local_merged_path, index=False)
    
    # Upload file tổng lên Repo cá nhân
    api.upload_file(
        path_or_fileobj=str(local_merged_path), path_in_repo="asr_segments.parquet",
        repo_id=OUTPUT_REPO_ID, repo_type="dataset", token=HF_TOKEN
    )
    print("Hoàn thành upload file tổng hợp lên Hugging Face!")
