from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from pandas.api.types import is_integer_dtype, is_numeric_dtype, is_string_dtype


@dataclass(frozen=True)
class ColumnRequirement:
    names: tuple[str, ...]

    @classmethod
    def one(cls, name: str) -> "ColumnRequirement":
        return cls((name,))

    @classmethod
    def any_of(cls, *names: str) -> "ColumnRequirement":
        return cls(tuple(names))

    @property
    def label(self) -> str:
        return " or ".join(self.names)

    def resolve(self, columns: set[str]) -> str | None:
        for name in self.names:
            if name in columns:
                return name
        return None


@dataclass(frozen=True)
class TableSchemaSpec:
    table_name: str
    relative_path: Path
    required: bool
    required_columns: tuple[ColumnRequirement, ...]
    non_null_columns: tuple[ColumnRequirement, ...] = ()
    unique_keys: tuple[tuple[ColumnRequirement, ...], ...] = ()
    numeric_columns: tuple[ColumnRequirement, ...] = ()
    integer_columns: tuple[ColumnRequirement, ...] = ()
    text_columns: tuple[ColumnRequirement, ...] = ()


@dataclass(frozen=True)
class SchemaValidationResult:
    status: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    tables: dict[str, dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "tables": self.tables,
        }


def column(name: str) -> ColumnRequirement:
    return ColumnRequirement.one(name)


def any_column(*names: str) -> ColumnRequirement:
    return ColumnRequirement.any_of(*names)


TABLE_SCHEMA_SPECS: tuple[TableSchemaSpec, ...] = (
    TableSchemaSpec(
        "videos",
        Path("tables/videos.parquet"),
        True,
        (column("video_id"), column("video_ref")),
        non_null_columns=(column("video_id"),),
        unique_keys=((column("video_id"),),),
        text_columns=(column("video_id"), column("video_ref")),
    ),
    TableSchemaSpec(
        "keyframes",
        Path("tables/keyframes.parquet"),
        True,
        (column("keyframe_id"), column("video_id"), column("frame_id"), column("keyframe_ref"), column("thumbnail_ref")),
        non_null_columns=(column("keyframe_id"), column("video_id")),
        unique_keys=((column("keyframe_id"),),),
        integer_columns=(column("frame_id"),),
        text_columns=(column("keyframe_id"), column("video_id"), column("keyframe_ref"), column("thumbnail_ref")),
    ),
    TableSchemaSpec(
        "shots",
        Path("tables/shots.parquet"),
        True,
        (column("shot_id"), column("video_id"), column("start_frame"), column("end_frame")),
        non_null_columns=(column("shot_id"), column("video_id")),
        unique_keys=((column("shot_id"),),),
        integer_columns=(column("start_frame"), column("end_frame")),
        text_columns=(column("shot_id"), column("video_id")),
    ),
    TableSchemaSpec(
        "scenes",
        Path("tables/scenes.parquet"),
        True,
        (column("scene_id"), column("video_id"), column("start_frame"), column("end_frame")),
        non_null_columns=(column("scene_id"), column("video_id")),
        unique_keys=((column("scene_id"),),),
        integer_columns=(column("start_frame"), column("end_frame")),
        text_columns=(column("scene_id"), column("video_id")),
    ),
    TableSchemaSpec(
        "asr_segments",
        Path("tables/asr_segments.parquet"),
        False,
        (column("video_id"), any_column("start_sec", "start_seconds"), any_column("end_sec", "end_seconds"), column("text")),
        non_null_columns=(column("video_id"),),
        numeric_columns=(any_column("start_sec", "start_seconds"), any_column("end_sec", "end_seconds")),
        text_columns=(column("video_id"), column("text")),
    ),
    TableSchemaSpec(
        "embeddings_meta",
        Path("tables/embeddings_meta.parquet"),
        True,
        (column("embedding_id"), column("keyframe_id"), column("video_id")),
        non_null_columns=(column("embedding_id"), column("keyframe_id"), column("video_id")),
        unique_keys=((column("embedding_id"),),),
        text_columns=(column("embedding_id"), column("keyframe_id"), column("video_id")),
    ),
    TableSchemaSpec(
        "ocr",
        Path("tables/ocr.parquet"),
        False,
        (column("keyframe_id"), column("video_id"), column("text")),
        non_null_columns=(column("keyframe_id"), column("video_id")),
        text_columns=(column("keyframe_id"), column("video_id"), column("text")),
    ),
    TableSchemaSpec(
        "objects",
        Path("tables/objects.parquet"),
        False,
        (column("keyframe_id"), column("video_id"), column("label")),
        non_null_columns=(column("keyframe_id"), column("video_id")),
        text_columns=(column("keyframe_id"), column("video_id"), column("label")),
    ),
    TableSchemaSpec(
        "image_captions",
        Path("tables/image_captions.parquet"),
        False,
        (column("keyframe_id"), column("video_id")),
        non_null_columns=(column("keyframe_id"), column("video_id")),
        text_columns=(column("keyframe_id"), column("video_id")),
    ),
    TableSchemaSpec(
        "shot_captions",
        Path("tables/shot_captions.parquet"),
        False,
        (column("shot_id"), column("video_id")),
        non_null_columns=(column("shot_id"), column("video_id")),
        text_columns=(column("shot_id"), column("video_id")),
    ),
    TableSchemaSpec(
        "scene_summaries",
        Path("tables/scene_summaries.parquet"),
        False,
        (column("scene_id"), column("video_id")),
        non_null_columns=(column("scene_id"), column("video_id")),
        text_columns=(column("scene_id"), column("video_id")),
    ),
    TableSchemaSpec(
        "scene_summaries_enriched",
        Path("tables/scene_summaries_enriched.parquet"),
        False,
        (column("scene_id"), column("video_id")),
        non_null_columns=(column("scene_id"), column("video_id")),
        text_columns=(column("scene_id"), column("video_id")),
    ),
    TableSchemaSpec(
        "text_sources",
        Path("tables/text_sources.parquet"),
        True,
        (column("video_id"), column("source_type"), any_column("raw_text", "normalized_text")),
        non_null_columns=(column("video_id"), column("source_type")),
        text_columns=(column("video_id"), column("source_type"), any_column("raw_text", "normalized_text")),
    ),
    TableSchemaSpec(
        "text_documents",
        Path("tables/text_documents.parquet"),
        True,
        (any_column("doc_id", "document_id"), column("video_id"), any_column("source_type", "source_types"), any_column("raw_text", "normalized_text")),
        non_null_columns=(any_column("doc_id", "document_id"), column("video_id"), any_column("source_type", "source_types")),
        unique_keys=((any_column("doc_id", "document_id"),),),
        text_columns=(any_column("doc_id", "document_id"), column("video_id"), any_column("source_type", "source_types")),
    ),
    TableSchemaSpec(
        "vector_map",
        Path("indexes/vector_map.parquet"),
        True,
        (column("index_name"), column("vector_id"), column("keyframe_id"), column("video_id")),
        non_null_columns=(column("index_name"), column("vector_id"), column("keyframe_id"), column("video_id")),
        unique_keys=((column("index_name"), column("vector_id")),),
        integer_columns=(column("vector_id"),),
        text_columns=(column("index_name"), column("keyframe_id"), column("video_id")),
    ),
    TableSchemaSpec(
        "feature_availability",
        Path("tables/feature_availability.parquet"),
        True,
        (any_column("entity_level", "entity_type"), column("entity_id"), column("video_id"), column("status")),
        non_null_columns=(any_column("entity_level", "entity_type"), column("entity_id"), column("video_id"), column("status")),
        text_columns=(any_column("entity_level", "entity_type"), column("entity_id"), column("video_id"), column("status")),
    ),
)


def validate_release_tables(release_dir: Path | str) -> SchemaValidationResult:
    release_path = Path(release_dir)
    errors: list[str] = []
    warnings: list[str] = []
    table_reports: dict[str, dict[str, Any]] = {}

    for spec in TABLE_SCHEMA_SPECS:
        path = release_path / spec.relative_path
        if not path.exists():
            message = f"schema validation: missing {'required' if spec.required else 'optional'} table: {spec.relative_path}"
            if spec.required:
                errors.append(message)
                table_reports[spec.table_name] = {"status": "fail", "path": str(spec.relative_path), "error": "missing required table"}
            else:
                warnings.append(message)
                table_reports[spec.table_name] = {"status": "skipped", "path": str(spec.relative_path), "warning": "missing optional table"}
            continue

        try:
            frame = pd.read_parquet(path)
        except Exception as exc:
            errors.append(f"schema validation: {spec.table_name} could not be read: {exc}")
            table_reports[spec.table_name] = {"status": "fail", "path": str(spec.relative_path), "error": str(exc)}
            continue

        table_errors = validate_table_schema(spec.table_name, frame, spec)
        errors.extend(table_errors)
        table_reports[spec.table_name] = {
            "status": "fail" if table_errors else "pass",
            "path": str(spec.relative_path),
            "row_count": int(len(frame)),
            "column_count": int(len(frame.columns)),
            "resolved_columns": resolved_column_map(frame, spec),
        }

    return SchemaValidationResult(
        status="fail" if errors else "pass",
        errors=tuple(errors),
        warnings=tuple(warnings),
        tables=table_reports,
    )


def validate_table_schema(table_name: str, dataframe: pd.DataFrame, spec: TableSchemaSpec) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_required_columns(table_name, dataframe, spec.required_columns))
    errors.extend(validate_non_null_columns(table_name, dataframe, spec.non_null_columns))
    for key_columns in spec.unique_keys:
        errors.extend(validate_unique_key(table_name, dataframe, key_columns))
    errors.extend(validate_column_types(table_name, dataframe, spec))
    return errors


def validate_required_columns(
    table_name: str,
    dataframe: pd.DataFrame,
    required_columns: tuple[ColumnRequirement, ...],
) -> list[str]:
    columns = set(dataframe.columns)
    errors: list[str] = []
    for requirement in required_columns:
        if requirement.resolve(columns) is None:
            errors.append(f"schema validation: {table_name} missing required column: {requirement.label}")
    return errors


def validate_non_null_columns(
    table_name: str,
    dataframe: pd.DataFrame,
    non_null_columns: tuple[ColumnRequirement, ...],
) -> list[str]:
    columns = set(dataframe.columns)
    errors: list[str] = []
    for requirement in non_null_columns:
        column_name = requirement.resolve(columns)
        if column_name is None:
            continue
        null_count = int(dataframe[column_name].isna().sum())
        if null_count:
            errors.append(f"schema validation: {table_name}.{column_name} has {null_count} null values")
    return errors


def validate_unique_key(
    table_name: str,
    dataframe: pd.DataFrame,
    key_columns: tuple[ColumnRequirement, ...],
) -> list[str]:
    columns = set(dataframe.columns)
    resolved_columns = [requirement.resolve(columns) for requirement in key_columns]
    if any(column_name is None for column_name in resolved_columns):
        return []
    key_names = [str(column_name) for column_name in resolved_columns]
    if dataframe.empty:
        return []
    duplicate_groups = dataframe.groupby(key_names, dropna=False).size()
    duplicate_count = int((duplicate_groups > 1).sum())
    if not duplicate_count:
        return []
    return [f"schema validation: {table_name} duplicate primary key {','.join(key_names)}: {duplicate_count} duplicate groups"]


def validate_column_types(table_name: str, dataframe: pd.DataFrame, spec: TableSchemaSpec) -> list[str]:
    columns = set(dataframe.columns)
    errors: list[str] = []
    for requirement in spec.integer_columns:
        column_name = requirement.resolve(columns)
        if column_name is not None and not is_integer_dtype(dataframe[column_name]):
            errors.append(f"schema validation: {table_name}.{column_name} must be integer dtype")
    for requirement in spec.numeric_columns:
        column_name = requirement.resolve(columns)
        if column_name is not None and not is_numeric_dtype(dataframe[column_name]):
            errors.append(f"schema validation: {table_name}.{column_name} must be numeric dtype")
    for requirement in spec.text_columns:
        column_name = requirement.resolve(columns)
        if column_name is not None and not _is_text_compatible(dataframe[column_name]):
            errors.append(f"schema validation: {table_name}.{column_name} must be text-compatible dtype")
    return errors


def resolved_column_map(dataframe: pd.DataFrame, spec: TableSchemaSpec) -> dict[str, str | None]:
    columns = set(dataframe.columns)
    requirements = set(spec.required_columns)
    requirements.update(spec.non_null_columns)
    for key_columns in spec.unique_keys:
        requirements.update(key_columns)
    requirements.update(spec.numeric_columns)
    requirements.update(spec.integer_columns)
    requirements.update(spec.text_columns)
    return {requirement.label: requirement.resolve(columns) for requirement in sorted(requirements, key=lambda item: item.label)}


def _is_text_compatible(series: pd.Series) -> bool:
    return is_string_dtype(series) or series.dtype == object
