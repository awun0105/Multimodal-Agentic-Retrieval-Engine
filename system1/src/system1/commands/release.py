from __future__ import annotations

from pathlib import Path

import typer

from system1.commands.common import default_output, release_dir, require_supported_mode
from system1.db.sqlite_builder import build_app_sqlite
from system1.indexes.builder import build_visual_index
from system1.release.mini_seed import build_mini_seed
from system1.release.smoke import write_smoke_report
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

    @app.command("build-mini-seed")
    def build_mini_seed_command(
        mode: str = typer.Option("debug_small_sample", "--mode"),
        providers: str = typer.Option("mock", "--providers"),
        output: Path = typer.Option(default_output(), "--output", "-o"),
        input_dir: Path | None = typer.Option(None, "--input", "-i"),
    ) -> None:
        """Build the full dev/test mini release in one command."""
        require_supported_mode(mode)
        release_path = build_mini_seed(output, input_dir=input_dir, validate=True, mode=mode, providers=providers)
        typer.echo(f"Built mini seed release: {release_path}")

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
