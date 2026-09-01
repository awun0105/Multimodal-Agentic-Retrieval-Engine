#!/usr/bin/env python3
"""Build and verify the project-owned CPython 3.13 Flashlight decoder wheel."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path


FLASHLIGHT_VERSION = "0.0.7"
FLASHLIGHT_SDIST = "flashlight-text-0.0.7.tar.gz"
FLASHLIGHT_SDIST_SHA256 = (
    "fb63779b4b642c0c59e66386f43db8357836ed1be82b49d30155f7c39136d836"
)
FLASHLIGHT_SDIST_URL = (
    "https://files.pythonhosted.org/packages/3a/b8/83f5a6a5aae7acc9289acd0c1e9ef954ccb881a912019f7bbb35f7d3a4cb/"
    "flashlight-text-0.0.7.tar.gz"
)
KENLM_REVISION = "5bf7b46558e1c5595bf3b8c9b0b1f9d8d257040a"
KENLM_SDIST = f"kenlm-{KENLM_REVISION}.tar.gz"
KENLM_SDIST_SHA256 = (
    "e706ce2a4b82a3cd93417012dbb04fc11e5c06b89c4fffde35c5761f4f034bf8"
)
KENLM_SDIST_URL = (
    "https://codeload.github.com/jacobkahn/kenlm/tar.gz/"
    f"{KENLM_REVISION}"
)
MANIFEST_SCHEMA = "phase01_flashlight_runtime_manifest_v1"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=2)
    arguments = parser.parse_args()
    if sys.version_info[:2] != (3, 13):
        raise RuntimeError("Flashlight runtime artifact must be built with CPython 3.13")
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "amd64"}:
        raise RuntimeError("Flashlight runtime artifact requires Linux x86_64")
    for executable in ("cmake", "g++", "patchelf"):
        if shutil.which(executable) is None:
            raise RuntimeError(f"Required build executable is unavailable: {executable}")

    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="system1_flashlight_build_") as temporary:
        root = Path(temporary)
        source_dist = root / "source_dist"
        source_dist.mkdir()
        flashlight_sdist = source_dist / FLASHLIGHT_SDIST
        kenlm_sdist = source_dist / KENLM_SDIST
        urllib.request.urlretrieve(FLASHLIGHT_SDIST_URL, flashlight_sdist)
        urllib.request.urlretrieve(KENLM_SDIST_URL, kenlm_sdist)
        _verify(flashlight_sdist, FLASHLIGHT_SDIST_SHA256)
        _verify(kenlm_sdist, KENLM_SDIST_SHA256)

        flashlight_source = _extract_sdist(flashlight_sdist, root / "flashlight")
        kenlm_source = _extract_sdist(kenlm_sdist, root / "kenlm")
        _patch_flashlight_kenlm_source(flashlight_source / "setup.py")

        build_env = {
            **os.environ,
            "CMAKE_BUILD_PARALLEL_LEVEL": str(max(1, arguments.jobs)),
            "MAX_JOBS": str(max(1, arguments.jobs)),
        }
        kenlm_build = root / "kenlm_build"
        _run(
            [
                "cmake",
                "-S",
                str(kenlm_source),
                "-B",
                str(kenlm_build),
                "-DCMAKE_BUILD_TYPE=Release",
                "-DCMAKE_POLICY_VERSION_MINIMUM=3.5",
                "-DBUILD_SHARED_LIBS=ON",
                "-DKENLM_BUILD_TESTS=OFF",
                "-DKENLM_BUILD_EXAMPLES=OFF",
                "-DKENLM_BUILD_BENCHMARKS=OFF",
            ],
            env=build_env,
        )
        _run(
            [
                "cmake",
                "--build",
                str(kenlm_build),
                "--target",
                "kenlm",
                "--parallel",
                str(max(1, arguments.jobs)),
            ],
            env=build_env,
        )
        kenlm_library = _one(
            kenlm_build.rglob("libkenlm.so"),
            "KenLM shared library",
        )

        wheelhouse = root / "wheelhouse"
        wheelhouse.mkdir()
        build_env["SYSTEM1_KENLM_SOURCE_DIR"] = str(kenlm_source)
        build_env["SYSTEM1_KENLM_LIBRARY_DIR"] = str(kenlm_library.parent)
        build_env["SYSTEM1_PYBIND11_CMAKE_DIR"] = subprocess.check_output(
            [sys.executable, "-m", "pybind11", "--cmakedir"],
            text=True,
        ).strip()
        build_env["BUILD_VERSION"] = FLASHLIGHT_VERSION
        build_env["USE_KENLM"] = "1"
        _run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--disable-pip-version-check",
                "--no-deps",
                "--no-build-isolation",
                "--wheel-dir",
                str(wheelhouse),
                str(flashlight_source),
            ],
            env=build_env,
        )
        native_wheel = _one(
            wheelhouse.glob("flashlight_text-0.0.7-*.whl"),
            "Flashlight wheel",
        )
        repaired = root / "repaired"
        repaired.mkdir()
        _run(
            [
                sys.executable,
                "-m",
                "auditwheel",
                "repair",
                "--plat",
                "manylinux_2_17_x86_64",
                "--wheel-dir",
                str(repaired),
                str(native_wheel),
            ]
        )
        final_wheel = _one(repaired.glob("flashlight_text-0.0.7-*.whl"), "repaired wheel")
        destination = output / final_wheel.name
        shutil.copy2(final_wheel, destination)
        _verify_wheel(destination, expected_version=FLASHLIGHT_VERSION)
        manifest = {
            "schema_version": MANIFEST_SCHEMA,
            "package_name": "flashlight-text",
            "package_version": FLASHLIGHT_VERSION,
            "python_tag": "cp313",
            "platform": "linux_x86_64",
            "wheel": {
                "filename": destination.name,
                "sha256": _sha256(destination),
                "size_bytes": destination.stat().st_size,
            },
            "sources": {
                "flashlight_text": {
                    "version": FLASHLIGHT_VERSION,
                    "filename": FLASHLIGHT_SDIST,
                    "sha256": FLASHLIGHT_SDIST_SHA256,
                },
                "kenlm": {
                    "revision": KENLM_REVISION,
                    "filename": KENLM_SDIST,
                    "sha256": KENLM_SDIST_SHA256,
                },
            },
        }
        manifest_path = output / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({
            "manifest": str(manifest_path),
            "manifest_sha256": _sha256(manifest_path),
            "wheel": str(destination),
            "wheel_sha256": _sha256(destination),
        }, indent=2, sort_keys=True))


def _patch_flashlight_kenlm_source(setup_path: Path) -> None:
    source = setup_path.read_text(encoding="utf-8")
    start = source.index("def get_kenlm_paths(_basedir: str) -> str:\n")
    end = source.index("\n\nclass CMakeExtension", start)
    replacement = '''def get_kenlm_paths(_basedir: str) -> str:
    source_dir = os.environ.get("SYSTEM1_KENLM_SOURCE_DIR")
    library_dir = os.environ.get("SYSTEM1_KENLM_LIBRARY_DIR")
    if not source_dir or not library_dir:
        raise RuntimeError("Pinned KenLM C++ source and library are required")
    # Flashlight 0.0.7's Findkenlm.cmake expects the hint to contain
    # model.hh directly; it derives the repository include root from it.
    return Path(source_dir) / "lm", Path(library_dir)
'''
    source = source[:start] + replacement + source[end:]
    cmake_anchor = '            "-DKENLM_HEADER_PATH=" + str(kenlm_header_path),\n'
    if source.count(cmake_anchor) != 1:
        raise RuntimeError("Unexpected Flashlight CMake argument layout")
    source = source.replace(
        cmake_anchor,
        cmake_anchor
        + '            "-DCMAKE_POLICY_VERSION_MINIMUM=3.5",\n'
        + '            "-Dpybind11_DIR="\n'
        + '            + os.environ["SYSTEM1_PYBIND11_CMAKE_DIR"],\n',
    )
    setup_path.write_text(source, encoding="utf-8")


def _extract_sdist(archive: Path, destination: Path) -> Path:
    destination.mkdir()
    with tarfile.open(archive, "r:gz") as handle:
        root = destination.resolve()
        for member in handle.getmembers():
            resolved = (destination / member.name).resolve()
            if root not in resolved.parents and resolved != root:
                raise RuntimeError(f"Unsafe source archive member: {member.name}")
        handle.extractall(destination, filter="data")
    directories = [path for path in destination.iterdir() if path.is_dir()]
    return _one(iter(directories), f"source root for {archive.name}")


def _verify_wheel(wheel: Path, *, expected_version: str) -> None:
    with tempfile.TemporaryDirectory(prefix="system1_flashlight_verify_") as temporary:
        environment = Path(temporary) / "venv"
        _run([sys.executable, "-m", "venv", str(environment)])
        python = environment / "bin" / "python"
        _run([str(python), "-m", "pip", "install", "--no-deps", str(wheel)])
        _run(
            [
                str(python),
                "-c",
                (
                    "import importlib.metadata as m; "
                    "from flashlight.lib.text.decoder import KenLM; "
                    f"assert m.version('flashlight-text') == '{expected_version}'; "
                    "assert KenLM is not None"
                ),
            ]
        )


def _verify(path: Path, expected: str) -> None:
    if not path.is_file() or _sha256(path) != expected:
        raise RuntimeError(f"Source checksum mismatch: {path.name}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _one(values: object, label: str) -> Path:
    items = list(values)  # type: ignore[arg-type]
    if len(items) != 1:
        raise RuntimeError(f"Expected exactly one {label}; found {len(items)}")
    return Path(items[0])


def _run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    subprocess.run(command, env=env, check=True)


if __name__ == "__main__":
    main()
