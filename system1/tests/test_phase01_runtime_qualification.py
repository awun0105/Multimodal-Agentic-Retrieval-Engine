from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from system1.phase01_qualification import (
    classify_pip_check,
    compose_candidate_manifest,
    runtime_identity,
    sanitize_payload,
    validate_candidate_runtime_isolation,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = {
    "candidates": {
        "candidate-a": {
            "overrides": {
                "numpy": "==2.1.3",
                "nemo-toolkit": "==2.7.3",
                "transformers": "==4.57.6",
            }
        },
        "candidate-b": {
            "requires_previous_candidate": "candidate-a",
            "allowed_previous_failure_checks": ["nemo_restore"],
            "overrides": {
                "numpy": "==2.1.3",
                "nemo-toolkit": "==3.0.0",
                "transformers": "==4.53.3",
            },
        },
    }
}


def test_candidate_manifest_uses_base_and_production_extra() -> None:
    manifest = compose_candidate_manifest(
        pyproject_path=ROOT / "pyproject.toml",
        qualification_config=CONFIG,
        candidate="candidate-a",
    )

    requirements = set(manifest.requirements)
    assert "numpy==2.1.3" in requirements
    assert "pandas>=2.0.0" in requirements
    assert "pyarrow>=15.0.0" in requirements
    assert "torch==2.8.0" in requirements
    assert "transformers==4.57.6" in requirements
    assert "nemo_toolkit[asr]==2.7.3" in requirements
    assert manifest.overrides["nemo-toolkit"]["preserved_extras"] == ["asr"]


def test_candidate_manifest_preserves_marker(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[project]
dependencies = ["numpy>=1.26; python_version >= '3.10'"]
[project.optional-dependencies]
phase01-production = [
  "nemo_toolkit[asr]==2.6.0; platform_system == 'Linux'",
  "transformers>=4.51.0",
]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    manifest = compose_candidate_manifest(
        pyproject_path=pyproject,
        qualification_config=CONFIG,
        candidate="candidate-a",
    )

    assert any(
        value.startswith("numpy==2.1.3;") and "python_version" in value
        for value in manifest.requirements
    )
    assert any(
        value.startswith("nemo_toolkit[asr]==2.7.3;") and "platform_system" in value
        for value in manifest.requirements
    )


def test_repository_nemo273_candidate_uses_supported_transformers_minor() -> None:
    qualification_config = yaml.safe_load(
        (ROOT / "configs" / "runtime_qualification.yaml").read_text(
            encoding="utf-8"
        )
    )

    manifest = compose_candidate_manifest(
        pyproject_path=ROOT / "pyproject.toml",
        qualification_config=qualification_config,
        candidate="py313-nemo273",
    )

    requirements = set(manifest.requirements)
    assert "nemo_toolkit[asr]==2.7.3" in requirements
    assert "transformers==4.57.6" in requirements


def test_candidate_manifest_rejects_missing_override_target(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[project]
dependencies = ["numpy>=1.26"]
[project.optional-dependencies]
phase01-production = ["nemo_toolkit[asr]==2.6.0"]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="exactly one"):
        compose_candidate_manifest(
            pyproject_path=pyproject,
            qualification_config=CONFIG,
            candidate="candidate-a",
        )


def test_pip_check_classifies_requirement_owner_not_dependency_name() -> None:
    result = classify_pip_check(
        "\n".join(
            [
                "nemo-toolkit 2.6.0 has requirement numpy<2, but you have numpy 2.1.3.",
                "rasterio 1.3.0 has requirement numpy>=2, but you have numpy 1.26.4.",
                "gradio 5.0.0 requires huggingface-hub<1.0, but you have 1.1.0.",
            ]
        )
    )

    assert [item["owner"] for item in result["hard_failures"]] == ["nemo-toolkit"]
    assert [item["owner"] for item in result["warnings"]] == ["rasterio", "gradio"]


def test_sanitizer_uses_allowlist_style_redaction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HF_TOKEN", "hf_abcdefghijklmnopqrstuvwxyz123456")
    value = sanitize_payload(
        {
            "message": (
                "Bearer abcdef https://user:pass@example.test/file?token=secret&safe=yes "
                "hf_abcdefghijklmnopqrstuvwxyz123456"
            )
        }
    )["message"]

    assert "abcdef" not in value
    assert "user:pass" not in value
    assert "secret" not in value
    assert "hf_abcdefghijklmnopqrstuvwxyz123456" not in value
    assert "safe=yes" in value


def test_candidate_b_requires_different_runtime(tmp_path: Path) -> None:
    identity = runtime_identity()
    previous = tmp_path / "previous.json"
    previous.write_text(
        json.dumps(
            {
                "candidate": "candidate-a",
                "status": "fail",
                "failed_check": "nemo_restore",
                "runtime_identity": identity,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="fresh runtime"):
        validate_candidate_runtime_isolation(
            candidate="candidate-b",
            qualification_config=CONFIG,
            previous_artifact=previous,
            current_identity=identity,
        )


def test_lightweight_cli_does_not_import_production_stack() -> None:
    code = (
        "import json,sys; import system1.phase01_qualification_cli; "
        "print(json.dumps(sorted(name for name in sys.modules "
        "if name == 'system1.phase01' or name.startswith('system1.phase01.'))))"
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-c", code],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        check=True,
    )

    assert json.loads(result.stdout) == []


def test_nemo_contract_is_synchronized_across_project_models_and_lock() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requirement = next(
        Requirement(value)
        for value in pyproject["project"]["optional-dependencies"][
            "phase01-production"
        ]
        if canonicalize_name(Requirement(value).name) == "nemo-toolkit"
    )
    assert requirement.extras == {"asr"}
    project_version = str(requirement.specifier).removeprefix("==")

    models = yaml.safe_load((ROOT / "configs" / "models.yaml").read_text())
    phase01 = models["phase01"]
    assert phase01["asr"]["install_package"] == f"nemo_toolkit[asr]=={project_version}"
    assert str(phase01["asr"]["package_version"]) == project_version
    assert phase01["asr_providers"]["nemo"]["install_package"] == (
        f"nemo_toolkit[asr]=={project_version}"
    )
    assert str(phase01["asr_providers"]["nemo"]["package_version"]) == project_version

    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked = [
        str(package["version"])
        for package in lock["package"]
        if package["name"] == "nemo-toolkit"
    ]
    assert locked == [project_version]
