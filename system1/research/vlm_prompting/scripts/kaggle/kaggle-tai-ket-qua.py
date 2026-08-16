"""Tai toan bo output cua mot kernel ve may, co phan trang.

kernels_output() mac dinh page_size=20 -- kernel sinh nhieu file hon se bi tai
thieu ma khong bao loi. Script nay lap het cac trang cho toi khi het token.

Chay:
    python kaggle-tai-ket-qua.py <slug> --dich D:/aic-tmp/out
    python kaggle-tai-ket-qua.py trnkhoa40phm/notebookdd8236fd34 --dich D:/aic-tmp/vintern
"""

import truststore

truststore.inject_into_ssl()

import argparse
import zipfile
from pathlib import Path

from kaggle.api.kaggle_api_extended import KaggleApi

p = argparse.ArgumentParser()
p.add_argument("slug", help="vd: trnkhoa40phm/notebookdd8236fd34")
p.add_argument("--dich", required=True, type=Path)
p.add_argument("--giai-nen", action="store_true", help="giai nen file .zip tai ve")
args = p.parse_args()

api = KaggleApi()
api.authenticate()
args.dich.mkdir(parents=True, exist_ok=True)

tat_ca: list[str] = []
token = None
trang = 0
while True:
    trang += 1
    files, token = api.kernels_output(
        args.slug, str(args.dich), page_size=200, page_token=token, quiet=False
    )
    tat_ca += list(files or [])
    print(f"  trang {trang}: {len(files or [])} file")
    if not token:
        break

print(f"Tong: {len(tat_ca)} file -> {args.dich}")

if args.giai_nen:
    for z in args.dich.glob("*.zip"):
        with zipfile.ZipFile(z) as zf:
            zf.extractall(args.dich / z.stem)
        print(f"  giai nen {z.name} -> {z.stem}/")

for f in sorted(args.dich.rglob("*")):
    if f.is_file():
        print(f"  {f.relative_to(args.dich)}  {f.stat().st_size:,} bytes")
