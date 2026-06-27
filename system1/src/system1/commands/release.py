from __future__ import annotations

from pathlib import Path

import typer

from system1.commands.common import default_output, release_dir, require_supported_mode
from system1.db.sqlite_builder import build_app_sqlite
from system1.indexes.builder import build_visual_index
from system1.release.smoke import write_smoke_report
from system1.release.sync import download_release_from_hf, upload_release_to_hf
from system1.release.writer import package_release
from system1.validation.release_validator import validate_release


def register(app: typer.Typer) -> None:
    @app.command("build-db")
    def build_db(
        mode: str = typer.Option("debug_small_sample", "--mode"),
        output: Path = typer.Option(default_output(), "--output", "-o"),
    ) -> None:
        """Report app.sqlite path for the generated debug release."""
        require_supported_mode(mode)
        try:
            sqlite_path = build_app_sqlite(release_dir(output))
        except (FileNotFoundError, NotImplementedError, ValueError) as exc:
            raise typer.BadParameter(str(exc)) from exc
        typer.echo(f"Built app.sqlite: {sqlite_path}")

    @app.command("build-index")
    def build_index(
        mode: str = typer.Option("debug_small_sample", "--mode"),
        output: Path = typer.Option(default_output(), "--output", "-o"),
    ) -> None:
        """Report visual mock index path for the generated debug release."""
        require_supported_mode(mode)
        try:
            index_path = build_visual_index(release_dir(output))
        except (FileNotFoundError, NotImplementedError, ValueError) as exc:
            raise typer.BadParameter(str(exc)) from exc
        typer.echo(f"Built visual index: {index_path}")


    @app.command("validate")
    def validate(
        mode: str = typer.Option("debug_small_sample", "--mode"),
        output: Path = typer.Option(default_output(), "--output", "-o"),
    ) -> None:
        """Validate the debug release."""
        require_supported_mode(mode)
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
        mode: str = typer.Option("debug_small_sample", "--mode"),
        output: Path = typer.Option(default_output(), "--output", "-o"),
    ) -> None:
        """Zip the generated debug release."""
        require_supported_mode(mode)
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
