from pathlib import Path

import typer

from system1.release.mini_seed import build_mini_seed

app = typer.Typer(help="System 1 data factory commands.")


@app.callback()
def root() -> None:
    """System 1 data factory commands."""


@app.command()
def hello() -> None:
    """Smoke command for checking the System 1 CLI."""
    typer.echo("System 1 CLI is ready.")


@app.command("build-mini-seed")
def build_mini_seed_command(
    output: Path = typer.Option(..., "--output", "-o", help="Directory where the seed release is written."),
) -> None:
    """Build the Phase 1 mini seed release."""
    release_dir = build_mini_seed(output)
    typer.echo(f"Built mini seed release: {release_dir}")


def main() -> None:
    app()
