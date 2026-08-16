"""Day notebook 27 cell len Kaggle, gan dataset, giu nguyen cau hinh GPU T4.

Gan dataset qua metadata (thay vi bam Add Data tren web) thi cau hinh duoc ghi
ngay luc tao phien moi -- tranh bay "chon GPU giua phien khong an thua".
"""

import truststore

truststore.inject_into_ssl()

import argparse
import json
import shutil
from pathlib import Path

from kaggle.api.kaggle_api_extended import KaggleApi

DATASET_SLUG = "trnkhoa40phm/aic-vlm-distill-290"

p = argparse.ArgumentParser()
p.add_argument("--notebook", required=True, type=Path)
p.add_argument("--meta", required=True, type=Path)
p.add_argument("--staging", required=True, type=Path)
p.add_argument("--chay-luon", action="store_true", help="push kem chay (Save & Run All)")
args = p.parse_args()

api = KaggleApi()
api.authenticate()

staging = args.staging
staging.mkdir(parents=True, exist_ok=True)

meta = json.loads(args.meta.read_text(encoding="utf-8"))
ten_file = meta["code_file"]
shutil.copy2(args.notebook, staging / ten_file)

meta["dataset_sources"] = [DATASET_SLUG]
meta["enable_gpu"] = True
meta["enable_internet"] = True
meta["machine_shape"] = "NvidiaTeslaT4"
meta.pop("id_no", None)

(staging / "kernel-metadata.json").write_text(
    json.dumps(meta, indent=2), encoding="utf-8"
)

so_cell = len(json.loads((staging / ten_file).read_text(encoding="utf-8"))["cells"])
print(f"Chuan bi day: {so_cell} cell, dataset={DATASET_SLUG}, GPU={meta['machine_shape']}")

if not args.chay_luon:
    print("Chua day (thieu --chay-luon).")
    raise SystemExit(0)

kq = api.kernels_push(str(staging))
print("Ket qua push:")
for truong in ("ref", "url", "versionNumber", "error", "invalidTags"):
    gia_tri = getattr(kq, truong, None)
    if gia_tri:
        print(f"  {truong}: {gia_tri}")
