"""CLI for the simplified pipeline: `worker-batch` and `build-release`."""

from __future__ import annotations

import json
import os
from pathlib import Path

import typer
import yaml

from system1.runtime.environment import resolve_runtime_environment

DEFAULT_RELEASE_ID = "canonical_release_v001"


def register(app: typer.Typer) -> None:
    @app.command("worker-batch")
    def worker_batch(
        batch_id: str = typer.Option(..., "--batch-id"),
        worker_id: str = typer.Option("worker_000", "--worker-id"),
        release_id: str = typer.Option(DEFAULT_RELEASE_ID, "--release-id"),
        output_repo: str | None = typer.Option(None, "--output-repo",
                                               help="Defaults to storage.output_repo (the test repo)."),
        limit: int | None = typer.Option(None, "--limit", help="Process only the first N videos."),
        captions: bool = typer.Option(True, "--captions/--no-captions"),
        work_root: Path = typer.Option(Path("worker_runtime"), "--work-root"),
    ) -> None:
        """Run one Phase00 batch through the worker and upload one package per video."""

        from system1.worker.batch import BatchPaths, run_batch
        from system1.worker.models import load_worker_models

        config = _worker_config()
        storage = config["storage"]
        models = load_worker_models(config, work_root, captions=captions)
        report = run_batch(
            BatchPaths(release_id=release_id, batch_id=batch_id, worker_id=worker_id),
            config=config, models=models,
            raw_store=_store(storage["raw_repo"], storage, work_root / "job" / ".hf_cache"),
            source_store=_store(storage["source_repo"], storage, work_root / "job" / ".hf_cache"),
            output_store=_store(output_repo or storage["output_repo"], storage, work_root / "job" / ".hf_cache"),
            work_root=work_root / "job", limit=limit,
        )
        typer.echo(json.dumps({key: report[key] for key in ("completed", "skipped", "failed")}, ensure_ascii=False))

    @app.command("build-release")
    def build_release_command(
        release_id: str = typer.Option(DEFAULT_RELEASE_ID, "--release-id"),
        source_repo: str | None = typer.Option(None, "--source-repo",
                                               help="Repo holding worker packages; defaults to storage.output_repo."),
        out_dir: Path = typer.Option(Path("release_build"), "--out-dir"),
    ) -> None:
        """Download every worker package of a release and build the runtime release locally."""

        from system1.release.build import build_release

        config = _worker_config()
        storage = config["storage"]
        store = _store(source_repo or storage["output_repo"], storage, out_dir / ".hf_cache")
        prefix = f"{release_id}/worker/artifacts"
        zips = []
        for remote in sorted(store.list_files(prefix)):
            if remote.suffix == ".zip":
                zips.append(store.download_file(str(remote), out_dir / "packages" / remote.name))
        if not zips:
            raise typer.BadParameter(f"no worker packages under {prefix}")
        release = build_release(zips, out_dir / "release", release_id=release_id)
        typer.echo(f"Built {release} from {len(zips)} packages")


def _worker_config() -> dict:
    path = resolve_runtime_environment().config_root / "worker.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _store(repo_id: str, storage: dict, cache_dir: Path):
    from system1.artifacts.hf_store import HuggingFaceDatasetArtifactStore

    return HuggingFaceDatasetArtifactStore(
        repo_id=repo_id, repo_type=storage["repo_type"],
        token=os.environ.get("AIC_HF_TOKEN") or os.environ.get("HF_TOKEN"), cache_dir=cache_dir,
    )
