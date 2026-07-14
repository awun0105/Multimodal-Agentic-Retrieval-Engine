import os
import sys
import tempfile
import argparse
import torch
import soundfile as sf
import easyocr
import nemo.collections.asr as nemo_asr

def run_ocr(image_path: str) -> list:
    """
    Nhận diện văn bản từ hình ảnh sử dụng EasyOCR (chạy trên GPU nếu khả dụng).
    
    Args:
        image_path (str): Đường dẫn đến tệp hình ảnh (.jpg, .png, ...).
        
    Returns:
        list: Danh sách kết quả dạng dict: [{"text": text, "bbox": bbox, "confidence": confidence}]
    """
    print(f"--- Đang chạy EasyOCR trên hình ảnh: {image_path} ---")
    gpu_available = torch.cuda.is_available()
    # Khởi tạo reader cho Tiếng Việt và Tiếng Anh
    reader = easyocr.Reader(["vi", "en"], gpu=gpu_available)
    
    raw_results = reader.readtext(image_path)
    
    formatted_results = []
    for bbox, text, confidence in raw_results:
        # Chuyển đổi định dạng bounding box sang danh sách các điểm (x, y) thông thường
        bbox_list = [[int(coord[0]), int(coord[1])] for coord in bbox]
        formatted_results.append({
            "text": text.strip(),
            "bbox": bbox_list,
            "confidence": float(confidence)
        })
    return formatted_results

def run_asr(audio_path: str) -> list:
    """
    Nhận dạng giọng nói tiếng Việt sử dụng NVIDIA NeMo (parakeet-ctc-0.6b-vi).
    Sử dụng kỹ thuật phân đoạn 30 giây để tránh lỗi tràn bộ nhớ GPU (CUDA Out of Memory).
    
    Args:
        audio_path (str): Đường dẫn đến tệp âm thanh (.wav, cần có tần số 16kHz).
        
    Returns:
        list: Danh sách các câu nhận diện kèm mốc thời gian: [{"start": start_time, "end": end_time, "text": text}]
    """
    print(f"--- Đang chạy NVIDIA NeMo ASR trên tệp âm thanh: {audio_path} ---")
    
    # Khởi tạo mô hình NeMo
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Đang tải mô hình parakeet-ctc-0.6b-vi lên thiết bị: {device}...")
    model = nemo_asr.models.ASRModel.from_pretrained("nvidia/parakeet-ctc-0.6b-vi")
    model = model.to(device)
    
    # Đọc tệp âm thanh
    audio, sr = sf.read(str(audio_path))
    chunk_size = 30 * sr  # Mỗi segment dài tối đa 30 giây
    results = []
    
    print("Bắt đầu xử lý nhận diện theo từng phân đoạn...")
    for i in range(0, len(audio), chunk_size):
        chunk = audio[i : i + chunk_size]
        if len(chunk) < 1.0 * sr:  # Bỏ qua đoạn cuối quá ngắn (< 1s)
            continue
            
        start_time = i / sr
        end_time = min((i + chunk_size) / sr, len(audio) / sr)
        
        # Ghi chunk ra tệp tạm thời để nạp vào NeMo
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
            sf.write(temp_wav.name, chunk, sr)
            temp_name = temp_wav.name
            
        try:
            res = model.transcribe([temp_name])
            # NeMo trả về Hypothesis hoặc danh sách string
            text = res[0] if isinstance(res[0], str) else res[0].text
            text = text.strip()
            if text:
                results.append({
                    "start": round(start_time, 2),
                    "end": round(end_time, 2),
                    "text": text
                })
        finally:
            try:
                os.remove(temp_name)
            except Exception:
                pass
                
    return results

def main():
    parser = argparse.ArgumentParser(description="Chương trình nhận dạng văn bản (OCR) và giọng nói (ASR) tích hợp.")
    parser.add_argument("--mode", type=str, required=True, choices=["ocr", "asr"],
                        help="Chế độ chạy: 'ocr' sử dụng EasyOCR hoặc 'asr' sử dụng NVIDIA NeMo.")
    parser.add_argument("--input", type=str, required=True,
                        help="Đường dẫn tới hình ảnh đầu vào (cho OCR) hoặc tệp âm thanh WAV 16kHz (cho ASR).")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"Lỗi: Không tìm thấy tệp đầu vào tại {args.input}")
        sys.exit(1)
        
    if args.mode == "ocr":
        results = run_ocr(args.input)
        print("\n=== KẾT QUẢ OCR ===")
        for res in results:
            print(f"[{res['confidence']:.2f}] Box: {res['bbox']} -> Văn bản: \"{res['text']}\"")
            
    elif args.mode == "asr":
        results = run_asr(args.input)
        print("\n=== KẾT QUẢ ASR ===")
        for res in results:
            print(f"[{res['start']:.2f}s - {res['end']:.2f}s]: \"{res['text']}\"")

if __name__ == "__main__":
    main()
