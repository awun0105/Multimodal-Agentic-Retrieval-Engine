"""Bien dich thu tung cell -- bat loi cu phap truoc khi ton mot luot GPU."""

import ast
import io
import json
import sys
from pathlib import Path

p = Path(sys.argv[1])
nb = json.loads(p.read_text(encoding="utf-8"))

loi = 0
for i, c in enumerate(nb["cells"]):
    if c.get("cell_type") != "code":
        continue
    src = "".join(c["source"])
    # bo dong magic ipython (!pip, %cd) -- ast khong hieu
    sach = "\n".join(
        "pass" if d.lstrip().startswith(("!", "%")) else d for d in src.splitlines()
    )
    try:
        ast.parse(sach)
        print(f"[OK  ] cell {i}")
    except SyntaxError as e:
        loi += 1
        print(f"[LOI ] cell {i}: dong {e.lineno}: {e.msg}")
        for n, d in enumerate(sach.splitlines(), 1):
            if abs(n - (e.lineno or 0)) <= 2:
                print(f"        {n}: {d}")

print(f"\nTong: {loi} cell loi cu phap")
sys.exit(1 if loi else 0)
