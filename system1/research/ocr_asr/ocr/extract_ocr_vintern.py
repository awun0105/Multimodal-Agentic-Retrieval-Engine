"""OCR keyframes bang Vintern-1B-v3_5, ho tro gop lo va chia viec 2 GPU.

CUDA_VISIBLE_DEVICES phai duoc dat TRUOC khi torch duoc import (torch khoi tao CUDA
context ngay luc import), nen argparse chay o dau file, import torch (truc tiep hoac
qua ocr_batch_runner) nam sau do.
"""
import argparse
import os
import sys
import sqlite3
import time
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="OCR keyframes bang Vintern-1B-v3_5")
    parser.add_argument("--gpu-id", type=int, default=0, help="ID GPU tien trinh nay dung")
    parser.add_argument("--num-gpus", type=int, default=1, help="Tong so GPU chia viec")
    parser.add_argument(
        "--batch-size", type=int, default=4,
        # Uoc tinh an toan: Vintern-1B fp16 ~1.9GB + lo 4 anh x 3 tile con du bo nho tren T4 16GB.
        # Chua chay kaggle_ocr_bench.ipynb (pha 01) nen chua co so do that - chot lai sau.
        help="So anh moi lo goi batch_chat (mac dinh 4, xem comment code de biet nguon goc)",
    )
    parser.add_argument("--db-in", type=str, required=True, help="Duong dan runtime.sqlite doc keyframe")
    parser.add_argument("--db-out", type=str, default=None, help="Duong dan file sqlite ghi ket qua OCR (mac dinh ocr_part{gpu-id}.sqlite)")
    parser.add_argument("--data-root", type=str, required=True, help="Thu muc goc chua anh keyframe")
    return parser.parse_args()


ARGS = parse_args()
os.environ["CUDA_VISIBLE_DEVICES"] = str(ARGS.gpu_id)

import torch

from ocr_batch_runner import load_model, chuan_bi_lo, chay_mot_lo


def init_output_db(db_path):
    """Tao ocr_texts / ocr_boxes / ocr_fts dung nguyen van schema mvp-app/db.py:53-70."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ocr_texts (
                keyframe_id TEXT PRIMARY KEY,
                video_id TEXT NOT NULL,
                full_text TEXT NOT NULL,
                FOREIGN KEY (keyframe_id) REFERENCES keyframes (keyframe_id)
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ocr_boxes (
                box_id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyframe_id TEXT NOT NULL,
                text TEXT NOT NULL,
                score REAL NOT NULL,
                ymin REAL NOT NULL,
                xmin REAL NOT NULL,
                ymax REAL NOT NULL,
                xmax REAL NOT NULL,
                FOREIGN KEY (keyframe_id) REFERENCES keyframes (keyframe_id)
            );
            """
        )
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ocr_fts'"
        ).fetchone()
        if not exists:
            conn.execute(
                "CREATE VIRTUAL TABLE ocr_fts USING fts5(keyframe_id UNINDEXED, full_text);"
            )
        conn.commit()


def main():
    args = ARGS
    db_in = Path(args.db_in)
    data_root = Path(args.data_root)
    db_out = Path(args.db_out) if args.db_out else Path(f"ocr_part{args.gpu_id}.sqlite")

    if not db_in.exists():
        print(f"Error: Database not found at {db_in}")
        sys.exit(1)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"GPU {args.gpu_id}/{args.num_gpus} - device: {device.upper()} - batch_size: {args.batch_size}")

    model, tokenizer = load_model(device)

    conn_in = sqlite3.connect(f"file:{db_in}?mode=ro", uri=True)
    conn_in.row_factory = sqlite3.Row
    query_keyframes = """
        SELECT k.keyframe_id, k.video_id, k.image_relpath
        FROM keyframes k
        LEFT JOIN ocr_texts o ON k.keyframe_id = o.keyframe_id
        WHERE o.keyframe_id IS NULL
        ORDER BY k.keyframe_id
    """
    all_keyframes = conn_in.execute(query_keyframes).fetchall()
    conn_in.close()

    keyframes = []
    for idx, kf in enumerate(all_keyframes):
        if idx % args.num_gpus != args.gpu_id:
            continue
        img_path = data_root / kf["image_relpath"]
        if not img_path.exists():
            img_path = Path(kf["image_relpath"])
        keyframes.append({
            "keyframe_id": kf["keyframe_id"],
            "video_id": kf["video_id"],
            "img_path": str(img_path),
        })

    print(f"Found {len(keyframes)} keyframe can xu ly (GPU {args.gpu_id}).")
    if not keyframes:
        print("0 keyframe can xu ly. Exiting.")
        return

    init_output_db(db_out)
    conn_out = sqlite3.connect(db_out)

    inserted_count = 0
    error_count = 0
    start_time = time.time()

    try:
        for lo in chuan_bi_lo(keyframes, args.batch_size):
            ket_qua = chay_mot_lo(model, tokenizer, device, lo)
            xu_ly_trong_lo = {id(kf): kf for kf in lo}
            for kf, text in ket_qua:
                extracted_text = text.strip() if text else ""
                if extracted_text:
                    conn_out.execute(
                        "INSERT OR REPLACE INTO ocr_texts (keyframe_id, video_id, full_text) VALUES (?, ?, ?)",
                        (kf["keyframe_id"], kf["video_id"], extracted_text)
                    )
                    conn_out.execute(
                        "INSERT OR REPLACE INTO ocr_fts (keyframe_id, full_text) VALUES (?, ?)",
                        (kf["keyframe_id"], extracted_text)
                    )
                    inserted_count += 1
                    if inserted_count % 50 == 0:
                        conn_out.commit()
                xu_ly_trong_lo.pop(id(kf), None)
            error_count += len(xu_ly_trong_lo)

            if inserted_count % 500 < args.batch_size:
                elapsed = time.time() - start_time
                rate = inserted_count / elapsed if elapsed > 0 else 0
                print(f"Progress: {inserted_count}/{len(keyframes)} - {rate:.2f} anh/giay")
    finally:
        conn_out.commit()
        conn_out.close()

    duration = time.time() - start_time
    rate = inserted_count / duration if duration > 0 else 0
    print("\n=== Tong ket ===")
    print(f"Da xu ly: {inserted_count}")
    print(f"Loi/bo qua: {error_count}")
    print(f"Thoi gian: {duration:.2f}s ({rate:.2f} anh/giay)")


if __name__ == "__main__":
    main()
