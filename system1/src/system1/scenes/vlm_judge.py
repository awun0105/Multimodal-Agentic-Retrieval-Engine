from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import pairwise
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageOps

from system1.vlm import TEXT_RESPONSE_SCHEMA, ModelRequest, StructuredClient


class SemanticSceneBoundaryJudge:
    def __init__(
        self,
        client: StructuredClient,
        *,
        video_id: str,
        prompt_dir: Path,
        diagnostics_dir: Path,
        model_config: Mapping[str, Any],
        focused_keyframe_roles: tuple[str, ...] = ("early", "late"),
        max_ocr_chars_per_shot: int = 800,
        max_transcript_chars_per_shot: int = 1600,
    ) -> None:
        self.client = client
        self.video_id = video_id
        self.prompt_dir = prompt_dir
        self.diagnostics_dir = diagnostics_dir
        self.model_config = model_config
        self.focused_keyframe_roles = focused_keyframe_roles
        self.max_ocr_chars_per_shot = max_ocr_chars_per_shot
        self.max_transcript_chars_per_shot = max_transcript_chars_per_shot
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

        prompt_keys = {
            "primary": "prompt_version",
            "focused_review": "focused_prompt_version",
            "consistency_review": "consistency_prompt_version",
        }
        if request_kind not in prompt_keys:
            raise ValueError(f"Unsupported scene boundary request kind: {request_kind}")
        prompt_version = str(self.model_config[prompt_keys[request_kind]])
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

        fallback_sheet = image_paths[0]
        if len(image_paths) > 1:
            fallback_sheet = (
                self.diagnostics_dir
                / f"{self.request_index:05d}_{request_kind}_fallback.jpg"
            )
            _combine_contact_sheets(image_paths, fallback_sheet)

        requests: list[ModelRequest] = []
        for gap_id in focus_gap_ids:
            prompt = (
                build_text_prompt(prompt_version)
                + "\n\nBEGIN_EVIDENCE\n"
                + _render_gap_evidence(
                    context,
                    gap_id=gap_id,
                    max_ocr_chars=self.max_ocr_chars_per_shot,
                    max_transcript_chars=self.max_transcript_chars_per_shot,
                )
                + "\nEND_EVIDENCE"
            )
            requests.append(
                ModelRequest(
                    request_kind=f"scene_boundary_{request_kind}",
                    video_id=self.video_id,
                    prompt=prompt,
                    prompt_version=prompt_version,
                    response_schema_version=str(
                        self.model_config.get(
                            "decision_contract_version",
                            "scene_boundary_label_v2",
                        )
                    ),
                    response_schema=TEXT_RESPONSE_SCHEMA,
                    image_paths=tuple(image_paths),
                    fallback_image_paths=(fallback_sheet,),
                    identity={"after_shot_id": gap_id},
                    response_mode="text",
                    allowed_text_values=("BOUNDARY", "SAME_SCENE"),
                )
            )

        self.request_index += 1

        responses = self.client.request_many(requests)
        if len(responses) != len(requests):
            raise ValueError(
                "scene boundary client returned a different number of responses"
            )

        result: dict[str, bool] = {}
        for request, response in zip(requests, responses, strict=True):
            gap_id = str(request.identity["after_shot_id"])
            label = str(response["text"])
            result[gap_id] = label == "BOUNDARY"
            self._diagnostics[gap_id] = {
                "reason": None,
                "confidence": None,
                "evidence_used": [],
                "provider": response.get("__provider"),
                "model_name": response.get("__model_id"),
                "model_version": response.get("__model_revision"),
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


def _render_gap_evidence(
    context: Sequence[Mapping[str, Any]],
    *,
    gap_id: str,
    max_ocr_chars: int,
    max_transcript_chars: int,
) -> str:
    shot_ids = [str(item["shot_id"]) for item in context]
    try:
        left_index = shot_ids.index(gap_id)
    except ValueError as exc:
        raise ValueError(f"Scene boundary gap is outside its context: {gap_id}") from exc
    if left_index + 1 >= len(context):
        raise ValueError(f"Scene boundary gap has no right shot: {gap_id}")

    left_id = shot_ids[left_index]
    right_id = shot_ids[left_index + 1]
    blocks = [
        f"TARGET_LEFT_SHOT_ID: {left_id}",
        f"TARGET_RIGHT_SHOT_ID: {right_id}",
        "ORDERED_CONTEXT:",
    ]
    blocks.extend(
        _render_shot_evidence(
            item,
            role=(
                "TARGET_LEFT"
                if str(item["shot_id"]) == left_id
                else "TARGET_RIGHT"
                if str(item["shot_id"]) == right_id
                else "CONTEXT"
            ),
            max_ocr_chars=max_ocr_chars,
            max_transcript_chars=max_transcript_chars,
        )
        for item in context
    )
    return "\n\n".join(blocks)


def _render_shot_evidence(
    item: Mapping[str, Any],
    *,
    role: str,
    max_ocr_chars: int,
    max_transcript_chars: int,
) -> str:
    if max_ocr_chars < 1 or max_transcript_chars < 1:
        raise ValueError("Scene boundary evidence limits must be positive")
    ocr = " ".join(_string_list(item.get("ocr_text", [])))
    transcript = str(item.get("transcript", "")).strip()
    return "\n".join(
        (
            "--- SHOT ---",
            f"ROLE: {role}",
            f"SHOT_ID: {item['shot_id']}",
            f"TIME: {float(item['start_sec']):.3f}-{float(item['end_sec']):.3f}",
            f"CAPTION_VI: {item.get('caption_vi', '')}",
            f"CAPTION_EN: {item.get('caption_en', '')}",
            "OBJECTS_VI: " + " | ".join(_string_list(item.get("objects_vi", []))),
            "OBJECTS_EN: " + " | ".join(_string_list(item.get("objects_en", []))),
            "ACTIONS_VI: " + " | ".join(_string_list(item.get("actions_vi", []))),
            "ACTIONS_EN: " + " | ".join(_string_list(item.get("actions_en", []))),
            f"VISIBLE_TEXT_VI: {item.get('visible_text_summary_vi', '')}",
            f"VISIBLE_TEXT_EN: {item.get('visible_text_summary_en', '')}",
            "OCR:\n" + (_truncate(ocr, max_ocr_chars) or "<NONE>"),
            "TRANSCRIPT:\n"
            + (_truncate(transcript, max_transcript_chars) or "<NONE>"),
        )
    )


def _truncate(value: str, maximum: int) -> str:
    if len(value) <= maximum:
        return value
    marker = "\n[TRUNCATED]"
    return value[: max(0, maximum - len(marker))].rstrip() + marker


def _combine_contact_sheets(paths: Sequence[Path], output: Path) -> Path:
    images: list[Image.Image] = []
    try:
        for path in paths:
            with Image.open(path) as opened:
                images.append(opened.convert("RGB").copy())
        width = max(image.width for image in images)
        height = sum(image.height for image in images)
        combined = Image.new("RGB", (width, height), "black")
        offset = 0
        for image in images:
            combined.paste(image, (0, offset))
            offset += image.height
        output.parent.mkdir(parents=True, exist_ok=True)
        combined.save(output, format="JPEG", quality=90, subsampling=0)
    finally:
        for image in images:
            image.close()
    return output


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Sequence):
        return [str(item) for item in value if str(item).strip()]
    return []


# Compatibility aliases for callers that have not migrated the class name yet.
VlmSceneBoundaryJudge = SemanticSceneBoundaryJudge
