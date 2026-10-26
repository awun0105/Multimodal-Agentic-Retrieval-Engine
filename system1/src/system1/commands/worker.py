"""CLI for the simplified pipeline: `worker-batch`, `caption-batch`, and `build-release`."""

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
        work_root: Path = typer.Option(Path("worker_runtime"), "--work-root"),
    ) -> None:
        """Run one Phase00 batch through the worker and upload one package per video."""

        from system1.worker.batch import BatchPaths, run_batch
        from system1.worker.models import load_worker_models

        config = _worker_config()
        storage = config["storage"]
        models = load_worker_models(config, work_root)
        report = run_batch(
            BatchPaths(release_id=release_id, batch_id=batch_id, worker_id=worker_id),
            config=config, models=models,
            raw_store=_store(storage["raw_repo"], storage, work_root / "job" / ".hf_cache"),
            source_store=_store(storage["source_repo"], storage, work_root / "job" / ".hf_cache"),
            output_store=_store(output_repo or storage["output_repo"], storage, work_root / "job" / ".hf_cache"),
            work_root=work_root / "job", limit=limit,
        )
        typer.echo(json.dumps({key: report[key] for key in ("completed", "skipped", "failed")}, ensure_ascii=False))

    @app.command("caption-batch")
    def caption_batch(
        batch_id: str = typer.Option(..., "--batch-id"),
        worker_id: str = typer.Option("worker_000", "--worker-id"),
        release_id: str = typer.Option(DEFAULT_RELEASE_ID, "--release-id"),
        source_repo: str | None = typer.Option(None, "--source-repo",
                                               help="Repo holding worker packages; defaults to storage.output_repo."),
        output_repo: str | None = typer.Option(None, "--output-repo",
                                               help="Defaults to storage.output_repo (the test repo)."),
        limit: int | None = typer.Option(None, "--limit", help="Caption only the first N videos."),
        work_root: Path = typer.Option(Path("caption_runtime"), "--work-root"),
        persist_dir: Path | None = typer.Option(None, "--persist-dir",
                                                help="Also write report.json here after every video."),
    ) -> None:
        """Caption every worker package of one batch and upload one caption package per video."""

        from system1.captions.batch import CaptionPaths, run_caption_batch
        from system1.captions.models import load_caption_models

        config = _worker_config()
        storage = config["storage"]
        captioner, text_embedder = load_caption_models(config)
        cache = work_root / "job" / ".hf_cache"
        report = run_caption_batch(
            CaptionPaths(release_id=release_id, batch_id=batch_id, worker_id=worker_id),
            config=config, captioner=captioner, text_embedder=text_embedder,
            worker_store=_store(source_repo or storage["output_repo"], storage, cache),
            output_store=_store(output_repo or storage["output_repo"], storage, cache),
            work_root=work_root / "job", limit=limit, persist_dir=persist_dir,
        )
        typer.echo(json.dumps({key: report[key] for key in ("completed", "skipped", "failed")}, ensure_ascii=False))

    @app.command("build-release")
    def build_release_command(
        release_id: str = typer.Option(DEFAULT_RELEASE_ID, "--release-id"),
        source_repo: str | None = typer.Option(None, "--source-repo",
                                               help="Repo holding worker and caption packages; "
                                                    "defaults to storage.output_repo."),
        out_dir: Path = typer.Option(Path("release_build"), "--out-dir"),
        bucket_id: str | None = typer.Option(None, "--bucket-id", help="Defaults to storage.bucket_id."),
        bucket_prefix: str | None = typer.Option(None, "--bucket-prefix",
                                                 help="Defaults to storage.bucket_prefix (the test prefix)."),
        publish: bool = typer.Option(False, "--publish/--no-publish",
                                     help="Upload media per video and the release to the bucket."),
        persist_dir: Path | None = typer.Option(None, "--persist-dir",
                                                help="Write build_report.json here after every video."),
    ) -> None:
        """Stream every package of a release into the runtime release, one video at a time."""

        import shutil

        import pandas as pd

        from system1.release.build import build_release
        from system1.release.publish import BucketClient, media_sink_for, publish_release
        from system1.scenes.release_builder import make_scene_builder

        config = _worker_config()
        storage = config["storage"]
        cache = out_dir / ".hf_cache"
        downloads = out_dir / "downloads"
        store = _store(source_repo or storage["output_repo"], storage, cache)
        phase00_store = _store(storage["source_repo"], storage, cache)

        def fetch(source_store, remote: str, target: Path) -> Path:
            path = source_store.download_file(remote, target)
            shutil.rmtree(cache, ignore_errors=True)  # keep one copy on disk
            return path

        worker_prefix = f"{release_id}/worker/artifacts"
        worker_remotes = sorted(path for path in store.list_files(worker_prefix) if path.suffix == ".zip")
        if not worker_remotes:
            raise typer.BadParameter(f"no worker packages under {worker_prefix}")
        caption_remotes = {path.stem: path for path in store.list_files(f"{release_id}/captions/artifacts")
                           if path.suffix == ".zip"}

        def worker_zips():
            for remote in worker_remotes:
                local = fetch(store, str(remote), downloads / "worker" / remote.name)
                try:
                    yield local
                finally:
                    local.unlink(missing_ok=True)

        def caption_zip(video_id: str) -> Path | None:
            shutil.rmtree(downloads / "captions", ignore_errors=True)
            remote = caption_remotes.get(video_id)
            return None if remote is None else fetch(store, str(remote), downloads / "captions" / remote.name)

        videos_path = fetch(phase00_store, f"{release_id}/phase00_ingestion/tables/videos.parquet",
                            downloads / "videos.parquet")
        phase00_videos = pd.read_parquet(videos_path)
        # `organizer_metadata_present` lives in the raw mapping, not in the videos table.
        mapping_path = fetch(phase00_store, f"{release_id}/phase00_ingestion/raw_mapping/media_store_manifest.parquet",
                             downloads / "media_store_manifest.parquet")
        mapping = pd.read_parquet(mapping_path)[["video_id", "organizer_metadata_present"]]
        phase00_videos = phase00_videos.drop(columns=["organizer_metadata_present"], errors="ignore").merge(
            mapping, on="video_id", how="left")

        prefix = f"{(bucket_prefix or storage['bucket_prefix']).strip('/')}/{release_id}"
        client = None
        if publish:
            client = BucketClient(bucket_id or storage["bucket_id"],
                                  token=os.environ.get("AIC_HF_TOKEN") or os.environ.get("HF_TOKEN"))
        report: dict = {"release_id": release_id, "videos_total": len(worker_remotes),
                        "captions_available": len(caption_remotes), "videos": []}

        def progress(item) -> None:
            report["videos"].append(dict(item))
            if persist_dir is not None:
                persist_dir.mkdir(parents=True, exist_ok=True)
                (persist_dir / "build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                                              encoding="utf-8")

        release = build_release(
            release_id=release_id, worker_zips=worker_zips, caption_zips_by_video=caption_zip,
            phase00_videos=phase00_videos, out_dir=out_dir,
            media_sink=media_sink_for(client, prefix) if client is not None else None,
            scene_builder=make_scene_builder(config["scenes"]), progress=progress,
        )
        shutil.rmtree(downloads, ignore_errors=True)
        typer.echo(f"Built {release} from {len(worker_remotes)} packages")
        if client is not None:
            ready = publish_release(release, bucket_id=client.bucket_id, prefix=prefix, client=client)
            typer.echo(f"Published {prefix} to {client.bucket_id}: {json.dumps(ready)}")


def _worker_config() -> dict:
    path = resolve_runtime_environment().config_root / "worker.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _store(repo_id: str, storage: dict, cache_dir: Path):
    from system1.artifacts.hf_store import HuggingFaceDatasetArtifactStore

    return HuggingFaceDatasetArtifactStore(
        repo_id=repo_id, repo_type=storage["repo_type"],
        token=os.environ.get("AIC_HF_TOKEN") or os.environ.get("HF_TOKEN"), cache_dir=cache_dir,
    )
