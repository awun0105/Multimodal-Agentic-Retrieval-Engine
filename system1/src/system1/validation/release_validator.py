from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path


REQUIRED_FILES = (
    "db/app.sqlite",
    "indexes/index_version.json",
    "tables/videos.parquet",
    "tables/keyframes.parquet",
    "tables/text_documents.parquet",
    "tables/vector_map.parquet",
    "tables/feature_availability.parquet",
    "manifests/dataset_manifest.json",
)

REQUIRED_TABLES = (
    "videos",
    "keyframes",
    "text_documents",
    "vector_map",
    "feature_availability",
    "release_capabilities",
    "text_documents_fts",
)

MEDIA_REF_COLUMNS = {
    "videos": ("video_ref",),
    "keyframes": ("keyframe_ref", "thumbnail_ref"),
}


@dataclass(frozen=True)
class ValidationResult:
    release_dir: Path
    status: str
    errors: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.status == "pass"


def validate_release(release_dir: Path | str) -> ValidationResult:
    release_path = Path(release_dir)
    errors: list[str] = []

    _check_required_files(release_path, errors)
    sqlite_path = release_path / "db" / "app.sqlite"
    if sqlite_path.exists():
        _check_sqlite(sqlite_path, errors)

    result = ValidationResult(
        release_dir=release_path,
        status="pass" if not errors else "fail",
        errors=tuple(errors),
    )
    _write_validation_outputs(release_path, result)
    return result


def _check_required_files(release_path: Path, errors: list[str]) -> None:
    for relative_path in REQUIRED_FILES:
        if not (release_path / relative_path).exists():
            errors.append(f"missing required file: {relative_path}")


def _check_sqlite(sqlite_path: Path, errors: list[str]) -> None:
    with sqlite3.connect(sqlite_path) as connection:
        table_names = _table_names(connection)
        for table_name in REQUIRED_TABLES:
            if table_name not in table_names:
                errors.append(f"missing required SQLite table: {table_name}")

        if not all(table_name in table_names for table_name in ("videos", "keyframes", "text_documents", "vector_map")):
            return

        _check_media_refs(connection, errors)
        _check_keyframes(connection, errors)
        _check_vector_map(connection, errors)
        _check_text_documents(connection, table_names, errors)


def _table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual')").fetchall()
    return {row[0] for row in rows}


def _check_media_refs(connection: sqlite3.Connection, errors: list[str]) -> None:
    for table_name, column_names in MEDIA_REF_COLUMNS.items():
        for column_name in column_names:
            rows = connection.execute(f"SELECT {column_name} FROM {table_name}").fetchall()
            for (value,) in rows:
                if not isinstance(value, str):
                    errors.append(f"{table_name}.{column_name} is not text")
                    continue
                if value.startswith("/") or value.startswith("file://"):
                    errors.append(f"{table_name}.{column_name} stores an absolute path: {value}")
                if not value.startswith("media://"):
                    errors.append(f"{table_name}.{column_name} must use media:// refs: {value}")


def _check_keyframes(connection: sqlite3.Connection, errors: list[str]) -> None:
    rows = connection.execute("SELECT keyframe_id, video_id, frame_id FROM keyframes").fetchall()
    for keyframe_id, video_id, frame_id in rows:
        if not isinstance(frame_id, int):
            errors.append(f"keyframes.frame_id must be integer for {keyframe_id}")
            continue
        expected_keyframe_id = f"{video_id}:{frame_id}"
        if keyframe_id != expected_keyframe_id:
            errors.append(f"keyframe_id mismatch: expected {expected_keyframe_id}, got {keyframe_id}")


def _check_vector_map(connection: sqlite3.Connection, errors: list[str]) -> None:
    rows = connection.execute(
        """
        SELECT vector_map.keyframe_id
        FROM vector_map
        LEFT JOIN keyframes ON vector_map.keyframe_id = keyframes.keyframe_id
        WHERE keyframes.keyframe_id IS NULL
        """
    ).fetchall()
    for (keyframe_id,) in rows:
        errors.append(f"vector_map.keyframe_id does not resolve: {keyframe_id}")


def _check_text_documents(connection: sqlite3.Connection, table_names: set[str], errors: list[str]) -> None:
    rows = connection.execute("SELECT document_id, entity_type, entity_id FROM text_documents").fetchall()
    for document_id, entity_type, entity_id in rows:
        entity_table = _entity_table(entity_type)
        if entity_table is None or entity_table not in table_names:
            errors.append(f"text_documents.entity_type is not implemented for {document_id}: {entity_type}")
            continue
        id_column = "keyframe_id" if entity_table == "keyframes" else "video_id"
        exists = connection.execute(
            f"SELECT 1 FROM {entity_table} WHERE {id_column} = ? LIMIT 1",
            (entity_id,),
        ).fetchone()
        if exists is None:
            errors.append(f"text_documents.entity_id does not resolve for {document_id}: {entity_id}")


def _entity_table(entity_type: str) -> str | None:
    return {"video": "videos", "keyframe": "keyframes"}.get(entity_type)


def _write_validation_outputs(release_path: Path, result: ValidationResult) -> None:
    manifests_dir = release_path / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "status": result.status,
        "error_count": len(result.errors),
        "errors": list(result.errors),
    }
    (manifests_dir / "validation_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (manifests_dir / "validation_errors.jsonl").open("w", encoding="utf-8") as error_file:
        for error in result.errors:
            error_file.write(json.dumps({"error": error}, sort_keys=True) + "\n")
