"""Tai output cua phien train ve may va giai nen adapter.

Kaggle xoa sach /kaggle/working khi phien tat -- chay cai nay ngay khi
trang thai chuyen sang COMPLETE.
"""

import truststore

truststore.inject_into_ssl()

import argparse
import zipfile
from pathlib import Path

from kaggle.api.kaggle_api_extended import KaggleApi

SLUG = "trnkhoa40phm/notebook4764945a8d"

p = argparse.ArgumentParser()
p.add_argument("--tai-ve", required=True, type=Path, help="thu muc chua file tai ve")
p.add_argument("--dich", required=True, type=Path, help="thu muc giai nen adapter")
args = p.parse_args()

api = KaggleApi()
api.authenticate()

args.tai_ve.mkdir(parents=True, exist_ok=True)
api.kernels_output(SLUG, path=str(args.tai_ve))

print("--- File tai ve ---")
for f in sorted(args.tai_ve.rglob("*")):
    if f.is_file():
        print(f"  {f.relative_to(args.tai_ve)}  {f.stat().st_size:,} bytes")

zips = [f for f in args.tai_ve.rglob("*.zip") if "lora" in f.name.lower()]
if not zips:
    print("KHONG THAY file zip adapter. Kiem lai output o tren.")
    raise SystemExit(1)

args.dich.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(zips[0]) as z:
    z.extractall(args.dich)
print(f"Da giai nen {zips[0].name} -> {args.dich}")

can_co = ["adapter_config.json", "adapter_model.safetensors"]
for ten in can_co:
    duong_dan = args.dich / ten
    dau = "OK " if duong_dan.exists() else "THIEU"
    kich_thuoc = f"{duong_dan.stat().st_size:,} bytes" if duong_dan.exists() else ""
    print(f"  [{dau}] {ten} {kich_thuoc}")
