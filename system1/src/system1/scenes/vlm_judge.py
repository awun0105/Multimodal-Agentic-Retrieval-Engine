from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from itertools import pairwise
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageOps

from system1.vlm import ModelRequest, TEXT_RESPONSE_SCHEMA
from system1.vlm import StructuredClient


class VlmSceneBoundaryJudge:
    def __init__(
        self,
        client: StructuredClient,
        *,
        video_id: str,
        prompt_dir: Path,
        diagnostics_dir: Path,
        model_config: Mapping[str, Any],
        focused_keyframe_roles: tuple[str, ...] = ("early", "late"),
    ) -> None:
        self.client = client
        self.video_id = video_id
        self.prompt_dir = prompt_dir
        self.diagnostics_dir = diagnostics_dir
        self.model_config = model_config
        self.focused_keyframe_roles = focused_keyframe_roles
        self.request_index = 0
        self._diagnostics: dict[str, dict[str, Any]] = {}

    def judge(
        self,
        focus_gap_ids: tuple[str, ...],
        context: Sequence[Mapping[str, Any]],
        request_kind: str = "primary",
    ) -> dict[str, bool]:
        if not focus_gap_ids:
            return {}

        base_prompt = str(self.model_config[f"prompt_version"]) if request_kind == "primary" else str(self.model_config[f"{request_kind}_prompt_version"])
        from system1.vlm.prompts import build_text_prompt

        self.diagnostics_dir.mkdir(parents=True, exist_ok=True)
        contact_sheet = self.diagnostics_dir / f"{self.request_index:05d}_{request_kind}.jpg"
        _write_contact_sheet(context, contact_sheet)
        image_paths = [contact_sheet]
        
        if request_kind != "primary":
            role_sheet = (
                self.diagnostics_dir
                / f"{self.request_index:05d}_{request_kind}_early_late.jpg"
            )
            if _write_role_contact_sheet(
                context,
                focus_gap_ids,
                role_sheet,
                roles=self.focused_keyframe_roles,
            ):
                image_paths.append(role_sheet)

        evidence_payload = [_json_safe_evidence(item) for item in context]
        
        requests = []
        for gap_id in focus_gap_ids:
            prompt = build_text_prompt(
                base_prompt,
                variables={}
            )
            prompt += f"\n\nEVIDENCE FOR SHOT {gap_id}:\n" + __import__("json").dumps(evidence_payload, ensure_ascii=False)
            
            requests.append(ModelRequest(
                request_kind=f"scene_boundary_{request_kind}",
                video_id=self.video_id,
                prompt=prompt,
                prompt_version=base_prompt,
                response_schema_version=str(self.model_config.get("decision_contract_version", "scene_boundary_label_v2")),
                response_mode="text",
                response_schema=TEXT_RESPONSE_SCHEMA,
                image_paths=tuple(image_paths),
                identity={"gap_id": gap_id},
            ))
            
        self.request_index += 1
        
        request_many = getattr(self.client, "request_many", None)
        if callable(request_many):
            responses = request_many(requests)
        else:
            responses = [self.client.request(req) for req in requests]
            
        result: dict[str, bool] = {}
        for req, resp in zip(requests, responses, strict=True):
            gap_id = req.identity["gap_id"]
            text_resp = str(resp.get("text", "")).strip().upper()
            
            is_boundary = "BOUNDARY" in text_resp
            result[gap_id] = is_boundary
            
            self._diagnostics[gap_id] = {
                "reason": "Text fallback extracted",
                "confidence": 1.0,
                "evidence_used": [],
                "raw_text": text_resp
            }
            
        return result

    def diagnostics_for(self, gap_id: str) -> Mapping[str, Any]:
        return self._diagnostics.get(gap_id, {})


def _write_contact_sheet(context: Sequence[Mapping[str, Any]], output: Path) -> None:
    tile_width, tile_height, label_height, columns = 320, 180, 32, 4
    rows = max(1, (len(context) + columns - 1) // columns)
    sheet = Image.new("RGB", (columns * tile_width, rows * (tile_height + label_height)), "black")
    draw = ImageDraw.Draw(sheet)
    for index, item in enumerate(context):
        x = (index % columns) * tile_width
        y = (index // columns) * (tile_height + label_height)
        image_path = Path(str(item["representative_path"]))
        with Image.open(image_path) as image:
            tile = ImageOps.fit(image.convert("RGB"), (tile_width, tile_height), method=Image.Resampling.LANCZOS)
        sheet.paste(tile, (x, y))
        label = f"{item['shot_id']} {float(item['start_sec']):.2f}-{float(item['end_sec']):.2f}s"
        draw.text((x + 4, y + tile_height + 6), label, fill="white")
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, format="JPEG", quality=90, subsampling=0)


def _write_role_contact_sheet(
    context: Sequence[Mapping[str, Any]],
    focus_gap_ids: tuple[str, ...],
    output: Path,
    *,
    roles: Sequence[str] = ("early", "late"),
) -> bool:
    relevant_ids = set(focus_gap_ids)
    for previous, current in pairwise(context):
        if str(previous["shot_id"]) in relevant_ids:
            relevant_ids.add(str(current["shot_id"]))
    tiles: list[tuple[str, str, Path]] = []
    for item in context:
        shot_id = str(item["shot_id"])
        if shot_id not in relevant_ids:
            continue
        for role in roles:
            if role == "supplemental":
                values = item.get("supplemental_paths", [])
                if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
                    tiles.extend(
                        (shot_id, role, Path(str(value)))
                        for value in values
                        if value
                    )
                continue
            value = item.get(f"{role}_path")
            if value:
                tiles.append((shot_id, role, Path(str(value))))
    if not tiles:
        return False
    tile_width, tile_height, label_height, columns = 320, 180, 32, 4
    rows = (len(tiles) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * tile_width, rows * (tile_height + label_height)), "black")
    draw = ImageDraw.Draw(sheet)
    for index, (shot_id, role, image_path) in enumerate(tiles):
        x = (index % columns) * tile_width
        y = (index // columns) * (tile_height + label_height)
        with Image.open(image_path) as image:
            tile = ImageOps.fit(
                image.convert("RGB"),
                (tile_width, tile_height),
                method=Image.Resampling.LANCZOS,
            )
        sheet.paste(tile, (x, y))
        draw.text((x + 4, y + tile_height + 6), f"{shot_id} {role}", fill="white")
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, format="JPEG", quality=90, subsampling=0)
    return True


def _json_safe_evidence(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "shot_id": str(item["shot_id"]),
        "start_sec": float(item["start_sec"]),
        "end_sec": float(item["end_sec"]),
        "caption_vi": str(item.get("caption_vi", "")),
        "caption_en": str(item.get("caption_en", "")),
        "objects_vi": _string_list(item.get("objects_vi", [])),
        "objects_en": _string_list(item.get("objects_en", [])),
        "actions_vi": _string_list(item.get("actions_vi", [])),
        "actions_en": _string_list(item.get("actions_en", [])),
        "visible_text_summary_vi": str(item.get("visible_text_summary_vi", "")),
        "visible_text_summary_en": str(item.get("visible_text_summary_en", "")),
        "ocr_text": _string_list(item.get("ocr_text", [])),
        "transcript": str(item.get("transcript", "")),
        "has_early_frame": bool(item.get("early_path")),
        "has_late_frame": bool(item.get("late_path")),
        "supplemental_frame_count": len(item.get("supplemental_paths", [])),
    }


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Sequence):
        return [str(item) for item in value if str(item).strip()]
    return []


# Compatibility for existing imports while production call sites use the
# provider-neutral name.
GeminiSceneBoundaryJudge = VlmSceneBoundaryJudge
