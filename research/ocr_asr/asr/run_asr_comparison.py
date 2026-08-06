import os
import json
from pathlib import Path

# Di chuyển thư mục làm việc vào 'asr' để các đường dẫn tương đối trong notebook chạy chính xác
os.chdir(Path(__file__).resolve().parent)

notebook_path = Path("asr_comparison.ipynb")
with open(notebook_path, "r", encoding="utf-8") as f:
    nb = json.load(f)

# Trích xuất toàn bộ code cell
code_cells = [c["source"] for c in nb["cells"] if c["cell_type"] == "code"]
full_code = ""
for cell in code_cells:
    full_code += "".join(cell) + "\n"

print("--- Đang thực thi mã nguồn asr_comparison.ipynb ---")
exec(full_code, globals())
print("--- Thực thi thành công và hoàn tất! ---")
