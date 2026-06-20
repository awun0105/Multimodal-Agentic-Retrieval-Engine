from __future__ import annotations

from pathlib import Path

import typer

from system1.ingest.source_importer import (
    import_organizer_source,
    shadow_google_drive_folder,
    standardize_archive_source,
    upload_standardized_raw_to_hf,
)


def register(app: typer.Typer) -> None:
    @app.command("import-source")
    def import_source(
        source_uri: str = typer.Option(
            ..., "--source-uri", help="Organizer source folder path or Google Drive folder URL."
        ),
        data_root: Path = typer.Option(
            Path("input"), "--data-root", help="Target data root with raw_videos/ and metadata/."
        ),
    ) -> None:
        """Import an organizer source into raw_videos/ and metadata/."""
        result = import_organizer_source(source_uri, data_root)
        typer.echo(
            f"Imported source videos={result.video_count} metadata={result.metadata_count}: {result.report_path}"
        )

    @app.command("upload-standardized-raw")
    def upload_standardized_raw(
        source_dir: Path = typer.Option(
            ..., "--source-dir", help="Standardized local folder containing raw_videos/ and metadata/."
        ),
        target_hf_repo_id: str = typer.Option(..., "--target-hf-repo-id", help="Existing Hugging Face Dataset repo for canonical data."),
        raw_import_id: str = typer.Option(..., "--raw-import-id", help="Version prefix inside the raw HF Dataset repo."),
        target_hf_repo_type: str = typer.Option("dataset", "--target-hf-repo-type"),
        target_hf_revision: str = typer.Option("main", "--target-hf-revision"),
    ) -> None:
        """Upload standardized raw videos and metadata into a versioned HF Dataset prefix."""
        result = upload_standardized_raw_to_hf(
            source_dir,
            repo_id=target_hf_repo_id,
            raw_import_id=raw_import_id,
            repo_type=target_hf_repo_type,
            revision=target_hf_revision,
            progress_path=None,
        )
        typer.echo(
            "Uploaded standardized raw "
            f"videos={result.video_count} metadata={result.metadata_count} "
            f"errors={result.error_count}: {result.report_path}"
        )
        if result.error_count:
            typer.echo(f"Standardized raw upload completed with errors. Review report: {result.report_path}", err=True)
            raise typer.Exit(code=1)

    @app.command("drive-shadow")
    def drive_shadow(
        source_folder_id: str = typer.Option(..., "--source-folder-id", help="Google Drive source folder ID."),
        dest_folder_id: str = typer.Option(..., "--dest-folder-id", help="Google Drive destination folder ID."),
        report_path: Path = typer.Option(Path("drive_shadow_report.json"), "--report-path"),
        allow_partial: bool = typer.Option(False, "--allow-partial", help="Return success even when some Drive items fail."),
    ) -> None:
        """Copy ordinary files/folders between Google Drive folders."""
        result = shadow_google_drive_folder(
            source_folder_id,
            dest_folder_id,
            report_path=report_path,
        )
        typer.echo(
            "Drive shadow summary: "
            f"files_copied={result.copied_files} "
            f"folders_created={result.created_folders} "
            f"skipped_existing={result.skipped_existing} "
            f"skipped_google_apps={result.skipped_google_apps} "
            f"errors={result.error_count} "
            f"report_path={result.report_path}"
        )
        no_actions = (
            result.copied_files == 0
            and result.created_folders == 0
            and result.skipped_existing == 0
            and result.skipped_google_apps == 0
        )
        if result.error_count and not allow_partial:
            typer.echo(f"Drive shadow failed with errors. Review report: {result.report_path}", err=True)
            raise typer.Exit(code=1)
        if no_actions and not allow_partial:
            typer.echo(f"Drive shadow made no changes or skips. Review report: {result.report_path}", err=True)
            raise typer.Exit(code=1)

    @app.command("standardize-archives")
    def standardize_archives(
        source_dir: Path = typer.Option(..., "--source-dir", help="Folder containing organizer zip files."),
        target_dir: Path = typer.Option(..., "--target-dir", help="Target folder that will receive raw_videos/ and metadata/."),
        temp_dir: Path | None = typer.Option(None, "--temp-dir", help="Temporary extraction folder."),
        media_extensions: str = typer.Option(
            ".mp4,.mov,.mkv,.avi,.webm,.wav",
            "--media-extensions",
            help="Comma-separated media extensions to move into raw_videos/.",
        ),
        overwrite: bool = typer.Option(False, "--overwrite/--no-overwrite"),
        resume: bool = typer.Option(True, "--resume/--no-resume", help="Resume completed source items from the progress JSONL."),
        progress_path: Path | None = typer.Option(None, "--progress-path", help="Optional progress JSONL path."),
        min_free_gb: float = typer.Option(15.0, "--min-free-gb", help="Minimum free local disk GB to keep before staging files."),
        drive_sync_sleep_seconds: int = typer.Option(30, "--drive-sync-sleep-seconds", help="Seconds to sleep after sync when DriveFS cache leaves low free disk."),
        cleanup_every_files: int = typer.Option(1, "--cleanup-every-files", help="Cleanup command-created temp stages after this many processed files."),
        cleanup_every_gb: float = typer.Option(50.0, "--cleanup-every-gb", help="Cleanup command-created temp stages after this many processed GB."),
        allow_partial: bool = typer.Option(False, "--allow-partial", help="Return success even when some archives/files fail."),
    ) -> None:
        """Extract zip archives and flatten media/JSON into System 1 input layout.

        Disk-safe options: --min-free-gb --drive-sync-sleep-seconds
        --cleanup-every-files --cleanup-every-gb.
        """
        extensions = {item.strip().lower() for item in media_extensions.split(",") if item.strip()}
        result = standardize_archive_source(
            source_dir,
            target_dir,
            temp_dir=temp_dir,
            media_extensions=extensions,
            overwrite=overwrite,
            resume=resume,
            progress_path=progress_path,
            min_free_gb=min_free_gb,
            drive_sync_sleep_seconds=drive_sync_sleep_seconds,
            cleanup_every_files=cleanup_every_files,
            cleanup_every_gb=cleanup_every_gb,
        )
        typer.echo(
            "Standardized archives "
            f"zips={result.zip_count} media={result.video_count} metadata={result.metadata_count} "
            f"skipped={result.skipped_count} errors={result.error_count}: {result.report_path}"
        )
        if result.error_count and not allow_partial:
            typer.echo(f"Archive standardization failed with errors. Review report: {result.report_path}", err=True)
            raise typer.Exit(code=1)
