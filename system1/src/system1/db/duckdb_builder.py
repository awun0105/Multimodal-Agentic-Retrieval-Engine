from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd


def write_duckdb(duckdb_path: Path, tables: dict[str, pd.DataFrame]) -> None:
    if duckdb_path.exists():
        duckdb_path.unlink()
    connection = duckdb.connect(str(duckdb_path))
    try:
        for name in ("videos", "shots", "scenes", "keyframes", "text_documents", "vector_map"):
            connection.register("frame", tables[name])
            connection.execute(f"CREATE TABLE {name} AS SELECT * FROM frame")
            connection.unregister("frame")
    finally:
        connection.close()
