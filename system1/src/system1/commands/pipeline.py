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
from system1.batch.writer import assign_batches as run_assign_batches
from system1.features.builder import process_feature_batch
from system1.ingest.pipeline import run_ingestion
from system1.release.merge import merge_worker_outputs
from system1.structure.builder import process_structure_batch


def register(app: typer.Typer) -> None:
    @app.command("ingest")
    def ingest(
        mode: str = typer.Option("debug_small_sample", "--mode"),
        output: Path = typer.Option(default_output(), "--output", "-o"),
        input_dir: Path | None = typer.Option(None, "--input", "-i"),
    ) -> None:
        """Normalize sample inputs into release tables."""
        require_supported_mode(mode)
        report_path = run_ingestion(output, input_dir=input_dir, mode=mode)
        typer.echo(f"Ingested sample inputs: {report_path}")

    @app.command("assign-batches")
    def assign_batches(
        mode: str = typer.Option("debug_small_sample", "--mode"),
        num_batches: int = typer.Option(1, "--num-batches"),
        output: Path = typer.Option(default_output(), "--output", "-o"),
    ) -> None:
        """Create deterministic debug batch manifests."""
        require_supported_mode(mode)
        try:
            batch_path = run_assign_batches(output, num_batches=num_batches)
        except (FileNotFoundError, ValueError) as exc:
            raise typer.BadParameter(str(exc)) from exc
        typer.echo(f"Assigned batches: {batch_path.parent}")

    @app.command("process-batch")
    def process_batch(
        batch_id: str = typer.Option(..., "--batch-id"),
        worker_id: str = typer.Option("worker_000", "--worker-id"),
        mode: str = typer.Option("debug_small_sample", "--mode"),
        providers: str = typer.Option("mock", "--providers"),
        output: Path = typer.Option(default_output(), "--output", "-o"),
        input_dir: Path | None = typer.Option(None, "--input", "-i"),
    ) -> None:
        """Build mock ASR, shot, scene, keyframe, and thumbnail artifacts."""
        require_supported_mode(mode)
        require_supported_providers(providers)
        require_supported_batch(batch_id, output)
        report_path = process_structure_batch(
            output, input_dir=input_dir, batch_id=batch_id, worker_id=worker_id, mode=mode, providers=providers
        )
        typer.echo(f"Processed {batch_id}: {release_dir(output)} ({report_path})")

    @app.command("feature-batch")
    def feature_batch(
        batch_id: str = typer.Option(..., "--batch-id"),
        worker_id: str = typer.Option("worker_000", "--worker-id"),
        mode: str = typer.Option("debug_small_sample", "--mode"),
        providers: str = typer.Option("mock", "--providers"),
        output: Path = typer.Option(default_output(), "--output", "-o"),
        input_dir: Path | None = typer.Option(None, "--input", "-i"),
    ) -> None:
        """Build mock OCR, object, caption, and embedding artifacts."""
        require_supported_mode(mode)
        require_supported_providers(providers)
        require_supported_batch(batch_id, output)
        report_path = process_feature_batch(
            output, input_dir=input_dir, batch_id=batch_id, worker_id=worker_id, mode=mode, providers=providers
        )
        typer.echo(f"Featured {batch_id}: {release_dir(output)} ({report_path})")

    @app.command("merge")
    def merge(
        mode: str = typer.Option("debug_small_sample", "--mode"),
        output: Path = typer.Option(default_output(), "--output", "-o"),
    ) -> None:
        """Merge structural and feature artifacts for debug release."""
        require_supported_mode(mode)
        report_path = merge_worker_outputs(release_dir(output))
        typer.echo(f"Merged debug artifacts: {report_path}")
