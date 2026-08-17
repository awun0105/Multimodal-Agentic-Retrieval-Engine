"""Kiem chenh lech giua cac model co y nghia thong ke khong.

30 anh la mau nho. Chenh 0,10 diem giua hai model dan dau co the chi la nhieu.
Dung phep thu dau (sign test) tren tung cap anh: dem so anh model X hon model Y,
roi tinh xac suat ket qua do xay ra neu hai model that su ngang nhau.
"""
import json
from itertools import combinations
from math import comb
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent

diem = json.loads((GOC / "results/phieu-cham-DIEM.json").read_text(encoding="utf-8"))
dap = json.loads((GOC / "results/phieu-cham-DAP-AN.json").read_text(encoding="utf-8"))["anh"]

# diem[anh][model] = tong 3 tieu chi
theo_anh = {}
for anh, v in diem.items():
    if anh.startswith("_"):
        continue
    theo_anh[anh] = {dap[anh][n]: sum(v[n][:3]) for n in "ABCD"}

models = sorted({m for d in theo_anh.values() for m in d})


def p_hai_phia(thang: int, thua: int) -> float:
    """Xac suat thay chenh lech nay (hoac hon) neu hai model ngang nhau."""
    n = thang + thua
    if n == 0:
        return 1.0
    k = max(thang, thua)
    duoi = sum(comb(n, i) for i in range(k, n + 1))
    return min(1.0, 2 * duoi / 2**n)


print("Phep thu dau tren 30 anh — chenh lech co that hay chi la nhieu?\n")
print(f'{"cap model":34} {"thang":>6} {"thua":>5} {"hoa":>4} {"p":>7}  ket luan')
print("-" * 78)
for a, b in combinations(models, 2):
    thang = sum(1 for d in theo_anh.values() if d[a] > d[b])
    thua = sum(1 for d in theo_anh.values() if d[a] < d[b])
    hoa = len(theo_anh) - thang - thua
    p = p_hai_phia(thang, thua)
    kl = "CO khac biet" if p < 0.05 else "chua du bang chung"
    print(f"{a+' vs '+b:34} {thang:6} {thua:5} {hoa:4} {p:7.3f}  {kl}")
