"""
Kịch bản tự động hóa tải dữ liệu từ Google Drive lên Kaggle Dataset thông qua Google Colab.
Tối ưu hóa:
1. Tận dụng băng thông Google Cloud tốc độ cao (200MB/s - 1GB/s).
2. Tự động sinh dataset-metadata.json và gọi Kaggle API.
3. Hỗ trợ tạo mới Dataset (dataset_create_new) hoặc cập nhật phiên bản mới (dataset_create_version).
"""

from __future__ import annotations
import os
import json
import zipfile
import glob
import shutil
from pathlib import Path


def setup_kaggle_credentials(kaggle_json_path: Path | str):
    """Cấu hình API Token của Kaggle trong môi trường Colab."""
    kaggle_dir = Path.home() / ".kaggle"
    kaggle_dir.mkdir(parents=True, exist_ok=True)
    dest_path = kaggle_dir / "kaggle.json"
    
    shutil.copy(str(kaggle_json_path), str(dest_path))
    os.chmod(str(dest_path), 0o600)
    print(f"[XÁC THỰC] Đã cấu hình Kaggle API Token thành công từ: {kaggle_json_path}")


def pack_and_upload_to_kaggle(
    source_dir_or_zip: Path | str,
    dataset_slug: str,
    dataset_title: str,
    output_staging_dir: Path = Path("/content/kaggle_staging"),
    is_new_dataset: bool = True,
    version_notes: str = "Cập nhật dữ liệu video mới cho AIC 2026"
):
    """
    Đóng gói dữ liệu và đẩy lên Kaggle Dataset.
    """
    import kaggle
    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    api.authenticate()

    output_staging_dir.mkdir(parents=True, exist_ok=True)
    source_path = Path(source_dir_or_zip)

    print(f"[TIẾN TRÌNH] Đang chuẩn bị dữ liệu từ: {source_path}")

    # Nếu source là thư mục chứa nhiều file zip/video, copy vào staging
    if source_path.is_dir():
        for item in source_path.glob("*"):
            if item.is_file():
                shutil.copy(str(item), str(output_staging_dir / item.name))
    elif source_path.is_file():
        shutil.copy(str(source_path), str(output_staging_dir / source_path.name))

    # Tạo metadata.json cho Kaggle Dataset
    meta_path = output_staging_dir / "dataset-metadata.json"
    metadata = {
        "title": dataset_title,
        "id": f"{api.get_config_value('username')}/{dataset_slug}",
        "licenses": [{"name": "CC0-1.0"}]
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print(f"[METADATA] Đã tạo file metadata: {meta_path}")

    # Đẩy lên Kaggle
    if is_new_dataset:
        print(f"[KAGGLE API] Đang tạo mới Dataset: {metadata['id']}...")
        try:
            api.dataset_create_new(
                folder=str(output_staging_dir),
                public=False, # Mặc định để Private
                quiet=False
            )
            print(f"[THÀNH CÔNG] Đã tạo mới Dataset: https://www.kaggle.com/datasets/{metadata['id']}")
        except Exception as e:
            print(f"[CẢNH BÁO] Không thể tạo mới (có thể dataset đã tồn tại): {e}")
            print(f"[KAGGLE API] Thử cập nhật version mới...")
            api.dataset_create_version(
                folder=str(output_staging_dir),
                version_notes=version_notes,
                quiet=False
            )
            print(f"[THÀNH CÔNG] Đã cập nhật version mới cho Dataset: https://www.kaggle.com/datasets/{metadata['id']}")
    else:
        print(f"[KAGGLE API] Đang cập nhật version mới cho Dataset: {metadata['id']}...")
        api.dataset_create_version(
            folder=str(output_staging_dir),
            version_notes=version_notes,
            quiet=False
        )
        print(f"[THÀNH CÔNG] Đã cập nhật version mới: https://www.kaggle.com/datasets/{metadata['id']}")


if __name__ == "__main__":
    print("Module upload Kaggle sẵn sàng.")
