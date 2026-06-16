from __future__ import annotations

import typer

from system1.commands import (
    register_import_commands,
    register_pipeline_commands,
    register_release_commands,
)

app = typer.Typer(help="System 1 data factory commands.")


@app.callback()
def root() -> None:
    """System 1 data factory commands."""


register_import_commands(app)
register_pipeline_commands(app)
register_release_commands(app)


def main() -> None:
    app()
