"""Kiểm tra dataset ảnh trên Kaggle có đủ 177.321 file .jpg gốc hay không.

Chạy CPU, trên máy local Windows. Không tốn giờ GPU.

Cách dùng:
    python kiem_tra_dataset_anh_kaggle.py [--dataset OWNER/SLUG] [--tao-metadata-mau]

Yêu cầu:
    - `pip install truststore kaggle`
    - `kaggle.json` (token API) đặt tại `~/.kaggle/kaggle.json`
      (Kaggle > Settings > API > Create New Token)

Bẫy đã biết (docs/kaggle-huong-dan-va-bay.md mục 4.6, 4bis):
    - PHẢI gọi `truststore.inject_into_ssl()` TRƯỚC khi import `kaggle`,
      nếu không CLI/SDK lỗi `CERTIFICATE_VERIFY_FAILED` trên máy này.
    - API `dataset_list_files` mặc định trả 20 dòng/trang — PHẢI phân trang
      bằng `page_token` tới khi `next_page_token` rỗng.
    - Thuộc tính dung lượng file là `total_bytes`, KHÔNG phải `size`.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

# --- Bẫy 4.6: truststore PHẢI được inject TRƯỚC khi import kaggle ---
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    print(
        "LỖI: thiếu thư viện 'truststore'.\n"
        "Cài bằng: pip install truststore\n"
        "Thư viện này bắt buộc để gọi Kaggle API trên máy này (né lỗi SSL "
        "CERTIFICATE_VERIFY_FAILED). Xem docs/kaggle-huong-dan-va-bay.md mục 4.6.",
        file=sys.stderr,
    )
    sys.exit(2)

try:
    from kaggle.api.kaggle_api_extended import KaggleApi
except ImportError:
    print(
        "LỖI: thiếu thư viện 'kaggle'.\n"
        "Cài bằng: pip install kaggle",
        file=sys.stderr,
    )
    sys.exit(2)


SO_ANH_MONG_DOI = 177_321
DATASET_MAC_DINH = "nhathoang42/aic2025-mvp-app-data"
DATASET_TAO_MOI_MAC_DINH = "aic2025-keyframes-raw"
SQLITE_PATH = Path("d:/AIC/aic25-b1-v1/metadata/runtime.sqlite")
GHI_KET_QUA_PATH = Path(
    "d:/AIC/plans/260821-1244-ocr-kaggle-2gpu/research/tinh-trang-dataset-anh.md"
)


def kiem_tra_credential() -> bool:
    """Kiểm tra kaggle.json có tồn tại chưa đọc API. Trả True nếu có vẻ ổn."""
    kaggle_config_dir = Path(os.environ.get("KAGGLE_CONFIG_DIR", Path.home() / ".kaggle"))
    kaggle_json = kaggle_config_dir / "kaggle.json"
    co_env = bool(os.environ.get("KAGGLE_USERNAME")) and bool(os.environ.get("KAGGLE_KEY"))
    if kaggle_json.exists() or co_env:
        return True
    print(
        "LỖI: không tìm thấy credential Kaggle.\n"
        f"Đã tìm: {kaggle_json}\n"
        "Cách lấy:\n"
        "  1. Đăng nhập https://www.kaggle.com/settings\n"
        "  2. Mục API -> bấm 'Create New Token' -> tải kaggle.json\n"
        f"  3. Đặt file vào: {kaggle_config_dir}\\kaggle.json\n"
        "  (hoặc set biến môi trường KAGGLE_USERNAME và KAGGLE_KEY)\n",
        file=sys.stderr,
    )
    return False


def liet_ke_toan_bo_file(api: KaggleApi, dataset: str) -> list:
    """Liệt kê toàn bộ file trong dataset, phân trang tới hết.

    Bẫy đã biết: API mặc định trả 20 dòng/trang. Không phân trang thì đếm
    thiếu và kết luận sai "thiếu ảnh" trong khi dataset đủ.
    """
    tat_ca_file = []
    page_token = None
    so_trang = 0
    while True:
        so_trang += 1
        response = api.dataset_list_files(dataset, page_token=page_token, page_size=200)
        trang_file = list(getattr(response, "files", []) or [])
        tat_ca_file.extend(trang_file)
        print(f"  trang {so_trang}: +{len(trang_file)} file (tổng {len(tat_ca_file)})")
        page_token = getattr(response, "next_page_token", "") or getattr(
            response, "nextPageToken", ""
        )
        if not page_token:
            break
    return tat_ca_file


def lay_mau_duong_dan_sqlite(sqlite_path: Path, so_luong: int = 5) -> list[str]:
    if not sqlite_path.exists():
        print(f"CẢNH BÁO: không tìm thấy sqlite tại {sqlite_path}, bỏ qua đối chiếu mẫu.")
        return []
    con = sqlite3.connect(str(sqlite_path))
    try:
        cur = con.cursor()
        cur.execute("SELECT image_relpath FROM keyframes LIMIT ?", (so_luong,))
        return [row[0] for row in cur.fetchall()]
    finally:
        con.close()


def tao_dataset_metadata_mau(thu_muc: Path, slug_moi: str) -> Path:
    """Tạo dataset-metadata.json mẫu cho nhánh B (thiếu ảnh, cần upload).

    KHÔNG tự upload — chỉ tạo file mẫu để người quyết định chạy tiếp.
    """
    thu_muc.mkdir(parents=True, exist_ok=True)
    metadata = {
        "title": "AIC2025 Keyframes Raw",
        "id": slug_moi,
        "licenses": [{"name": "unknown"}],
    }
    duong_dan = thu_muc / "dataset-metadata.json"
    duong_dan.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return duong_dan


def ghi_ket_qua(
    duong_dan_ghi: Path,
    dataset: str,
    tong_file: int,
    so_jpg: int,
    trang_thai: str,
    mau_khop: list[tuple[str, bool | None]],
    tien_to_mount: str,
) -> None:
    duong_dan_ghi.parent.mkdir(parents=True, exist_ok=True)
    dong = []
    dong.append("# Tình trạng dataset ảnh trên Kaggle")
    dong.append("")
    dong.append(f"- Dataset kiểm tra: `{dataset}`")
    dong.append(f"- Tổng số file trong dataset: {tong_file}")
    dong.append(f"- Số file .jpg: {so_jpg}")
    dong.append(f"- Số ảnh mong đợi (local): {SO_ANH_MONG_DOI}")
    dong.append(f"- **Kết luận: {trang_thai}**")
    dong.append("")
    dong.append(f"- Tiền tố mount thật: `{tien_to_mount}`")
    dong.append("")
    dong.append("## Đối chiếu mẫu đường dẫn (sqlite vs dataset)")
    dong.append("")
    if mau_khop:
        dong.append("| image_relpath (sqlite) | khớp cấu trúc dataset |")
        dong.append("|---|---|")
        for duong_dan, khop in mau_khop:
            if khop is None:
                nhan = "chưa kiểm được (không truy cập dataset)"
            else:
                nhan = "có" if khop else "KHÔNG"
            dong.append(f"| `{duong_dan}` | {nhan} |")
    else:
        dong.append("(không đọc được sqlite để đối chiếu)")
    dong.append("")
    duong_dan_ghi.write_text("\n".join(dong), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=DATASET_MAC_DINH, help="owner/slug dataset cần kiểm")
    parser.add_argument(
        "--tao-metadata-mau",
        action="store_true",
        help="Nếu thiếu ảnh: tạo dataset-metadata.json mẫu (không tự upload)",
    )
    args = parser.parse_args()

    if not kiem_tra_credential():
        return 1

    try:
        api = KaggleApi()
        api.authenticate()
    except Exception as loi:  # xác thực có thể lỗi vì nhiều lý do (token sai, hết hạn...)
        print(f"LỖI xác thực Kaggle API: {loi}", file=sys.stderr)
        return 1

    print(f"Đang liệt kê file dataset: {args.dataset}")
    try:
        tat_ca_file = liet_ke_toan_bo_file(api, args.dataset)
    except Exception as loi:
        trang_thai = "KHÔNG TRUY CẬP ĐƯỢC"
        print(f"{trang_thai} dataset '{args.dataset}': {loi}", file=sys.stderr)
        tien_to_mount = f"/kaggle/input/{args.dataset.split('/')[-1]}"
        mau_sqlite = lay_mau_duong_dan_sqlite(SQLITE_PATH)
        mau_khong_doi_chieu = [
            (duong_dan, None) for duong_dan in mau_sqlite
        ]  # không truy cập được dataset nên không có gì để đối chiếu
        ghi_ket_qua(
            GHI_KET_QUA_PATH,
            args.dataset,
            0,
            0,
            f"{trang_thai} ({loi})",
            mau_khong_doi_chieu,
            tien_to_mount,
        )
        print(f"Đã ghi kết quả vào: {GHI_KET_QUA_PATH}")
        return 1

    tong_file = len(tat_ca_file)
    file_jpg = [f for f in tat_ca_file if str(getattr(f, "name", "")).lower().endswith(".jpg")]
    so_jpg = len(file_jpg)

    print(f"\nTổng số file trong dataset: {tong_file}")
    print(f"Số file .jpg: {so_jpg}")
    print(f"Số ảnh mong đợi: {SO_ANH_MONG_DOI}")

    mau_sqlite = lay_mau_duong_dan_sqlite(SQLITE_PATH)
    mau_khop: list[tuple[str, bool]] = []
    if mau_sqlite:
        ten_file_dataset = {str(getattr(f, "name", "")) for f in tat_ca_file}
        print("\nĐối chiếu mẫu đường dẫn sqlite với dataset:")
        for duong_dan in mau_sqlite:
            # Dataset có thể lưu tên file kèm hoặc không kèm tiền tố "keyframes/"
            khop = duong_dan in ten_file_dataset or Path(duong_dan).name in {
                Path(n).name for n in ten_file_dataset
            }
            mau_khop.append((duong_dan, khop))
            print(f"  {duong_dan}: {'khớp' if khop else 'KHÔNG khớp'}")

    if so_jpg >= SO_ANH_MONG_DOI:
        trang_thai = "ĐÃ CÓ ĐỦ ẢNH"
    elif tong_file == 0:
        trang_thai = "KHÔNG TRUY CẬP ĐƯỢC"
    else:
        trang_thai = f"THIẾU ẢNH, cần upload (chỉ có {so_jpg}/{SO_ANH_MONG_DOI})"

    tien_to_mount = f"/kaggle/input/{args.dataset.split('/')[-1]}"

    print(f"\n=== KẾT LUẬN: {trang_thai} ===")

    ghi_ket_qua(
        GHI_KET_QUA_PATH,
        args.dataset,
        tong_file,
        so_jpg,
        trang_thai,
        mau_khop,
        tien_to_mount,
    )
    print(f"Đã ghi kết quả vào: {GHI_KET_QUA_PATH}")

    if trang_thai.startswith("THIẾU ẢNH") and args.tao_metadata_mau:
        thu_muc_staging = Path("d:/AIC/plans/260821-1244-ocr-kaggle-2gpu/research/staging-upload")
        duong_dan_meta = tao_dataset_metadata_mau(thu_muc_staging, DATASET_TAO_MOI_MAC_DINH)
        print(
            f"\nĐã tạo dataset-metadata.json mẫu tại: {duong_dan_meta}\n"
            "Hướng dẫn upload thủ công (KHÔNG tự động — cần người quyết định):\n"
            "  1. Copy toàn bộ cây d:/AIC/aic25-b1-v1/keyframes/ vào thư mục staging trên,\n"
            "     giữ nguyên cấu trúc L21/L21_V001/001.jpg (không nén 1 zip khổng lồ).\n"
            "  2. Sửa 'id' trong dataset-metadata.json thành <kaggle-username>/"
            f"{DATASET_TAO_MOI_MAC_DINH}\n"
            "  3. Chạy: api.dataset_create_new(str(thu_muc_staging), dir_mode='zip', "
            "public=False)\n"
            "  4. Theo dõi trạng thái tới khi 'ready' rồi chạy lại script này để kiểm lại.\n"
        )

    return 0


if __name__ == "__main__":
    # Đảm bảo stdout không vỡ vì ký tự tiếng Việt khi bị redirect ra file/log.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    sys.exit(main())
