"""Ghep diem cham tay voi dap an, tinh diem tung model."""
import json
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent

diem = json.loads((GOC / "results/phieu-cham-DIEM.json").read_text(encoding="utf-8"))
dap = json.loads((GOC / "results/phieu-cham-DAP-AN.json").read_text(encoding="utf-8"))["anh"]

tong = {}
anh_da_cham = [k for k in diem if not k.startswith("_")]
for anh in anh_da_cham:
    for nhan in "ABCD":
        mk = dap[anh][nhan]
        d, t, u = diem[anh][nhan][:3]
        s = tong.setdefault(mk, [0, 0, 0, 0])
        s[0] += d
        s[1] += t
        s[2] += u
        s[3] += 1

print(f"Da cham {len(anh_da_cham)}/30 anh")
print()
print(f'{"model":16} {"Dung":>6} {"TViet":>6} {"Du":>6} {"TB/6":>7}')
print("-" * 46)
for mk, (d, t, u, n) in sorted(tong.items(), key=lambda x: -sum(x[1][:3])):
    print(f"{mk:16} {d/n:6.2f} {t/n:6.2f} {u/n:6.2f} {(d+t+u)/n:7.2f}")

if len(sys.argv) > 1 and sys.argv[1] == "--chi-tiet":
    print()
    for anh in sorted(anh_da_cham):
        print(f"{anh}: ", end="")
        for nhan in "ABCD":
            mk = dap[anh][nhan]
            d, t, u = diem[anh][nhan][:3]
            print(f"{mk.split('-')[0][:7]}={d+t+u} ", end="")
        print()
