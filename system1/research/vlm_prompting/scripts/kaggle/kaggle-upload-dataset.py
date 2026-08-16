"""Tao/cap nhat Kaggle dataset chua anh keyframe + file jsonl huan luyen.

Chay truc tiep `python -m kaggle` tren may nay se dut o buoc xac thuc HTTPS vi
co phan mem chen chung chi vao ket noi. truststore doc kho chung chi Windows
nen phai inject truoc khi import kaggle.
"""

import truststore

truststore.inject_into_ssl()

import argparse
import json
import shutil
import sys
from pathlib import Path

SLUG = "aic-vlm-distill-290"
TITLE = "AIC VLM Distill 290"


def gom_file(nguon_jsonl: Path, nguon_anh: Path, dich: Path, loc_290: bool) -> dict:
    dich.mkdir(parents=True, exist_ok=True)

    ten_anh_can = set()
    for ten in ("train.jsonl", "eval.jsonl"):
        src = nguon_jsonl / ten
        shutil.copy2(src, dich / ten)
        with src.open(encoding="utf-8") as f:
            for dong in f:
                dong = dong.strip()
                if dong:
                    ten_anh_can.add(json.loads(dong)["image"])

    thu_muc_anh = dich / "images"
    thu_muc_anh.mkdir(exist_ok=True)

    da_chep = 0
    thieu = []
    if loc_290:
        for ten in sorted(ten_anh_can):
            src = nguon_anh / ten
            if src.exists():
                shutil.copy2(src, thu_muc_anh / ten)
                da_chep += 1
            else:
                thieu.append(ten)
    else:
        for src in sorted(nguon_anh.iterdir()):
            if src.is_file():
                shutil.copy2(src, thu_muc_anh / src.name)
                da_chep += 1
        thieu = [t for t in sorted(ten_anh_can) if not (thu_muc_anh / t).exists()]

    return {"anh_da_chep": da_chep, "anh_dataset_can": len(ten_anh_can), "thieu": thieu}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--jsonl", required=True, type=Path)
    p.add_argument("--anh", required=True, type=Path)
    p.add_argument("--staging", required=True, type=Path)
    p.add_argument("--tat-ca-anh", action="store_true")
    p.add_argument("--chi-gom", action="store_true")
    args = p.parse_args()

    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    api.authenticate()
    print(f"Xac thuc OK — tai khoan: {api.config_values.get('username')}")

    ket_qua = gom_file(args.jsonl, args.anh, args.staging, loc_290=not args.tat_ca_anh)
    print(f"Da gom {ket_qua['anh_da_chep']} anh + 2 file jsonl vao {args.staging}")
    print(f"Dataset can {ket_qua['anh_dataset_can']} anh rieng biet")
    if ket_qua["thieu"]:
        print(f"THIEU {len(ket_qua['thieu'])} anh: {ket_qua['thieu'][:10]}")
        return 1

    meta = {
        "title": TITLE,
        "id": f"{api.config_values['username']}/{SLUG}",
        "licenses": [{"name": "unknown"}],
    }
    (args.staging / "dataset-metadata.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )

    if args.chi_gom:
        print("Chi gom file, chua upload (--chi-gom).")
        return 0

    print("Bat dau upload... (vai phut)")
    api.dataset_create_new(
        folder=str(args.staging),
        public=False,
        quiet=False,
        dir_mode="zip",
    )
    print(f"Xong. Dataset: {meta['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
