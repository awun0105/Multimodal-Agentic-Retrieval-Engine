from __future__ import annotations

import os

import typer

if os.environ.get("AIC_HF_PROGRESS", "0") != "1":
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("HF_HUB_VERBOSITY", "error")

from system1.commands import (
    register_checkpoint_commands,
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
register_checkpoint_commands(app)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
