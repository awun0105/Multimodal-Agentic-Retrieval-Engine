from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer

from system1.phase01_qualification import (
    base_qualification_report,
    command_result_payload,
    compose_candidate_manifest,
    load_qualification_config,
    new_run_id,
    project_root_from_module,
    python_version_matches,
    runtime_identity,
    sanitize_payload,
    utc_now,
    validate_candidate_runtime_isolation,
    write_candidate_manifest,
    write_json_atomic,
)


def qualify(
    workspace: Annotated[Path, typer.Option("--workspace")],
    candidate: Annotated[str, typer.Option("--candidate")] = "py313-nemo273",
    project_root: Annotated[Path | None, typer.Option("--project-root")] = None,
    previous_artifact: Annotated[
        Path | None, typer.Option("--previous-artifact")
    ] = None,
) -> None:
    root = (project_root or project_root_from_module()).resolve()
    config_path = root / "configs" / "runtime_qualification.yaml"
    pyproject_path = root / "pyproject.toml"
    config = load_qualification_config(config_path)
    identity = runtime_identity()
    validate_candidate_runtime_isolation(
        candidate=candidate,
        qualification_config=config,
        previous_artifact=previous_artifact,
        current_identity=identity,
    )
    manifest = compose_candidate_manifest(
        pyproject_path=pyproject_path,
        qualification_config=config,
        candidate=candidate,
    )
    run_id = new_run_id()
    run_dir = workspace.resolve() / "qualification_runs" / run_id
    manifest_path = write_candidate_manifest(
        manifest, run_dir / "candidate-requirements.txt"
    )
    report_path = run_dir / "phase01_runtime_qualification_v1.json"
    report = base_qualification_report(
        run_id=run_id,
        candidate=candidate,
        identity=identity,
        manifest=manifest,
    )
    profile = config["candidates"][candidate]
    report["environment"]["requires_python"] = profile["requires_python"]
    write_json_atomic(report_path, report)
    if not python_version_matches(str(profile["requires_python"])):
        report["failed_check"] = "python_runtime"
        report["error"] = {
            "type": "UnsupportedPythonRuntime",
            "message": (
                f"Python {identity['python']} does not satisfy "
                f"{profile['requires_python']}"
            ),
        }
        report["finished_at"] = utc_now()
        write_json_atomic(report_path, report)
        typer.echo(str(report_path))
        raise typer.Exit(code=2)

    installer_process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-r",
            str(manifest_path),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    installer_stdout, installer_stderr = installer_process.communicate()
    installer = subprocess.CompletedProcess(
        installer_process.args,
        installer_process.returncode,
        installer_stdout,
        installer_stderr,
    )
    report["installer"] = command_result_payload(installer)
    report["installer"]["pid"] = installer_process.pid
    if installer.returncode != 0:
        report["failed_check"] = "candidate_install"
        report["error"] = {
            "type": "CandidateInstallError",
            "message": "candidate full-stack installation failed",
        }
        report["finished_at"] = utc_now()
        write_json_atomic(report_path, report)
        typer.echo(str(report_path))
        raise typer.Exit(code=installer.returncode or 1)

    runtime_installer = subprocess.run(
        [
            sys.executable,
            "-m",
            "system1.cli",
            "phase01-prepare-asr-runtime",
        ],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    report["asr_runtime_installer"] = command_result_payload(runtime_installer)
    if runtime_installer.returncode != 0:
        report["failed_check"] = "asr_runtime_install"
        report["error"] = {
            "type": "AsrRuntimeInstallError",
            "message": "pinned Flashlight runtime installation failed",
        }
        report["finished_at"] = utc_now()
        write_json_atomic(report_path, report)
        typer.echo(str(report_path))
        raise typer.Exit(code=runtime_installer.returncode or 1)

    context_path = run_dir / "qualification_context.json"
    write_json_atomic(
        context_path,
        {
            "schema_version": "phase01_runtime_qualification_context_v1",
            "run_id": run_id,
            "candidate": candidate,
            "runtime_identity": identity,
            "project_root": str(root),
            "workspace": str(workspace.resolve()),
            "run_dir": str(run_dir),
            "report_path": str(report_path),
            "qualification_config_path": str(config_path),
            "candidate_manifest": manifest.to_dict(),
            "installer": report["installer"],
            "asr_runtime_installer": report["asr_runtime_installer"],
            "controller_pid": os.getpid(),
            "installer_pid": installer_process.pid,
        },
    )
    worker = subprocess.run(
        [
            sys.executable,
            "-m",
            "system1.phase01_qualification_worker",
            "--context",
            str(context_path),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if worker.stdout:
        typer.echo(sanitize_payload(worker.stdout), nl=False)
    if worker.stderr:
        typer.echo(sanitize_payload(worker.stderr), err=True, nl=False)
    typer.echo(str(report_path))
    if worker.returncode != 0:
        raise typer.Exit(code=worker.returncode)


def main() -> None:
    typer.run(qualify)


if __name__ == "__main__":
    main()
