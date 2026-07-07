from __future__ import annotations

import shutil
from pathlib import Path


def copy_if_exists(source: Path, target: Path) -> None:
    if not source.exists():
        return
    if source.is_dir():
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def package_release(release_dir: Path | str) -> Path:
    release_path = Path(release_dir)
    archive_base = release_path.parent / release_path.name
    archive_path = shutil.make_archive(str(archive_base), "zip", release_path.parent, release_path.name)
    return Path(archive_path)
