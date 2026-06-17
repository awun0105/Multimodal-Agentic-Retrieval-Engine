from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

DEFAULT_RELEASE_ID = "competition_dataset_v001"

_TRUE_VALUES = {"1", "true", "yes", "y", "on"}
_FALSE_VALUES = {"0", "false", "no", "n", "off"}

@dataclass(frozen=True)
class RuntimePaths:
    environment: str
    workspace_root: Path
    input_root: Path
    output_root: Path
    artifact_root: Path
    release_id: str
    batch_id: str
    worker_id: str
    resume: bool
    sync: bool
    force_rebuild: bool

@dataclass(frozen=True)
class RuntimeEnvironment:
    environment: str
    package_root: Path
    input_root: Path
    output_root: Path
    artifact_root: Path
    config_root: Path
    release_name: str = DEFAULT_RELEASE_ID

    @property
    def release_root(self) -> Path:
        return self.output_root / self.release_name

def detect_environment() -> str:
    if os.environ.get("KAGGLE_KERNEL_RUN_TYPE") or Path("/kaggle/working").exists():
        return "kaggle"
    try:
        import google.colab  # type: ignore  # noqa: F401
        return "colab"
    except Exception:
        if Path("/content").exists():
            return "colab"
        return "local"

def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    return default

def _resolve_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()

def _path_from_arg_or_env(value: str | Path | None, env_name: str, default: Path) -> Path:
    if value is not None:
        return _resolve_path(value)
    env_value = os.environ.get(env_name)
    if env_value:
        return _resolve_path(env_value)
    return _resolve_path(default)

def _string_from_arg_or_env(value: str | None, env_name: str, default: str) -> str:
    if value is not None:
        return value
    return os.environ.get(env_name, default)

def _bool_from_arg_or_env(value: bool | None, env_name: str, default: bool) -> bool:
    if value is not None:
        return value
    return parse_bool(os.environ.get(env_name), default)

def _workspace_root(environment: str) -> Path:
    if environment == "kaggle":
        return Path("/kaggle/working").resolve()
    if environment == "colab":
        return Path("/content").resolve()
    return Path.cwd().resolve()

def resolve_runtime_paths(
    *,
    input_root: str | Path | None = None,
    output_root: str | Path | None = None,
    artifact_root: str | Path | None = None,
    release_id: str | None = None,
    batch_id: str | None = None,
    worker_id: str | None = None,
    resume: bool | None = None,
    sync: bool | None = None,
    force_rebuild: bool | None = None,
) -> RuntimePaths:
    environment = detect_environment()
    workspace_root = _workspace_root(environment)
    default_input_root = workspace_root / "input"
    default_output_root = workspace_root / "output"
    default_artifact_root = workspace_root / "system1_artifacts"

    return RuntimePaths(
        environment=environment,
        workspace_root=workspace_root,
        input_root=_path_from_arg_or_env(input_root, "AIC_INPUT_ROOT", default_input_root),
        output_root=_path_from_arg_or_env(output_root, "AIC_OUTPUT_ROOT", default_output_root),
        artifact_root=_path_from_arg_or_env(artifact_root, "AIC_ARTIFACT_ROOT", default_artifact_root),
        release_id=_string_from_arg_or_env(release_id, "AIC_RELEASE_ID", DEFAULT_RELEASE_ID),
        batch_id=_string_from_arg_or_env(batch_id, "AIC_BATCH_ID", "batch_000"),
        worker_id=_string_from_arg_or_env(worker_id, "AIC_WORKER_ID", "worker_000"),
        resume=_bool_from_arg_or_env(resume, "AIC_RESUME", True),
        sync=_bool_from_arg_or_env(sync, "AIC_SYNC", True),
        force_rebuild=_bool_from_arg_or_env(force_rebuild, "AIC_FORCE_REBUILD", False),
    )

def package_root() -> Path:
    return Path(__file__).resolve().parents[3]

def _env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    if not value:
        return None
    return _resolve_path(value)

def resolve_runtime_environment() -> RuntimeEnvironment:
    paths = resolve_runtime_paths(
        input_root=os.environ.get("AIC_INPUT_ROOT") or os.environ.get("AIC_DATA_ROOT"),
        output_root=os.environ.get("AIC_OUTPUT_ROOT") or os.environ.get("AIC_RUNTIME_ROOT"),
        artifact_root=os.environ.get("AIC_ARTIFACT_ROOT"),
        release_id=os.environ.get("AIC_RELEASE_ID") or DEFAULT_RELEASE_ID,
    )
    root = _env_path("AIC_SYSTEM1_ROOT") or package_root()
    config_root = _env_path("AIC_CONFIG_ROOT") or (root / "configs").resolve()
    return RuntimeEnvironment(
        environment=paths.environment,
        package_root=root,
        input_root=paths.input_root,
        output_root=paths.output_root,
        artifact_root=paths.artifact_root,
        config_root=config_root,
        release_name=paths.release_id,
    )
