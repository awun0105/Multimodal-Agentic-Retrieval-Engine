from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REQUIRED_CONFIGS = ("artifact.yaml", "dataset.yaml", "frame.yaml", "media.yaml", "models.yaml", "preprocessing.yaml", "release.yaml")


@dataclass(frozen=True)
class ProviderPlan:
    asr: str
    ocr: str
    embedding: str
    object_detection: str
    shot_caption: str
    scene_summary: str

    @property
    def uses_only_mock_providers(self) -> bool:
        values = {self.asr, self.ocr, self.embedding, self.object_detection, self.shot_caption, self.scene_summary}
        return values == {"mock"}


def load_configs(config_dir: Path | str) -> dict[str, dict[str, Any]]:
    root = Path(config_dir)
    configs: dict[str, dict[str, Any]] = {}
    for name in REQUIRED_CONFIGS:
        path = root / name
        if not path.exists():
            raise FileNotFoundError(f"missing config file: {path}")
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError(f"config must be a mapping: {path}")
        configs[path.stem] = data
    return configs


def load_provider_plan(config_dir: Path | str, provider_profile: str) -> ProviderPlan:
    configs = load_configs(config_dir)
    provider_defaults = configs["models"].get("providers", {})
    if provider_profile == "mock":
        return ProviderPlan(**{key: "mock" for key in _provider_keys()})
    if provider_profile == "real":
        return ProviderPlan(
            asr="whisper",
            ocr="paddleocr",
            embedding="openclip",
            object_detection="yolo",
            shot_caption="vlm",
            scene_summary="llm",
        )
    if provider_profile == "rule_based":
        return ProviderPlan(
            asr=provider_defaults.get("asr", "mock"),
            ocr=provider_defaults.get("ocr", "mock"),
            embedding=provider_defaults.get("embedding", "mock"),
            object_detection=provider_defaults.get("object_detection", "mock"),
            shot_caption="rule_based",
            scene_summary="rule_based",
        )
    if provider_profile == "vlm":
        return ProviderPlan(
            asr=provider_defaults.get("asr", "mock"),
            ocr=provider_defaults.get("ocr", "mock"),
            embedding=provider_defaults.get("embedding", "mock"),
            object_detection=provider_defaults.get("object_detection", "mock"),
            shot_caption="vlm",
            scene_summary="llm",
        )
    if provider_profile == "config":
        return ProviderPlan(**{key: str(provider_defaults.get(key, "mock")) for key in _provider_keys()})
    raise ValueError(f"unsupported provider profile: {provider_profile}")


def _provider_keys() -> tuple[str, ...]:
    return ("asr", "ocr", "embedding", "object_detection", "shot_caption", "scene_summary")
