"""Merge OCR part databases into a release's runtime.sqlite and re-sign the
two-tier checksum chain (manifest.json <- READY.json).

Order is mandatory, see phase-06 plan:
  1. write OCR into runtime.sqlite
  2. new sha256 of sqlite -> manifest.artifacts["metadata/runtime.sqlite"].sha256
  3. new size_bytes -> same entry
  4. new sha256 of manifest.json -> READY.json.manifest_sha256

Usage:
    python merge_ocr_into_release.py <release_dir> <part1.sqlite> [<part2.sqlite> ...]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sqlite3
import sys
from pathlib import Path

# Make the app package importable regardless of cwd (tools/ is a subdir of mvp-app).
_MVP_APP_ROOT = Path(__file__).resolve().parent.parent
if str(_MVP_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MVP_APP_ROOT))

from database_utils import _load_manifest, sha256_file  # noqa: E402

ARTIFACT_KEY = "metadata/runtime.sqlite"

# Copied verbatim from mvp-app/db.py:53-70 so future CREATE TABLE IF NOT EXISTS
# calls made by the app never disagree with what we ship.
OCR_TEXTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS ocr_texts (
    keyframe_id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    full_text TEXT NOT NULL,
    FOREIGN KEY (keyframe_id) REFERENCES keyframes (keyframe_id)
);
"""

OCR_BOXES_SCHEMA = """
CREATE TABLE IF NOT EXISTS ocr_boxes (
    box_id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyframe_id TEXT NOT NULL,
    text TEXT NOT NULL,
    score REAL NOT NULL,
    ymin REAL NOT NULL,
    xmin REAL NOT NULL,
    ymax REAL NOT NULL,
    xmax REAL NOT NULL,
    FOREIGN KEY (keyframe_id) REFERENCES keyframes (keyframe_id)
);
"""

OCR_FTS_SCHEMA = "CREATE VIRTUAL TABLE ocr_fts USING fts5(keyframe_id UNINDEXED, full_text);"


def backup_file(path: Path, timestamp: str) -> Path:
    backup_path = path.with_name(f"{path.name}.bak-{timestamp}")
    shutil.copy2(path, backup_path)
    if not backup_path.is_file() or backup_path.stat().st_size == 0:
        raise RuntimeError(f"Backup verification failed for {path} -> {backup_path}")
    return backup_path


def backup_or_die(sqlite_path: Path, manifest_path: Path, ready_path: Path) -> dict[str, Path]:
    timestamp = dt.datetime.now().strftime("%y%m%d-%H%M")
    try:
        backups = {
            "sqlite": backup_file(sqlite_path, timestamp),
            "manifest": backup_file(manifest_path, timestamp),
            "ready": backup_file(ready_path, timestamp),
        }
    except Exception as exc:  # noqa: BLE001 - deliberately broad, this must halt everything
        print(f"BACKUP FAILED, ABORTING: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    return backups


def table_row_count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def preflight_check_part(part_path: Path) -> tuple[int, int, set[str]]:
    """Open a part db, verify ocr_texts/ocr_fts row counts match, return ids."""
    if not part_path.is_file():
        raise FileNotFoundError(f"OCR part not found: {part_path}")
    connection = sqlite3.connect(f"file:{part_path}?mode=ro", uri=True)
    try:
        texts_count = table_row_count(connection, "ocr_texts")
        fts_count = table_row_count(connection, "ocr_fts")
        if texts_count != fts_count:
            raise ValueError(
                f"{part_path}: ocr_texts has {texts_count} rows but ocr_fts has {fts_count}"
            )
        ids = {
            row[0]
            for row in connection.execute("SELECT keyframe_id FROM ocr_texts").fetchall()
        }
    finally:
        connection.close()
    return texts_count, fts_count, ids


def preflight_check_parts(part_paths: list[Path]) -> None:
    seen: set[str] = set()
    for part_path in part_paths:
        texts_count, fts_count, ids = preflight_check_part(part_path)
        overlap = seen & ids
        if overlap:
            print(
                f"WARNING: {len(overlap)} keyframe_id(s) in {part_path.name} "
                "already seen in a previous part (will be replaced, not duplicated)"
            )
        seen |= ids
        print(f"  preflight {part_path.name}: ocr_texts={texts_count} ocr_fts={fts_count}")


def create_ocr_tables(connection: sqlite3.Connection) -> None:
    connection.execute(OCR_TEXTS_SCHEMA)
    connection.execute(OCR_BOXES_SCHEMA)
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ocr_fts'"
    ).fetchone()
    if not exists:
        connection.execute(OCR_FTS_SCHEMA)


def merge_parts(sqlite_path: Path, part_paths: list[Path]) -> int:
    connection = sqlite3.connect(sqlite_path)
    try:
        create_ocr_tables(connection)
        for index, part_path in enumerate(part_paths):
            alias = f"part{index}"
            connection.execute(f"ATTACH DATABASE ? AS {alias}", (str(part_path),))
            try:
                connection.execute(
                    f"INSERT OR REPLACE INTO ocr_texts (keyframe_id, video_id, full_text) "
                    f"SELECT keyframe_id, video_id, full_text FROM {alias}.ocr_texts"
                )
                connection.commit()  # release the read lock on the attached part before DETACH
            finally:
                connection.execute(f"DETACH DATABASE {alias}")

        # Rebuild ocr_fts from ocr_texts (the merged source of truth) so the two
        # tables always agree in row count, even if parts had overlapping ids.
        connection.execute("DELETE FROM ocr_fts")
        connection.execute(
            "INSERT INTO ocr_fts(keyframe_id, full_text) SELECT keyframe_id, full_text FROM ocr_texts"
        )
        connection.commit()

        merged_count = table_row_count(connection, "ocr_texts")
        fts_count = table_row_count(connection, "ocr_fts")
        if merged_count != fts_count:
            raise RuntimeError(
                f"Post-merge mismatch: ocr_texts={merged_count} ocr_fts={fts_count}"
            )
    finally:
        connection.close()
    return merged_count


def update_manifest(manifest_path: Path, sqlite_path: Path) -> tuple[dict, str, int, str, int]:
    """Update the single metadata/runtime.sqlite entry in manifest.json.

    Returns (manifest, old_sha, old_size, new_sha, new_size).
    """
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = manifest["artifacts"]
    assert ARTIFACT_KEY in artifacts, f"manifest missing expected key {ARTIFACT_KEY!r}"

    old_entry = artifacts[ARTIFACT_KEY]
    old_sha = str(old_entry["sha256"])
    old_size = int(old_entry["size_bytes"])

    new_sha = sha256_file(sqlite_path)
    new_size = sqlite_path.stat().st_size

    artifacts[ARTIFACT_KEY] = {"size_bytes": new_size, "sha256": new_sha}
    assert len(manifest["artifacts"]) == 8, (
        f"expected 8 artifact entries, got {len(manifest['artifacts'])} "
        "(a new key may have been created by a path separator mismatch)"
    )

    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest, old_sha, old_size, new_sha, new_size


def update_ready(ready_path: Path, manifest_path: Path) -> tuple[str, str]:
    ready = json.loads(ready_path.read_text(encoding="utf-8"))
    old_manifest_sha256 = str(ready.get("manifest_sha256") or "")
    new_manifest_sha256 = sha256_file(manifest_path)
    ready["manifest_sha256"] = new_manifest_sha256
    ready_path.write_text(json.dumps(ready, indent=2), encoding="utf-8")
    return old_manifest_sha256, new_manifest_sha256


def self_check(data_root: Path, sqlite_path: Path) -> None:
    manifest = _load_manifest(data_root)  # raises if tier 1 is broken
    expected_sha = manifest["artifacts"][ARTIFACT_KEY]["sha256"]
    actual_sha = sha256_file(sqlite_path)
    if actual_sha != expected_sha:
        raise RuntimeError(
            f"Tier 2 self-check failed: sqlite sha256 {actual_sha} != manifest {expected_sha}"
        )


def run(release_dir: Path, part_paths: list[Path], report_path: Path | None) -> None:
    sqlite_path = release_dir / "metadata" / "runtime.sqlite"
    manifest_path = release_dir / "manifest.json"
    ready_path = release_dir / "READY.json"

    for path in (sqlite_path, manifest_path, ready_path):
        if not path.is_file():
            raise FileNotFoundError(f"Required release file not found: {path}")

    print(f"Release dir: {release_dir}")
    print(f"Parts ({len(part_paths)}): {[str(p) for p in part_paths]}")

    print("\n[0] Backing up 3 files...")
    backups = backup_or_die(sqlite_path, manifest_path, ready_path)
    for label, backup_path in backups.items():
        print(f"  {label}: {backup_path} ({backup_path.stat().st_size} bytes)")

    old_manifest_entry = json.loads(manifest_path.read_text(encoding="utf-8"))["artifacts"][
        ARTIFACT_KEY
    ]
    old_ready = json.loads(ready_path.read_text(encoding="utf-8"))
    print(f"\nOld sqlite sha256:  {old_manifest_entry['sha256']}")
    print(f"Old sqlite size:    {old_manifest_entry['size_bytes']}")
    print(f"Old manifest_sha256: {old_ready.get('manifest_sha256')}")

    print("\n[1] Preflight checking parts...")
    preflight_check_parts(part_paths)

    print("\n[2] Merging OCR into runtime.sqlite...")
    merged_count = merge_parts(sqlite_path, part_paths)
    print(f"  ocr_texts rows after merge: {merged_count}")

    print("\n[3] Updating manifest.json checksum for metadata/runtime.sqlite...")
    manifest, old_sha, old_size, new_sha, new_size = update_manifest(manifest_path, sqlite_path)

    print("\n[4] Updating READY.json manifest_sha256...")
    old_manifest_sha256, new_manifest_sha256 = update_ready(ready_path, manifest_path)

    print("\n[5] Self-check via app's real _load_manifest()...")
    self_check(release_dir, sqlite_path)
    print("  OK - tier 1 and tier 2 both verified")

    summary_lines = [
        "## Ket qua gop OCR",
        "",
        f"- ocr_texts rows (merged): {merged_count}",
        f"- sqlite sha256: {old_sha} -> {new_sha}",
        f"- sqlite size_bytes: {old_size} -> {new_size}",
        f"- manifest_sha256 (READY.json): {old_manifest_sha256} -> {new_manifest_sha256}",
        f"- artifacts entries: {len(manifest['artifacts'])}",
        f"- backups: {', '.join(str(p) for p in backups.values())}",
    ]
    summary = "\n".join(summary_lines)
    print("\n" + summary)

    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(summary + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_dir", type=Path, help="Path to the release directory")
    parser.add_argument(
        "parts", type=Path, nargs="+", help="One or more OCR part sqlite files"
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Optional path to write a summary report to",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run(args.release_dir.resolve(), [p.resolve() for p in args.parts], args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
