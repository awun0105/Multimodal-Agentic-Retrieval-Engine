from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tomllib
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yaml
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version


_PHASE01_PIP_CHECK_OWNERS = frozenset(
    canonicalize_name(name)
    for name in (
        "numpy",
        "pandas",
        "pyarrow",
        "torch",
        "torchvision",
        "torchaudio",
        "nemo-toolkit",
        "transformers",
        "bitsandbytes",
        "accelerate",
        "timm",
        "einops",
        "qwen-vl-utils",
        "onnx",
        "faster-whisper",
    )
)
_ALLOWED_ENVIRONMENT_KEYS = (
    "CUDA_VISIBLE_DEVICES",
    "COLAB_RELEASE_TAG",
    "KAGGLE_KERNEL_RUN_TYPE",
    "HF_HOME",
    "HF_HUB_CACHE",
    "TRANSFORMERS_CACHE",
)
_SECRET_ENV_PATTERN = re.compile(r"(?:TOKEN|KEY|SECRET|PASSWORD|AUTHORIZATION)", re.I)
_HF_TOKEN_PATTERN = re.compile(r"\bhf_[A-Za-z0-9]{16,}\b")
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_URL_PATTERN = re.compile(r"https?://[^\s\]\[<>\"']+")
_PIP_CHECK_OWNER_PATTERN = re.compile(
    r"^(?P<owner>[A-Za-z0-9_.-]+)(?:\s+[^\s]+)?\s+(?:has requirement|requires)\b",
    re.I,
)


@dataclass(frozen=True)
class CandidateManifest:
    candidate: str
    requirements: tuple[str, ...]
    manifest_sha256: str
    pyproject_sha256: str
    overrides: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate,
            "requirements": list(self.requirements),
            "manifest_sha256": self.manifest_sha256,
            "pyproject_sha256": self.pyproject_sha256,
            "overrides": self.overrides,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}_{uuid.uuid4().hex[:8]}"


def project_root_from_module() -> Path:
    return Path(__file__).resolve().parents[2]


def load_qualification_config(path: Path | str) -> dict[str, Any]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if payload.get("schema_version") != "phase01_runtime_qualification_config_v1":
        raise ValueError("unsupported Phase01 runtime qualification config")
    if not isinstance(payload.get("candidates"), dict):
        raise ValueError("qualification config is missing candidates")
    return payload


def compose_candidate_manifest(
    *,
    pyproject_path: Path | str,
    qualification_config: Mapping[str, Any],
    candidate: str,
) -> CandidateManifest:
    source = Path(pyproject_path)
    raw = source.read_bytes()
    project = tomllib.loads(raw.decode("utf-8")).get("project", {})
    base = project.get("dependencies")
    extras = project.get("optional-dependencies", {}).get("phase01-production")
    if not isinstance(base, list) or not isinstance(extras, list):
        raise ValueError(
            "candidate composition requires project.dependencies and "
            "project.optional-dependencies.phase01-production"
        )
    candidates = qualification_config.get("candidates", {})
    profile = candidates.get(candidate)
    if not isinstance(profile, Mapping):
        raise ValueError(f"unknown qualification candidate: {candidate}")
    overrides_payload = profile.get("overrides")
    if not isinstance(overrides_payload, Mapping):
        raise ValueError(f"candidate {candidate} has no overrides")
    overrides = {
        canonicalize_name(str(name)): str(specifier)
        for name, specifier in overrides_payload.items()
    }

    parsed = [Requirement(str(value)) for value in [*base, *extras]]
    grouped: dict[tuple[str, str], list[Requirement]] = {}
    for requirement in parsed:
        key = (
            canonicalize_name(requirement.name),
            str(requirement.marker or ""),
        )
        grouped.setdefault(key, []).append(requirement)
    for key, values in grouped.items():
        distinct = {_render_requirement(value) for value in values}
        if len(distinct) > 1:
            raise ValueError(
                "ambiguous direct dependency requirements for "
                f"{key[0]} marker={key[1]!r}: {sorted(distinct)}"
            )

    replaced_counts = {name: 0 for name in overrides}
    audit: dict[str, dict[str, Any]] = {}
    rendered: set[str] = set()
    for requirement in parsed:
        name = canonicalize_name(requirement.name)
        updated = requirement
        if name in overrides:
            before = _render_requirement(requirement)
            updated = _requirement_with_specifier(requirement, overrides[name])
            after = _render_requirement(updated)
            replaced_counts[name] += 1
            audit[name] = {
                "before": before,
                "after": after,
                "preserved_extras": sorted(requirement.extras),
                "preserved_marker": str(requirement.marker or ""),
            }
        rendered.add(_render_requirement(updated))
    invalid = {name: count for name, count in replaced_counts.items() if count != 1}
    if invalid:
        raise ValueError(
            "candidate overrides must each match exactly one direct requirement: "
            f"{invalid}"
        )
    nemo = next(
        Requirement(value)
        for value in rendered
        if canonicalize_name(Requirement(value).name) == "nemo-toolkit"
    )
    if "asr" not in nemo.extras:
        raise ValueError("candidate composition dropped nemo-toolkit[asr]")

    ordered = tuple(
        sorted(
            rendered,
            key=lambda value: (
                canonicalize_name(Requirement(value).name),
                str(Requirement(value).marker or ""),
                value,
            ),
        )
    )
    manifest_text = "\n".join(ordered) + "\n"
    return CandidateManifest(
        candidate=candidate,
        requirements=ordered,
        manifest_sha256=hashlib.sha256(manifest_text.encode("utf-8")).hexdigest(),
        pyproject_sha256=hashlib.sha256(raw).hexdigest(),
        overrides=audit,
    )


def write_candidate_manifest(manifest: CandidateManifest, path: Path | str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(manifest.requirements) + "\n"
    _atomic_write_text(target, text)
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != manifest.manifest_sha256:
        raise RuntimeError("candidate manifest changed while being written")
    return target


def runtime_identity() -> dict[str, str]:
    boot_id_path = Path("/proc/sys/kernel/random/boot_id")
    boot_id = (
        boot_id_path.read_text(encoding="utf-8").strip()
        if boot_id_path.is_file()
        else "unavailable"
    )
    values = {
        "boot_id": boot_id,
        "executable": str(Path(sys.executable).resolve()),
        "hostname": platform.node(),
        "python": platform.python_version(),
    }
    encoded = json.dumps(values, sort_keys=True, separators=(",", ":"))
    return {
        **values,
        "identity_sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
    }


def validate_candidate_runtime_isolation(
    *,
    candidate: str,
    qualification_config: Mapping[str, Any],
    previous_artifact: Path | str | None,
    current_identity: Mapping[str, str],
) -> None:
    profile = qualification_config["candidates"][candidate]
    required_previous = profile.get("requires_previous_candidate")
    if not required_previous:
        if previous_artifact is not None:
            raise ValueError(f"candidate {candidate} does not accept --previous-artifact")
        return
    if previous_artifact is None:
        raise ValueError(
            f"candidate {candidate} requires --previous-artifact from {required_previous}"
        )
    previous = json.loads(Path(previous_artifact).read_text(encoding="utf-8"))
    if previous.get("candidate") != required_previous or previous.get("status") != "fail":
        raise ValueError(
            f"candidate {candidate} requires a failed {required_previous} artifact"
        )
    failed_check = str(previous.get("failed_check") or "")
    allowed = {str(value) for value in profile.get("allowed_previous_failure_checks", [])}
    if failed_check not in allowed:
        raise ValueError(
            f"candidate {candidate} is not allowed after failed_check={failed_check!r}"
        )
    previous_identity = previous.get("runtime_identity", {}).get("identity_sha256")
    if previous_identity == current_identity.get("identity_sha256"):
        raise ValueError(
            f"candidate {candidate} must run in a fresh runtime, not the previous candidate runtime"
        )


def classify_pip_check(output: str) -> dict[str, Any]:
    hard_failures: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line == "No broken requirements found.":
            continue
        match = _PIP_CHECK_OWNER_PATTERN.match(line)
        owner = canonicalize_name(match.group("owner")) if match else "unparsed"
        entry = {"owner": owner, "message": line}
        if owner in _PHASE01_PIP_CHECK_OWNERS:
            hard_failures.append(entry)
        else:
            warnings.append(entry)
    return {
        "raw": output,
        "hard_failures": hard_failures,
        "warnings": warnings,
    }


def allowlisted_environment() -> dict[str, str]:
    return {
        key: os.environ[key]
        for key in _ALLOWED_ENVIRONMENT_KEYS
        if key in os.environ
    }


def sanitize_payload(value: Any) -> Any:
    secret_values = {
        text
        for key, raw in os.environ.items()
        if _SECRET_ENV_PATTERN.search(key)
        for text in [str(raw)]
        if len(text) >= 8
    }
    return _sanitize_value(value, secret_values=secret_values)


def write_json_atomic(path: Path | str, payload: Mapping[str, Any]) -> Path:
    target = Path(path)
    sanitized = sanitize_payload(dict(payload))
    text = json.dumps(sanitized, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _atomic_write_text(target, text)
    return target


def base_qualification_report(
    *,
    run_id: str,
    candidate: str,
    identity: Mapping[str, str],
    manifest: CandidateManifest,
) -> dict[str, Any]:
    return {
        "schema_version": "phase01_runtime_qualification_v1",
        "run_id": run_id,
        "candidate": candidate,
        "status": "fail",
        "ready_to_pin_production": False,
        "started_at": utc_now(),
        "finished_at": None,
        "runtime_identity": dict(identity),
        "candidate_manifest": manifest.to_dict(),
        "environment": {},
        "installed_packages": {},
        "pip_check": {"raw": "", "hard_failures": [], "warnings": []},
        "checks": {},
        "resources": {},
        "installer": {},
        "failed_check": None,
        "error": None,
    }


def command_result_payload(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return sanitize_payload(
        {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    )


def python_version_matches(specifier: str) -> bool:
    from packaging.specifiers import SpecifierSet

    return Version(platform.python_version()) in SpecifierSet(specifier)


def _render_requirement(requirement: Requirement) -> str:
    extras = f"[{','.join(sorted(requirement.extras))}]" if requirement.extras else ""
    if requirement.url:
        body = f"{requirement.name}{extras} @ {requirement.url}"
    else:
        body = f"{requirement.name}{extras}{requirement.specifier}"
    if requirement.marker:
        body += f"; {requirement.marker}"
    return body


def _requirement_with_specifier(requirement: Requirement, specifier: str) -> Requirement:
    extras = f"[{','.join(sorted(requirement.extras))}]" if requirement.extras else ""
    value = f"{requirement.name}{extras}{specifier}"
    if requirement.marker:
        value += f"; {requirement.marker}"
    return Requirement(value)


def _sanitize_value(value: Any, *, secret_values: set[str]) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _sanitize_value(item, secret_values=secret_values)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(item, secret_values=secret_values) for item in value]
    if not isinstance(value, str):
        return value
    text = value
    for secret in secret_values:
        text = text.replace(secret, "[REDACTED_SECRET]")
    text = _HF_TOKEN_PATTERN.sub("[REDACTED_HF_TOKEN]", text)
    text = _BEARER_PATTERN.sub("Bearer [REDACTED]", text)
    text = _URL_PATTERN.sub(lambda match: _sanitize_url(match.group(0)), text)
    return text


def _sanitize_url(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return "[REDACTED_URL]"
    hostname = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    netloc = f"{hostname}{port}"
    sensitive = re.compile(r"(?:token|signature|credential|x-amz-|auth)", re.I)
    query = [
        (key, "[REDACTED]" if sensitive.search(key) else item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
    ]
    return urlunsplit((parts.scheme, netloc, parts.path, urlencode(query), ""))


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.partial")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)
