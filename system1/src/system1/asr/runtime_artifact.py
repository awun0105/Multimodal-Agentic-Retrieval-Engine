from __future__ import annotations

import fcntl
import hashlib
import importlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any

from huggingface_hub import hf_hub_download

RECEIPT_SCHEMA = "phase01_flashlight_runtime_receipt_v1"
MANIFEST_SCHEMA = "phase01_flashlight_runtime_manifest_v1"


def default_runtime_root() -> Path:
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        return Path(hf_home) / "system1_runtime" / "flashlight_text"
    cache_root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return cache_root / "system1" / "flashlight_text"


def prepare_flashlight_runtime(
    *,
    artifact_config: Mapping[str, Any],
    storage_config: Mapping[str, Any],
    cache_root: Path | str | None = None,
    token: str | None = None,
    installer: Any = subprocess.run,
) -> Path:
    """Download, verify, and install the project-owned CPython 3.13 wheel."""

    runtime_root = Path(cache_root) if cache_root is not None else default_runtime_root()
    runtime_root.mkdir(parents=True, exist_ok=True)
    with _exclusive_lock(runtime_root / ".prepare.lock"):
        manifest_remote = _safe_remote_path(
            str(storage_config.get("prefix", "")),
            str(artifact_config["manifest_path"]),
        )
        manifest_path = Path(
            hf_hub_download(
                repo_id=str(storage_config["repo_id"]),
                repo_type=str(storage_config.get("repo_type", "dataset")),
                revision=str(storage_config.get("revision", "main")),
                filename=manifest_remote,
                token=token,
                cache_dir=str(runtime_root / "hf_cache"),
            )
        )
        expected_manifest_hash = str(
            artifact_config.get("manifest_sha256", "")
        ).strip()
        if expected_manifest_hash and _sha256_file(manifest_path) != expected_manifest_hash:
            raise RuntimeError("Flashlight runtime manifest checksum mismatch")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        validate_runtime_manifest(manifest, artifact_config=artifact_config)

        wheel = manifest["wheel"]
        wheel_filename = _safe_basename(str(wheel["filename"]))
        wheel_remote = _safe_remote_path(
            str(PurePosixPath(manifest_remote).parent), wheel_filename
        )
        wheel_path = Path(
            hf_hub_download(
                repo_id=str(storage_config["repo_id"]),
                repo_type=str(storage_config.get("repo_type", "dataset")),
                revision=str(storage_config.get("revision", "main")),
                filename=wheel_remote,
                token=token,
                cache_dir=str(runtime_root / "hf_cache"),
            )
        )
        if wheel_path.stat().st_size != int(wheel["size_bytes"]):
            raise RuntimeError("Flashlight runtime wheel size mismatch")
        wheel_sha256 = _sha256_file(wheel_path)
        if wheel_sha256 != str(wheel["sha256"]):
            raise RuntimeError("Flashlight runtime wheel checksum mismatch")

        receipt_path = runtime_root / "receipt.json"
        if _receipt_is_current(receipt_path, manifest, wheel_sha256):
            try:
                validate_installed_flashlight_runtime(
                    artifact_config=artifact_config,
                    receipt_path=receipt_path,
                )
            except (ImportError, RuntimeError, importlib.metadata.PackageNotFoundError):
                pass
            else:
                return receipt_path

        result = installer(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-deps",
                "--force-reinstall",
                str(wheel_path),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if result.returncode != 0:
            output = str(result.stdout or "")[-4000:]
            raise RuntimeError(f"Flashlight runtime wheel installation failed: {output}")
        _validate_flashlight_import(str(artifact_config["package_version"]))
        receipt = {
            "schema_version": RECEIPT_SCHEMA,
            "repo_id": str(storage_config["repo_id"]),
            "repo_type": str(storage_config.get("repo_type", "dataset")),
            "revision": str(storage_config.get("revision", "main")),
            "manifest_path": manifest_remote,
            "manifest_sha256": _sha256_file(manifest_path),
            "wheel_filename": wheel_filename,
            "wheel_sha256": wheel_sha256,
            "package_name": str(artifact_config["package_name"]),
            "package_version": str(artifact_config["package_version"]),
            "python_tag": _python_tag(),
            "platform": _platform_identity(),
        }
        _atomic_write_json(receipt_path, receipt)
        return receipt_path


def validate_installed_flashlight_runtime(
    *,
    artifact_config: Mapping[str, Any],
    receipt_path: Path | str | None = None,
) -> dict[str, Any]:
    resolved_receipt = (
        Path(receipt_path)
        if receipt_path is not None
        else default_runtime_root() / "receipt.json"
    )
    if not resolved_receipt.is_file():
        raise RuntimeError(
            "Flashlight runtime receipt is missing; run phase01-prepare-asr-runtime"
        )
    receipt = json.loads(resolved_receipt.read_text(encoding="utf-8"))
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise RuntimeError("Unsupported Flashlight runtime receipt schema")
    expected = {
        "package_name": str(artifact_config["package_name"]),
        "package_version": str(artifact_config["package_version"]),
        "python_tag": str(artifact_config["python_tag"]),
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            raise RuntimeError(f"Flashlight runtime receipt {key} mismatch")
    if receipt.get("python_tag") != _python_tag():
        raise RuntimeError("Flashlight runtime receipt belongs to another Python ABI")
    if receipt.get("platform") != _platform_identity():
        raise RuntimeError("Flashlight runtime receipt belongs to another platform")
    expected_manifest_hash = str(
        artifact_config.get("manifest_sha256", "")
    ).strip()
    if expected_manifest_hash and receipt.get("manifest_sha256") != expected_manifest_hash:
        raise RuntimeError("Flashlight runtime receipt manifest checksum mismatch")
    _validate_flashlight_import(str(artifact_config["package_version"]))
    return receipt


def validate_runtime_manifest(
    manifest: Mapping[str, Any],
    *,
    artifact_config: Mapping[str, Any],
    python_tag: str | None = None,
    platform_identity: str | None = None,
) -> None:
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise RuntimeError("Unsupported Flashlight runtime manifest schema")
    for key in ("package_name", "package_version", "python_tag"):
        if str(manifest.get(key, "")) != str(artifact_config[key]):
            raise RuntimeError(f"Flashlight runtime manifest {key} mismatch")
    expected_python = python_tag or _python_tag()
    if str(manifest["python_tag"]) != expected_python:
        raise RuntimeError("Flashlight runtime wheel does not match the Python ABI")
    expected_platform = platform_identity or _platform_identity()
    supported_platform = str(manifest.get("platform", ""))
    if supported_platform != expected_platform:
        raise RuntimeError("Flashlight runtime wheel does not match the platform")
    wheel = manifest.get("wheel")
    if not isinstance(wheel, Mapping):
        raise TypeError("Flashlight runtime manifest has no wheel record")
    filename = _safe_basename(str(wheel.get("filename", "")))
    if expected_python not in filename or "x86_64" not in filename:
        raise RuntimeError("Flashlight runtime wheel filename has an invalid ABI tag")
    sha256 = str(wheel.get("sha256", ""))
    if len(sha256) != 64 or any(character not in "0123456789abcdef" for character in sha256):
        raise RuntimeError("Flashlight runtime wheel has an invalid SHA-256")
    if int(wheel.get("size_bytes", 0)) <= 0:
        raise RuntimeError("Flashlight runtime wheel size is invalid")


def _validate_flashlight_import(expected_version: str) -> None:
    actual = importlib.metadata.version("flashlight-text")
    if actual != expected_version:
        raise RuntimeError(
            f"Installed flashlight-text {actual} differs from required {expected_version}"
        )
    module = importlib.import_module("flashlight.lib.text.decoder")
    if getattr(module, "KenLM", None) is None:
        raise RuntimeError("flashlight-text decoder does not expose KenLM")


def _receipt_is_current(
    receipt_path: Path,
    manifest: Mapping[str, Any],
    wheel_sha256: str,
) -> bool:
    if not receipt_path.is_file():
        return False
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return bool(
        receipt.get("schema_version") == RECEIPT_SCHEMA
        and receipt.get("wheel_sha256") == wheel_sha256
        and receipt.get("package_version") == manifest.get("package_version")
        and receipt.get("python_tag") == _python_tag()
        and receipt.get("platform") == _platform_identity()
    )


def _python_tag() -> str:
    return f"cp{sys.version_info.major}{sys.version_info.minor}"


def _platform_identity() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system != "linux" or machine not in {"x86_64", "amd64"}:
        return f"{system}_{machine}"
    return "linux_x86_64"


def _safe_basename(value: str) -> str:
    if not value or PurePosixPath(value).name != value or value in {".", ".."}:
        raise RuntimeError("Unsafe Flashlight runtime artifact filename")
    return value


def _safe_remote_path(*parts: str) -> str:
    normalized = PurePosixPath(*[part.strip("/") for part in parts if part.strip("/")])
    if normalized.is_absolute() or ".." in normalized.parts:
        raise RuntimeError("Unsafe Flashlight runtime artifact path")
    return normalized.as_posix()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n")
        temporary = Path(handle.name)
    temporary.replace(path)


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
