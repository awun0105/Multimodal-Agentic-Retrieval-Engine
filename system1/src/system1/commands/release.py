from __future__ import annotations

from pathlib import Path

import typer

from system1.commands.common import default_output, release_dir, require_supported_mode
from system1.release.mini_seed import package_release, write_smoke_report
from system1.validation.release_validator import validate_release


def register(app: typer.Typer) -> None:
    @app.command("build-db")
    def build_db(
        mode: str = typer.Option("debug_small_sample", "--mode"),
        output: Path = typer.Option(default_output(), "--output", "-o"),
    ) -> None:
        """Report app.sqlite path for the generated debug release."""
        require_supported_mode(mode)
        sqlite_path = release_dir(output) / "db" / "app.sqlite"
        if not sqlite_path.exists():
            raise typer.BadParameter(f"missing app.sqlite; run system1 ingest first: {sqlite_path}")
        typer.echo(f"Built app.sqlite: {sqlite_path}")

    @app.command("build-index")
    def build_index(
        mode: str = typer.Option("debug_small_sample", "--mode"),
        output: Path = typer.Option(default_output(), "--output", "-o"),
    ) -> None:
        """Report visual mock index path for the generated debug release."""
        require_supported_mode(mode)
        index_path = release_dir(output) / "indexes" / "visual.faiss"
        if not index_path.exists():
            raise typer.BadParameter(f"missing visual.faiss; run system1 ingest first: {index_path}")
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
