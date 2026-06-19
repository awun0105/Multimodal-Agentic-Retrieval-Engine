from __future__ import annotations

from pathlib import Path

import typer

from system1.commands.common import (
    EXPECTED_CHECKPOINT_ERRORS,
    checkpoint_error,
    default_artifact_backend,
    default_artifact_root,
    default_cli_resume,
    default_cli_sync,
    default_hf_prefix,
    default_hf_repo_id,
    default_hf_repo_type,
    default_hf_revision,
    default_output,
    release_dir,
    require_supported_batch,
    require_supported_mode,
    require_supported_providers,
    save_phase_checkpoint,
    try_restore_checkpoint,
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
        canonical_hf_repo_id: str | None = typer.Option(None, "--canonical-hf-repo-id"),
        canonical_hf_prefix: str = typer.Option("", "--canonical-hf-prefix"),
        canonical_hf_repo_type: str = typer.Option("dataset", "--canonical-hf-repo-type"),
        canonical_hf_revision: str = typer.Option("main", "--canonical-hf-revision"),
        canonical_staging_root: Path | None = typer.Option(None, "--canonical-staging-root"),
        artifact_backend: str = typer.Option(default_artifact_backend(), "--artifact-backend"),
        artifact_root: Path = typer.Option(default_artifact_root(), "--artifact-root"),
        hf_repo_id: str | None = typer.Option(default_hf_repo_id(), "--hf-repo-id"),
        hf_repo_type: str = typer.Option(default_hf_repo_type(), "--hf-repo-type"),
        hf_revision: str = typer.Option(default_hf_revision(), "--hf-revision"),
        hf_prefix: str = typer.Option(default_hf_prefix(), "--hf-prefix"),
        resume: bool = typer.Option(default_cli_resume(), "--resume/--no-resume"),
        sync: bool = typer.Option(default_cli_sync(), "--sync/--no-sync"),
    ) -> None:
        """Normalize sample inputs into release tables."""
        require_supported_mode(mode)
        if resume:
            try:
                if try_restore_checkpoint(output=output, artifact_root=artifact_root, artifact_backend=artifact_backend, hf_repo_id=hf_repo_id, hf_repo_type=hf_repo_type, hf_revision=hf_revision, hf_prefix=hf_prefix, phase="phase00_ingest_assignment"):
                    typer.echo("Restored phase00 checkpoint; skipping ingest.")
                    return
            except EXPECTED_CHECKPOINT_ERRORS as exc:
                checkpoint_error(exc)
        report_path = run_ingestion(
            output,
            input_dir=input_dir,
            mode=mode,
            canonical_hf_repo_id=canonical_hf_repo_id,
            canonical_hf_prefix=canonical_hf_prefix,
            canonical_hf_repo_type=canonical_hf_repo_type,
            canonical_hf_revision=canonical_hf_revision,
            canonical_staging_root=canonical_staging_root,
        )
        typer.echo(f"Ingested sample inputs: {report_path}")

    @app.command("assign-batches")
    def assign_batches(
        mode: str = typer.Option("debug_small_sample", "--mode"),
        num_batches: int = typer.Option(1, "--num-batches"),
        output: Path = typer.Option(default_output(), "--output", "-o"),
        artifact_backend: str = typer.Option(default_artifact_backend(), "--artifact-backend"),
        artifact_root: Path = typer.Option(default_artifact_root(), "--artifact-root"),
        hf_repo_id: str | None = typer.Option(default_hf_repo_id(), "--hf-repo-id"),
        hf_repo_type: str = typer.Option(default_hf_repo_type(), "--hf-repo-type"),
        hf_revision: str = typer.Option(default_hf_revision(), "--hf-revision"),
        hf_prefix: str = typer.Option(default_hf_prefix(), "--hf-prefix"),
        resume: bool = typer.Option(default_cli_resume(), "--resume/--no-resume"),
        sync: bool = typer.Option(default_cli_sync(), "--sync/--no-sync"),
    ) -> None:
        """Create deterministic debug batch manifests."""
        require_supported_mode(mode)
        try:
            batch_path = run_assign_batches(output, num_batches=num_batches)
        except (FileNotFoundError, ValueError) as exc:
            raise typer.BadParameter(str(exc)) from exc
        typer.echo(f"Assigned batches: {batch_path.parent}")
        if sync:
            try:
                save_phase_checkpoint(
                    release=release_dir(output),
                    artifact_root=artifact_root,
                    artifact_backend=artifact_backend,
                    hf_repo_id=hf_repo_id,
                    hf_repo_type=hf_repo_type,
                    hf_revision=hf_revision,
                    hf_prefix=hf_prefix,
                    phase="phase00_ingest_assignment",
                )
            except EXPECTED_CHECKPOINT_ERRORS as exc:
                checkpoint_error(exc)

    @app.command("process-batch")
    def process_batch(
        batch_id: str = typer.Option(..., "--batch-id"),
        worker_id: str = typer.Option("worker_000", "--worker-id"),
        mode: str = typer.Option("debug_small_sample", "--mode"),
        providers: str = typer.Option("mock", "--providers"),
        output: Path = typer.Option(default_output(), "--output", "-o"),
        input_dir: Path | None = typer.Option(None, "--input", "-i"),
        artifact_backend: str = typer.Option(default_artifact_backend(), "--artifact-backend"),
        artifact_root: Path = typer.Option(default_artifact_root(), "--artifact-root"),
        hf_repo_id: str | None = typer.Option(default_hf_repo_id(), "--hf-repo-id"),
        hf_repo_type: str = typer.Option(default_hf_repo_type(), "--hf-repo-type"),
        hf_revision: str = typer.Option(default_hf_revision(), "--hf-revision"),
        hf_prefix: str = typer.Option(default_hf_prefix(), "--hf-prefix"),
        resume: bool = typer.Option(default_cli_resume(), "--resume/--no-resume"),
        sync: bool = typer.Option(default_cli_sync(), "--sync/--no-sync"),
    ) -> None:
        """Build mock ASR, shot, scene, keyframe, and thumbnail artifacts."""
        require_supported_mode(mode)
        require_supported_providers(providers)
        if resume:
            try:
                if try_restore_checkpoint(
                    output=output,
                    artifact_root=artifact_root,
                    artifact_backend=artifact_backend,
                    hf_repo_id=hf_repo_id,
                    hf_repo_type=hf_repo_type,
                    hf_revision=hf_revision,
                    hf_prefix=hf_prefix,
                    phase="phase01_structure",
                    batch_id=batch_id,
                ):
                    typer.echo("Restored phase01 checkpoint; skipping process-batch.")
                    return
            except EXPECTED_CHECKPOINT_ERRORS as exc:
                checkpoint_error(exc)
        require_supported_batch(batch_id, output)
        report_path = process_structure_batch(
            output, input_dir=input_dir, batch_id=batch_id, worker_id=worker_id, mode=mode, providers=providers
        )
        typer.echo(f"Processed {batch_id}: {release_dir(output)} ({report_path})")
        if sync:
            try:
                save_phase_checkpoint(
                    release=release_dir(output),
                    artifact_root=artifact_root,
                    artifact_backend=artifact_backend,
                    hf_repo_id=hf_repo_id,
                    hf_repo_type=hf_repo_type,
                    hf_revision=hf_revision,
                    hf_prefix=hf_prefix,
                    phase="phase01_structure",
                    batch_id=batch_id,
                    worker_id=worker_id,
                )
            except EXPECTED_CHECKPOINT_ERRORS as exc:
                checkpoint_error(exc)

    @app.command("feature-batch")
    def feature_batch(
        batch_id: str = typer.Option(..., "--batch-id"),
        worker_id: str = typer.Option("worker_000", "--worker-id"),
        mode: str = typer.Option("debug_small_sample", "--mode"),
        providers: str = typer.Option("mock", "--providers"),
        output: Path = typer.Option(default_output(), "--output", "-o"),
        input_dir: Path | None = typer.Option(None, "--input", "-i"),
        artifact_backend: str = typer.Option(default_artifact_backend(), "--artifact-backend"),
        artifact_root: Path = typer.Option(default_artifact_root(), "--artifact-root"),
        hf_repo_id: str | None = typer.Option(default_hf_repo_id(), "--hf-repo-id"),
        hf_repo_type: str = typer.Option(default_hf_repo_type(), "--hf-repo-type"),
        hf_revision: str = typer.Option(default_hf_revision(), "--hf-revision"),
        hf_prefix: str = typer.Option(default_hf_prefix(), "--hf-prefix"),
        resume: bool = typer.Option(default_cli_resume(), "--resume/--no-resume"),
        sync: bool = typer.Option(default_cli_sync(), "--sync/--no-sync"),
    ) -> None:
        """Build mock OCR, object, caption, and embedding artifacts."""
        require_supported_mode(mode)
        require_supported_providers(providers)
        if resume:
            try:
                if try_restore_checkpoint(
                    output=output,
                    artifact_root=artifact_root,
                    artifact_backend=artifact_backend,
                    hf_repo_id=hf_repo_id,
                    hf_repo_type=hf_repo_type,
                    hf_revision=hf_revision,
                    hf_prefix=hf_prefix,
                    phase="phase02_features",
                    batch_id=batch_id,
                ):
                    typer.echo("Restored phase02 checkpoint; skipping feature-batch.")
                    return
            except EXPECTED_CHECKPOINT_ERRORS as exc:
                checkpoint_error(exc)
        require_supported_batch(batch_id, output)
        report_path = process_feature_batch(
            output, input_dir=input_dir, batch_id=batch_id, worker_id=worker_id, mode=mode, providers=providers
        )
        typer.echo(f"Featured {batch_id}: {release_dir(output)} ({report_path})")
        if sync:
            try:
                save_phase_checkpoint(
                    release=release_dir(output),
                    artifact_root=artifact_root,
                    artifact_backend=artifact_backend,
                    hf_repo_id=hf_repo_id,
                    hf_repo_type=hf_repo_type,
                    hf_revision=hf_revision,
                    hf_prefix=hf_prefix,
                    phase="phase02_features",
                    batch_id=batch_id,
                    worker_id=worker_id,
                )
            except EXPECTED_CHECKPOINT_ERRORS as exc:
                checkpoint_error(exc)

    @app.command("merge")
    def merge(
        mode: str = typer.Option("debug_small_sample", "--mode"),
        output: Path = typer.Option(default_output(), "--output", "-o"),
    ) -> None:
        """Merge structural and feature artifacts for debug release."""
        require_supported_mode(mode)
        # Phase03 checkpoint remains manual via checkpoint-save after final release artifacts exist.
        report_path = merge_worker_outputs(release_dir(output))
        typer.echo(f"Merged debug artifacts: {report_path}")
