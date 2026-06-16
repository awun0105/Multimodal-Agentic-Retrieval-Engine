from __future__ import annotations

from pathlib import Path

import typer

from system1.ingest.source_importer import import_organizer_source


def register(app: typer.Typer) -> None:
    @app.command("import-source")
    def import_source(
        source_uri: str = typer.Option(
            ..., "--source-uri", help="Organizer source folder path or Google Drive folder URL."
        ),
        data_root: Path = typer.Option(
            Path("input"), "--data-root", help="Target data root with raw_videos/ and metadata/."
        ),
    ) -> None:
        """Import an organizer source into raw_videos/ and metadata/."""
        result = import_organizer_source(source_uri, data_root)
        typer.echo(
            f"Imported source videos={result.video_count} metadata={result.metadata_count}: {result.report_path}"
        )
