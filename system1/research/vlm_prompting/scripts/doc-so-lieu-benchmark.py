"""In moi con so can de sua report — doc thang tu file ket qua.

Ly do co script nay: sample_results.json CHI luu ca thanh cong, con ca loi nam
o checkpoint_*.json. Doc mot file roi suy ra file kia la cach 3 con so sai da
lot vao PR hom 16/08. Chay lenh nay roi chep, dung tu tinh.

    python scripts/doc-so-lieu-benchmark.py
"""

import argparse
import json
from collections import Counter
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent

p = argparse.ArgumentParser()
p.add_argument("--results", type=Path, default=GOC / "results")
args = p.parse_args()

RES = args.results

print("=" * 64)
print("CHECKPOINT — nguon duy nhat co ca loi")
print("=" * 64)

for cp in sorted(RES.glob("checkpoint_*.json")):
    try:
        d = json.loads(cp.read_text(encoding="utf-8"))
    except Exception as loi:
        print(f"{cp.name}: doc khong duoc — {loi}")
        continue
    xong = d.get("da_xong") or {}
    if not xong:
        continue
    tong = len(xong)
    ok = sum(1 for v in xong.values() if v.get("thanh_cong"))
    print(f"{cp.name:42s} tong={tong:4d}  thanh_cong={ok:4d}  "
          f"loi={tong - ok:3d}  ty_le={ok / tong:.1%}")

print()
print("=" * 64)
print("SAMPLE_RESULTS — chi ca thanh cong, day la file nop bai")
print("=" * 64)

sr = RES / "sample_results.json"
if not sr.exists():
    print("KHONG THAY sample_results.json")
    raise SystemExit(1)

d = json.loads(sr.read_text(encoding="utf-8"))
muc = d if isinstance(d, list) else d.get("results", d)

print(f"Tong so muc: {len(muc)}")
for model, so_muc in Counter(m.get("model") for m in muc).items():
    anh = {m.get("image") for m in muc if m.get("model") == model}
    dat = "DAT" if len(anh) >= 100 else "CHUA DAT"
    print(f"  {model:16s} {so_muc:4d} muc / {len(anh):4d} anh rieng biet   [{dat} moc 100]")

# Ten truong la '_latency_sec' — generate.py them tien to '_' cho moi truong
# sieu du lieu. Doc nham ten khong-gach-duoi thi moi muc deu ra 0.0.
gia = [m for m in muc if float(m.get("_latency_sec") or 0) == 0.0]
print(f"\nMuc co latency = 0 (dau hieu mock, so khong dung duoc): {len(gia)}")
if gia:
    for model, n in Counter(m.get("model") for m in gia).items():
        print(f"  {model}: {n} muc")

tong_anh = {m.get("image") for m in muc}
print(f"\nTong anh rieng biet moi model gop lai: {len(tong_anh)}")
