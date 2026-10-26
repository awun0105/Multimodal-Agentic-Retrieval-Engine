from __future__ import annotations

from pathlib import Path

import typer

from system1.commands.common import default_output, release_dir
from system1.release.sync import (
    download_phase00_ingestion_from_hf,
    upload_phase00_ingestion_to_hf,
)


def register(app: typer.Typer) -> None:
    @app.command("sync-phase00-ingestion")
    def sync_phase00_ingestion(
        output: Path = typer.Option(default_output(), "--output", "-o"),
        hf_repo_id: str = typer.Option(..., "--hf-repo-id"),
        hf_prefix: str = typer.Option("", "--hf-prefix"),
        hf_repo_type: str = typer.Option("dataset", "--hf-repo-type"),
        hf_revision: str = typer.Option("main", "--hf-revision"),
    ) -> None:
        """Upload Notebook 00 ingestion artifacts using the phase00_ingestion HF layout."""
        result = upload_phase00_ingestion_to_hf(
            release_dir(output),
            repo_id=hf_repo_id,
            prefix=hf_prefix,
            repo_type=hf_repo_type,
            revision=hf_revision,
        )
        typer.echo(f"Synced phase00 ingestion files={result.file_count}: {result.manifest_path}")

    @app.command("restore-phase00-ingestion")
    def restore_phase00_ingestion(
        output: Path = typer.Option(default_output(), "--output", "-o"),
        release_id: str = typer.Option("competition_dataset_v001", "--release-id"),
        hf_repo_id: str = typer.Option(..., "--hf-repo-id"),
        hf_prefix: str = typer.Option("", "--hf-prefix"),
        hf_repo_type: str = typer.Option("dataset", "--hf-repo-type"),
        hf_revision: str = typer.Option("main", "--hf-revision"),
        overwrite: bool = typer.Option(True, "--overwrite/--no-overwrite"),
    ) -> None:
        """Restore phase00_ingestion artifacts from a Hugging Face Dataset repo."""
        result = download_phase00_ingestion_from_hf(
            output,
            release_id=release_id,
            repo_id=hf_repo_id,
            prefix=hf_prefix,
            repo_type=hf_repo_type,
            revision=hf_revision,
            overwrite=overwrite,
        )
        typer.echo(f"Restored phase00 ingestion files={result.file_count}: {result.release_dir}")
