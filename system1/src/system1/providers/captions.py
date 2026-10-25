"""Shot captions: one JSON-schema constrained Qwen3-VL call per image (ADR 0023)."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from system1.text.evidence import is_prompt_echo

CAPTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "caption": {"type": "string", "minLength": 20, "maxLength": 400},
        "objects": {"type": "array", "items": {"type": "string", "maxLength": 40}, "maxItems": 12},
        "actions": {"type": "array", "items": {"type": "string", "maxLength": 60}, "maxItems": 6},
        "visible_text": {"type": "string", "maxLength": 300},
    },
    "required": ["caption", "objects", "actions", "visible_text"],
    "additionalProperties": False,
}

CAPTION_PROMPT = """Describe this video frame for a search index. Answer in Vietnamese.

Return one JSON object with these keys:
- caption: one or two sentences about who is visible, what they do, where, and notable details (clothing, colors, objects).
- objects: short names of the main visible objects.
- actions: short phrases for visible actions.
- visible_text: text that is clearly readable in the frame, copied exactly, or an empty string.

Describe only what is visible. Do not guess names, intentions, or events outside the frame. Do not calculate or complete text.

Example:
{"caption": "Một người đàn ông mặc áo sơ mi trắng đứng trước bảng xanh, tay chỉ vào phép tính viết bằng phấn.", "objects": ["bảng xanh", "phấn", "áo sơ mi trắng"], "actions": ["chỉ vào bảng"], "visible_text": "764 + 146"}"""

_LOOP = re.compile(r"(\S+(?:\s+\S+){0,3})(?:\s+\1){7,}")


@dataclass(frozen=True)
class CaptionResult:
    payload: dict[str, Any] | None
    problems: tuple[str, ...]


def has_repetition_loop(text: str) -> bool:
    """True when a phrase of up to four tokens repeats eight or more times in a row."""

    return bool(_LOOP.search(text))


def parse_caption(raw: str) -> CaptionResult:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return CaptionResult(None, ("invalid_json",))
    if not isinstance(payload, dict) or set(payload) != set(CAPTION_SCHEMA["required"]):
        return CaptionResult(None, ("invalid_fields",))
    texts = [payload["caption"], payload["visible_text"], *payload["objects"], *payload["actions"]]
    problems = []
    if any(has_repetition_loop(str(text)) for text in texts):
        problems.append("repetition_loop")
    if any(is_prompt_echo(str(text), CAPTION_PROMPT) for text in texts if str(text).strip()):
        problems.append("prompt_echo")
    return CaptionResult(None if problems else payload, tuple(problems))


class QwenCaptioner:
    def __init__(self, config: Mapping[str, Any], device: str = "cuda") -> None:
        import torch
        import xgrammar as xgr
        from transformers import AutoModelForImageTextToText, AutoProcessor

        self._torch = torch
        self._xgr = xgr
        self.config = config
        self.model = AutoModelForImageTextToText.from_pretrained(
            config["model_id"], revision=config["revision"], dtype=torch.float16, device_map=device
        )
        self.processor = AutoProcessor.from_pretrained(config["model_id"], revision=config["revision"])
        self.processor.tokenizer.padding_side = "left"
        vocab_size = self.model.get_output_embeddings().weight.shape[0]
        info = xgr.TokenizerInfo.from_huggingface(self.processor.tokenizer, vocab_size=vocab_size)
        self.grammar = xgr.GrammarCompiler(info).compile_json_schema(json.dumps(CAPTION_SCHEMA))

    def caption(self, images: Sequence[Any]) -> list[CaptionResult]:
        """Caption PIL images in batches; each result is validated by `parse_caption`."""

        results: list[CaptionResult] = []
        size = int(self.config["batch_size"])
        for offset in range(0, len(images), size):
            conversations = []
            for image in images[offset:offset + size]:
                image = image.copy()
                image.thumbnail((int(self.config["max_image_side"]),) * 2)
                conversations.append([{"role": "user", "content": [
                    {"type": "image", "image": image}, {"type": "text", "text": CAPTION_PROMPT}]}])
            inputs = self.processor.apply_chat_template(
                conversations, tokenize=True, add_generation_prompt=True, padding=True,
                return_dict=True, return_tensors="pt").to(self.model.device)
            with self._torch.no_grad():
                output = self.model.generate(
                    **inputs, max_new_tokens=int(self.config["max_new_tokens"]), do_sample=False,
                    logits_processor=[self._xgr.contrib.hf.LogitsProcessor(self.grammar)])
            texts = self.processor.batch_decode(
                output[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)
            results += [parse_caption(text) for text in texts]
        return results

    def close(self) -> None:
        del self.model
        self._torch.cuda.empty_cache()
