from __future__ import annotations

from pathlib import Path

import typer

from system1.commands.common import (
    default_output,
    release_dir,
    require_supported_batch,
    require_supported_mode,
    require_supported_providers,
)
from system1.release.mini_seed import build_mini_seed, write_worker_artifacts


def register(app: typer.Typer) -> None:
    @app.command("ingest")
    def ingest(
        mode: str = typer.Option("debug_small_sample", "--mode"),
        output: Path = typer.Option(default_output(), "--output", "-o"),
        input_dir: Path | None = typer.Option(None, "--input", "-i"),
    ) -> None:
        """Normalize sample inputs into release tables."""
        require_supported_mode(mode)
        built_release_dir = build_mini_seed(output, input_dir=input_dir, validate=False, mode=mode)
        typer.echo(f"Ingested sample inputs: {built_release_dir}")

    @app.command("assign-batches")
    def assign_batches(
        mode: str = typer.Option("debug_small_sample", "--mode"),
        num_batches: int = typer.Option(1, "--num-batches"),
        output: Path = typer.Option(default_output(), "--output", "-o"),
        input_dir: Path | None = typer.Option(None, "--input", "-i"),
    ) -> None:
        """Create deterministic debug batch manifests."""
        require_supported_mode(mode)
        if num_batches != 1:
            raise typer.BadParameter("debug_small_sample currently supports exactly one batch")
        built_release_dir = build_mini_seed(output, input_dir=input_dir, validate=False, mode=mode)
        typer.echo(f"Assigned batch_000: {built_release_dir / 'manifests' / 'batch_000.txt'}")

    @app.command("process-batch")
    def process_batch(
        batch_id: str = typer.Option(..., "--batch-id"),
        mode: str = typer.Option("debug_small_sample", "--mode"),
        providers: str = typer.Option("mock", "--providers"),
        output: Path = typer.Option(default_output(), "--output", "-o"),
        input_dir: Path | None = typer.Option(None, "--input", "-i"),
    ) -> None:
        """Build mock ASR, shot, scene, keyframe, and thumbnail artifacts."""
        require_supported_mode(mode)
        require_supported_providers(providers)
        require_supported_batch(batch_id)
        built_release_dir = build_mini_seed(
            output, input_dir=input_dir, validate=False, mode=mode, providers=providers
        )
        report_path = write_worker_artifacts(built_release_dir, batch_id=batch_id, phase="structure")
        typer.echo(f"Processed {batch_id}: {built_release_dir} ({report_path})")

    @app.command("feature-batch")
    def feature_batch(
        batch_id: str = typer.Option(..., "--batch-id"),
        mode: str = typer.Option("debug_small_sample", "--mode"),
        providers: str = typer.Option("mock", "--providers"),
        output: Path = typer.Option(default_output(), "--output", "-o"),
        input_dir: Path | None = typer.Option(None, "--input", "-i"),
    ) -> None:
        """Build mock OCR, object, caption, and embedding artifacts."""
        require_supported_mode(mode)
        require_supported_providers(providers)
        require_supported_batch(batch_id)
        built_release_dir = build_mini_seed(
            output, input_dir=input_dir, validate=False, mode=mode, providers=providers
        )
        report_path = write_worker_artifacts(built_release_dir, batch_id=batch_id, phase="features")
        typer.echo(f"Featured {batch_id}: {built_release_dir} ({report_path})")

    @app.command("merge")
    def merge(
        mode: str = typer.Option("debug_small_sample", "--mode"),
        output: Path = typer.Option(default_output(), "--output", "-o"),
    ) -> None:
        """Merge structural and feature artifacts for debug release."""
        require_supported_mode(mode)
        typer.echo(f"Merged debug artifacts: {release_dir(output)}")
