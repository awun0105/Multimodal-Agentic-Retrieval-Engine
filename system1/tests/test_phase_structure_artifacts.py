from __future__ import annotations

import zipfile
from pathlib import Path

from system1.artifacts.package import validate_artifact_zip, write_artifact_zip


def _write_structure_zip(
    release_dir: Path,
    video_id: str,
    *,
    batch_id: str = "batch_000",
    artifact_type: str = "structure",
) -> Path:
    artifact_dir = release_dir / "artifacts" / "structure" / video_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "manifest.json").write_text('{"status":"pass"}\n', encoding="utf-8")
    (artifact_dir / "shots.parquet").write_bytes(f"{video_id} shots".encode())
    return write_artifact_zip(
        artifact_dir=artifact_dir,
        zip_path=release_dir / "artifacts" / "structure" / f"{video_id}_structure.zip",
        video_id=video_id,
        artifact_type=artifact_type,
        batch_id=batch_id,
        worker_id="worker_local_01",
        status="complete",
    )


def test_artifact_validation_streams_payload_checksum_reads(
    tmp_path: Path, monkeypatch
) -> None:
    release_dir = tmp_path / "release"
    zip_path = _write_structure_zip(release_dir, "L21_V001")
    original_read = zipfile.ZipFile.read

    def metadata_only_read(archive, name, *args, **kwargs):
        if Path(str(name)).name not in {"artifact_manifest.json", "checksums.json"}:
            raise AssertionError("payload members must be streamed with ZipFile.open")
        return original_read(archive, name, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "read", metadata_only_read)

    manifest = validate_artifact_zip(zip_path)

    assert manifest["video_id"] == "L21_V001"



def test_artifact_zip_stores_compressed_media_and_deflates_text(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifact"
    for name in ("a.jpg", "b.JPEG", "c.webp", "d.npy", "e.parquet", "f.json", "g.txt"):
        (artifact_dir / "sub").mkdir(parents=True, exist_ok=True)
        (artifact_dir / "sub" / name).write_bytes(b"payload " * 64)
    zip_path = write_artifact_zip(artifact_dir=artifact_dir, zip_path=tmp_path / "V1.zip", video_id="V1",
                                  artifact_type="worker", batch_id="b", worker_id="w", status="ok")

    with zipfile.ZipFile(zip_path) as archive:
        types = {Path(info.filename).name: info.compress_type for info in archive.infolist()}
    stored = {"a.jpg", "b.JPEG", "c.webp", "d.npy", "e.parquet"}
    assert {name for name, kind in types.items() if kind == zipfile.ZIP_STORED} == stored
    assert all(kind == zipfile.ZIP_DEFLATED for name, kind in types.items() if name not in stored)
    assert {"f.json", "g.txt"} <= set(types)
