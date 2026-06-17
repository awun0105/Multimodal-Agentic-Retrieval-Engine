from __future__ import annotations

from pathlib import Path
import json
import zipfile

import typer

from system1.artifacts.checkpoint import checkpoint_status, restore_checkpoint, save_checkpoint
from system1.release.types import DEFAULT_RELEASE_ID


def _exit_with_error(exc: Exception) -> None:
    typer.echo(f"Error: {exc}", err=True)
    raise typer.Exit(1)


def register(app: typer.Typer) -> None:
    @app.command("checkpoint-status")
    def checkpoint_status_command(
        artifact_root: Path = typer.Option(..., "--artifact-root"),
        release_id: str = typer.Option(DEFAULT_RELEASE_ID, "--release-id"),
    ) -> None:
        """Print checkpoint registry status from the artifact store."""
        try:
            status = checkpoint_status(artifact_root, release_id=release_id)
        except (FileNotFoundError, FileExistsError, ValueError, zipfile.BadZipFile) as exc:
            _exit_with_error(exc)
        typer.echo(json.dumps(status, indent=2, sort_keys=True))

    @app.command("checkpoint-save")
    def checkpoint_save_command(
        phase: str = typer.Option(..., "--phase"),
        release: Path = typer.Option(..., "--release"),
        artifact_root: Path = typer.Option(..., "--artifact-root"),
        batch_id: str | None = typer.Option(None, "--batch-id"),
        worker_id: str | None = typer.Option(None, "--worker-id"),
        status: str = typer.Option("pass", "--status"),
    ) -> None:
        """Save a release phase checkpoint into the artifact store."""
        try:
            checkpoint_path = save_checkpoint(
                release,
                artifact_root,
                phase,
                batch_id=batch_id,
                worker_id=worker_id,
                status=status,
            )
        except (FileNotFoundError, FileExistsError, ValueError, zipfile.BadZipFile) as exc:
            _exit_with_error(exc)
        typer.echo(str(checkpoint_path))

    @app.command("checkpoint-restore")
    def checkpoint_restore_command(
        phase: str = typer.Option(..., "--phase"),
        output: Path = typer.Option(..., "--output"),
        artifact_root: Path = typer.Option(..., "--artifact-root"),
        batch_id: str | None = typer.Option(None, "--batch-id"),
        release_id: str = typer.Option(DEFAULT_RELEASE_ID, "--release-id"),
        overwrite: bool = typer.Option(True, "--overwrite/--no-overwrite"),
    ) -> None:
        """Restore a release phase checkpoint from the artifact store."""
        try:
            release_dir = restore_checkpoint(
                output,
                artifact_root,
                phase,
                batch_id=batch_id,
                release_id=release_id,
                overwrite=overwrite,
            )
        except (FileNotFoundError, FileExistsError, ValueError, zipfile.BadZipFile) as exc:
            _exit_with_error(exc)
        typer.echo(str(release_dir))
