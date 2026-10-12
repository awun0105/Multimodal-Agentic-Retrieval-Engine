from __future__ import annotations

import os
from pathlib import Path

import typer

from system1.batch.writer import assign_batches as run_assign_batches
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
    require_supported_providers,
    save_phase_checkpoint,
    try_restore_checkpoint,
)
from system1.features.builder import process_feature_batch
from system1.ingest.pipeline import run_ingestion
from system1.asr.runtime_artifact import prepare_flashlight_runtime
from system1.config.loader import load_configs
from system1.phase01 import (
    Phase01SmokeError,
    run_phase01_pipeline,
    run_phase01_smoke,
)
from system1.release.merge import merge_worker_outputs
from system1.release.types import config_dir
from system1.structure.builder import process_structure_batch


def register(app: typer.Typer) -> None:
    @app.command("phase01-prepare-asr-runtime")
    def phase01_prepare_asr_runtime(
        hf_model_artifact_repo: str | None = typer.Option(
            None, "--hf-model-artifact-repo"
        ),
        model_artifact_revision: str | None = typer.Option(
            None, "--model-artifact-revision"
        ),
        model_artifact_prefix: str | None = typer.Option(
            None, "--model-artifact-prefix"
        ),
        cache_dir: Path | None = typer.Option(None, "--cache-dir"),
    ) -> None:
        """Install the pinned Flashlight decoder wheel before workers start."""

        configs = load_configs(config_dir())
        asr = configs["models"]["phase01"]["asr"]
        decoder = asr["decoder"]
        storage = dict(configs["storage"]["model_artifacts"])
        for key, value in (
            ("repo_id", hf_model_artifact_repo),
            ("revision", model_artifact_revision),
            ("prefix", model_artifact_prefix),
        ):
            if value is not None:
                storage[key] = value
        try:
            receipt = prepare_flashlight_runtime(
                artifact_config=decoder["runtime_artifact"],
                storage_config=storage,
                cache_root=cache_dir,
                token=os.environ.get("HF_TOKEN") or os.environ.get("AIC_HF_TOKEN"),
            )
        except (FileNotFoundError, KeyError, RuntimeError, ValueError) as exc:
            raise typer.BadParameter(str(exc)) from exc
        typer.echo(f"Flashlight runtime ready: {receipt}")

    @app.command("phase01-smoke")
    def phase01_smoke(
        asr_provider: str | None = typer.Option(None, "--asr-provider"),
        hf_checkpoint_repo: str | None = typer.Option(None, "--hf-checkpoint-repo"),
        checkpoint_revision: str | None = typer.Option(None, "--checkpoint-revision"),
        checkpoint_prefix: str | None = typer.Option(None, "--checkpoint-prefix"),
        scratch_dir: Path | None = typer.Option(None, "--scratch-dir"),
        keep_remote_artifacts: bool | None = typer.Option(
            None,
            "--keep-remote-artifacts/--delete-remote-artifacts",
        ),
        cleanup_local: bool | None = typer.Option(
            None, "--cleanup-local/--keep-local"
        ),
        output: Path = typer.Option(default_output(), "--output", "-o"),
    ) -> None:
        """Run the optional one-video real-provider Phase01 smoke only."""

        user_settings = {
            "batch_id": "phase01_smoke",
            "worker_id": "phase01_smoke",
            "asr_provider": asr_provider,
            "hf_checkpoint_repo": hf_checkpoint_repo,
            "checkpoint_revision": checkpoint_revision,
            "checkpoint_prefix": checkpoint_prefix,
            "scratch_dir": str(scratch_dir) if scratch_dir else None,
        }
        user_settings = {
            key: value for key, value in user_settings.items() if value is not None
        }
        try:
            result = run_phase01_smoke(
                config_dir=config_dir(),
                output_root=output,
                user_settings=user_settings,
                keep_remote_artifacts=keep_remote_artifacts,
                cleanup_local=cleanup_local,
            )
        except Phase01SmokeError as exc:
            raise typer.BadParameter(str(exc)) from exc
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            raise typer.BadParameter(str(exc)) from exc
        typer.echo(f"Smoke PASS: {result.report_path}")

    @app.command("ingest")
    def ingest(
        output: Path = typer.Option(default_output(), "--output", "-o"),
        input_dir: Path | None = typer.Option(None, "--input", "-i"),
        source_uri: str | None = typer.Option(
            None,
            "--source-uri",
            help="Local standardized input root with raw_videos/ and metadata/.",
        ),
        max_workers: int | None = typer.Option(
            None,
            "--max-workers",
            min=1,
            help="Maximum parallel metadata/probe workers.",
        ),
        pairing_policy: str = typer.Option(
            "video-primary",
            "--pairing-policy",
            help="Local input pairing policy: strict or video-primary.",
        ),
        quarantine_unmatched_metadata: bool = typer.Option(
            False,
            "--quarantine-unmatched-metadata/--no-quarantine-unmatched-metadata",
            help="Move local metadata JSON files without matching videos into _unmatched_metadata/.",
        ),
        canonical_hf_repo_id: str | None = typer.Option(None, "--canonical-hf-repo-id"),
        canonical_hf_prefix: str = typer.Option("", "--canonical-hf-prefix"),
        canonical_hf_repo_type: str = typer.Option("dataset", "--canonical-hf-repo-type"),
        canonical_hf_revision: str = typer.Option("main", "--canonical-hf-revision"),
        canonical_staging_root: Path | None = typer.Option(None, "--canonical-staging-root"),
        frame_timeline_policy: str = typer.Option(
            "if-available",
            "--frame-timeline-policy",
            help="Decoded timeline policy: required, if-available, or disabled.",
        ),
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
        if source_uri is not None and canonical_hf_repo_id:
            raise typer.BadParameter(
                "pass only one source: --source-uri for local standardized input "
                "or --canonical-hf-repo-id for HF fallback"
            )
        if source_uri is not None and input_dir:
            raise typer.BadParameter("pass only one local input option: --source-uri or --input")
        normalized_pairing_policy = pairing_policy.strip().lower().replace("_", "-")
        if normalized_pairing_policy not in {"strict", "video-primary"}:
            raise typer.BadParameter("pairing policy must be strict or video-primary")
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
            source_uri=source_uri,
            max_workers=max_workers,
            pairing_policy=normalized_pairing_policy,
            quarantine_unmatched_metadata=quarantine_unmatched_metadata,
            canonical_hf_repo_id=canonical_hf_repo_id,
            canonical_hf_prefix=canonical_hf_prefix,
            canonical_hf_repo_type=canonical_hf_repo_type,
            canonical_hf_revision=canonical_hf_revision,
            canonical_staging_root=canonical_staging_root,
            frame_timeline_policy=frame_timeline_policy,
        )
        typer.echo(f"Ingested sample inputs: {report_path}")

    @app.command("assign-batches")
    def assign_batches(
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
        """Create deterministic batch manifests."""
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
        asr_provider: str | None = typer.Option(
            None,
            "--asr-provider",
            help="Optional Phase01 ASR provider override from models.yaml.",
        ),
        release_id_override: str | None = typer.Option(None, "--release-id-override"),
        hf_checkpoint_repo: str | None = typer.Option(None, "--hf-checkpoint-repo"),
        checkpoint_revision: str | None = typer.Option(None, "--checkpoint-revision"),
        checkpoint_prefix: str | None = typer.Option(None, "--checkpoint-prefix"),
        scratch_dir: Path | None = typer.Option(None, "--scratch-dir"),
        restore_phase00: bool = typer.Option(
            True, "--restore-phase00/--no-restore-phase00"
        ),
        validate_remote: bool = typer.Option(
            True, "--validate-remote/--no-validate-remote"
        ),
        require_frame_timeline: bool = typer.Option(
            True,
            "--require-frame-timeline/--allow-missing-frame-timeline",
            help="Fail the batch if any video lacks a usable decoded frame timeline.",
        ),
        output: Path = typer.Option(default_output(), "--output", "-o"),
        input_dir: Path | None = typer.Option(None, "--input", "-i"),
        artifact_backend: str = typer.Option(default_artifact_backend(), "--artifact-backend"),
        artifact_root: Path = typer.Option(default_artifact_root(), "--artifact-root"),
        hf_repo_id: str | None = typer.Option(None, "--hf-repo-id"),
        hf_repo_type: str | None = typer.Option(None, "--hf-repo-type"),
        hf_revision: str | None = typer.Option(None, "--hf-revision"),
        hf_prefix: str | None = typer.Option(None, "--hf-prefix"),
        resume: bool = typer.Option(default_cli_resume(), "--resume/--no-resume"),
        sync: bool = typer.Option(True, "--sync/--no-sync"),
    ) -> None:
        """Build phase01 structure artifacts for one assigned batch."""
        provider_profile = _phase01_test_provider_profile()
        if provider_profile == "config":
            if input_dir is not None:
                raise typer.BadParameter(
                    "Production Phase01 reads canonical media from Phase00; --input is test-only"
                )
            if not require_frame_timeline:
                raise typer.BadParameter("Production Phase01 requires the decoded frame timeline")
            user_settings = {
                "batch_id": batch_id,
                "worker_id": worker_id,
                "asr_provider": asr_provider,
                "release_id_override": release_id_override,
                "hf_release_repo": hf_repo_id,
                "hf_repo_type": hf_repo_type,
                "hf_release_revision": hf_revision,
                "hf_release_prefix": hf_prefix,
                "hf_checkpoint_repo": hf_checkpoint_repo,
                "checkpoint_revision": checkpoint_revision,
                "checkpoint_prefix": checkpoint_prefix,
                "scratch_dir": str(scratch_dir) if scratch_dir else None,
            }
            user_settings = {
                key: value for key, value in user_settings.items() if value is not None
            }
            try:
                result = run_phase01_pipeline(
                    config_dir=config_dir(),
                    output_root=output,
                    user_settings=user_settings,
                    restore_phase00=restore_phase00,
                    sync_release=sync,
                    validate_remote=validate_remote,
                )
            except (FileNotFoundError, RuntimeError, ValueError) as exc:
                raise typer.BadParameter(str(exc)) from exc
            typer.echo(
                f"Processed {batch_id}: {result.release_dir} "
                f"({result.worker_report_path})"
            )
            return
        legacy_hf_repo_type = hf_repo_type or default_hf_repo_type()
        legacy_hf_revision = hf_revision or default_hf_revision()
        legacy_hf_prefix = hf_prefix if hf_prefix is not None else default_hf_prefix()
        legacy_hf_repo_id = hf_repo_id or default_hf_repo_id()
        if resume:
            try:
                if try_restore_checkpoint(
                    output=output,
                    artifact_root=artifact_root,
                    artifact_backend=artifact_backend,
                    hf_repo_id=legacy_hf_repo_id,
                    hf_repo_type=legacy_hf_repo_type,
                    hf_revision=legacy_hf_revision,
                    hf_prefix=legacy_hf_prefix,
                    phase="phase01_structure",
                    batch_id=batch_id,
                ):
                    typer.echo("Restored phase01 checkpoint; skipping process-batch.")
                    return
            except EXPECTED_CHECKPOINT_ERRORS as exc:
                checkpoint_error(exc)
        require_supported_batch(batch_id, output)
        report_path = process_structure_batch(
            output,
            input_dir=input_dir,
            batch_id=batch_id,
            worker_id=worker_id,
            providers=provider_profile,
            require_frame_timeline=require_frame_timeline,
        )
        typer.echo(f"Processed {batch_id}: {release_dir(output)} ({report_path})")
        if sync:
            try:
                save_phase_checkpoint(
                    release=release_dir(output),
                    artifact_root=artifact_root,
                    artifact_backend=artifact_backend,
                    hf_repo_id=legacy_hf_repo_id,
                    hf_repo_type=legacy_hf_repo_type,
                    hf_revision=legacy_hf_revision,
                    hf_prefix=legacy_hf_prefix,
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
            output,
            input_dir=input_dir,
            batch_id=batch_id,
            worker_id=worker_id,
            providers=providers,
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
        output: Path = typer.Option(default_output(), "--output", "-o"),
    ) -> None:
        """Merge structural and feature artifacts for the release."""
        # Phase03 checkpoint remains manual via checkpoint-save after final release artifacts exist.
        report_path = merge_worker_outputs(release_dir(output))
        typer.echo(f"Merged artifacts: {report_path}")


def _phase01_test_provider_profile() -> str:
    """Return a test-only provider injection without exposing a CLI selector."""

    profile = os.environ.get("AIC_SYSTEM1_TEST_PROVIDER_PROFILE", "").strip()
    if not profile:
        return "config"
    if os.environ.get("AIC_ALLOW_TEST_PROVIDERS") != "1":
        raise typer.BadParameter(
            "AIC_SYSTEM1_TEST_PROVIDER_PROFILE is test-only and requires "
            "AIC_ALLOW_TEST_PROVIDERS=1"
        )
    require_supported_providers(profile)
    return profile
