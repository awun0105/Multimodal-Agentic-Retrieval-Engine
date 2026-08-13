from __future__ import annotations

from pathlib import Path
import zipfile

import typer

from system1.commands.common import default_output, release_dir
from system1.db.sqlite_builder import build_app_sqlite
from system1.indexes.builder import build_visual_index
from system1.release.phase_artifacts import (
    download_structure_artifacts_from_hf,
    upload_structure_artifacts_to_hf,
)
from system1.release.smoke import write_smoke_report
from system1.release.sync import (
    download_phase00_ingestion_from_hf,
    download_release_from_hf,
    upload_phase00_ingestion_to_hf,
    upload_release_to_hf,
)
from system1.release.writer import package_release
from system1.validation.release_validator import validate_release


def register(app: typer.Typer) -> None:
    @app.command("build-db")
    def build_db(
        output: Path = typer.Option(default_output(), "--output", "-o"),
    ) -> None:
        """Build app.sqlite for the generated release."""
        try:
            sqlite_path = build_app_sqlite(release_dir(output))
        except (FileNotFoundError, NotImplementedError, ValueError) as exc:
            raise typer.BadParameter(str(exc)) from exc
        typer.echo(f"Built app.sqlite: {sqlite_path}")

    @app.command("build-index")
    def build_index(
        output: Path = typer.Option(default_output(), "--output", "-o"),
    ) -> None:
        """Build the visual index for the generated release."""
        try:
            index_path = build_visual_index(release_dir(output))
        except (FileNotFoundError, NotImplementedError, ValueError) as exc:
            raise typer.BadParameter(str(exc)) from exc
        typer.echo(f"Built visual index: {index_path}")


    @app.command("validate")
    def validate(
        output: Path = typer.Option(default_output(), "--output", "-o"),
    ) -> None:
        """Validate the generated release."""
        result = validate_release(release_dir(output))
        if not result.passed:
            raise typer.Exit(1)
        typer.echo(f"Validation passed: {result.release_dir}")

    @app.command("smoke-test")
    def smoke_test(release: Path = typer.Option(..., "--release")) -> None:
        """Run a minimal System 2 compatibility smoke check against app.sqlite."""
        report_path = write_smoke_report(release)
        typer.echo(f"Smoke test report: {report_path}")

    @app.command("release")
    def release(
        output: Path = typer.Option(default_output(), "--output", "-o"),
    ) -> None:
        """Zip the generated release."""
        archive_path = package_release(release_dir(output))
        typer.echo(f"Packaged release: {archive_path}")

    @app.command("sync-release")
    def sync_release(
        output: Path = typer.Option(default_output(), "--output", "-o"),
        hf_repo_id: str = typer.Option(..., "--hf-repo-id"),
        hf_prefix: str = typer.Option("", "--hf-prefix"),
        hf_repo_type: str = typer.Option("dataset", "--hf-repo-type"),
        hf_revision: str = typer.Option("main", "--hf-revision"),
    ) -> None:
        """Upload the current release folder into a Hugging Face Dataset repo."""
        result = upload_release_to_hf(
            release_dir(output),
            repo_id=hf_repo_id,
            prefix=hf_prefix,
            repo_type=hf_repo_type,
            revision=hf_revision,
        )
        typer.echo(f"Synced release files={result.file_count}: {result.manifest_path}")

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

    @app.command("sync-structure-artifacts")
    def sync_structure_artifacts(
        output: Path = typer.Option(default_output(), "--output", "-o"),
        hf_repo_id: str = typer.Option(..., "--hf-repo-id"),
        release_id: str = typer.Option(..., "--release-id"),
        batch_id: str = typer.Option(..., "--batch-id"),
        worker_id: str = typer.Option(..., "--worker-id"),
        hf_prefix: str = typer.Option("", "--hf-prefix"),
        hf_repo_type: str = typer.Option("dataset", "--hf-repo-type"),
        hf_revision: str = typer.Option("main", "--hf-revision"),
    ) -> None:
        """Upload structure artifact ZIPs for one batch using the phase01_structure HF layout."""
        try:
            result = upload_structure_artifacts_to_hf(
                Path(output) / release_id,
                repo_id=hf_repo_id,
                release_id=release_id,
                batch_id=batch_id,
                worker_id=worker_id,
                prefix=hf_prefix,
                repo_type=hf_repo_type,
                revision=hf_revision,
            )
        except (FileNotFoundError, ValueError, zipfile.BadZipFile) as exc:
            raise typer.BadParameter(str(exc)) from exc
        typer.echo(f"Synced structure artifacts files={result.file_count}: {result.release_id}/{result.batch_id}")


    @app.command("restore-release")
    def restore_release(
        output: Path = typer.Option(default_output(), "--output", "-o"),
        release_id: str = typer.Option("competition_dataset_v001", "--release-id"),
        hf_repo_id: str = typer.Option(..., "--hf-repo-id"),
        hf_prefix: str = typer.Option("", "--hf-prefix"),
        hf_repo_type: str = typer.Option("dataset", "--hf-repo-type"),
        hf_revision: str = typer.Option("main", "--hf-revision"),
        overwrite: bool = typer.Option(True, "--overwrite/--no-overwrite"),
    ) -> None:
        """Restore a synced release folder from a Hugging Face Dataset repo."""
        result = download_release_from_hf(
            output,
            release_id=release_id,
            repo_id=hf_repo_id,
            prefix=hf_prefix,
            repo_type=hf_repo_type,
            revision=hf_revision,
            overwrite=overwrite,
        )
        typer.echo(f"Restored release files={result.file_count}: {result.release_dir}")

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

    @app.command("restore-structure-artifacts")
    def restore_structure_artifacts(
        output: Path = typer.Option(default_output(), "--output", "-o"),
        hf_repo_id: str = typer.Option(..., "--hf-repo-id"),
        release_id: str = typer.Option(..., "--release-id"),
        batch_id: str = typer.Option(..., "--batch-id"),
        hf_prefix: str = typer.Option("", "--hf-prefix"),
        hf_repo_type: str = typer.Option("dataset", "--hf-repo-type"),
        hf_revision: str = typer.Option("main", "--hf-revision"),
        overwrite: bool = typer.Option(True, "--overwrite/--no-overwrite"),
    ) -> None:
        """Restore structure artifact ZIPs for one batch from the phase01_structure HF layout."""
        try:
            result = download_structure_artifacts_from_hf(
                output,
                repo_id=hf_repo_id,
                release_id=release_id,
                batch_id=batch_id,
                prefix=hf_prefix,
                repo_type=hf_repo_type,
                revision=hf_revision,
                overwrite=overwrite,
            )
        except (FileNotFoundError, FileExistsError, ValueError) as exc:
            raise typer.BadParameter(str(exc)) from exc
        typer.echo(f"Restored structure artifacts files={result.file_count}: {result.release_dir}")
