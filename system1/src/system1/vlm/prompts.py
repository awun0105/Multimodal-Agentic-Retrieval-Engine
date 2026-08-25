from __future__ import annotations

from collections.abc import Mapping
from typing import Any

TEXT_BUNDLE_VERSIONS: dict[str, dict[str, str]] = {
    "shot_caption_plain_text_fields_v1": {
        "caption_vi": "shot_caption_vi_v1",
        "caption_en": "shot_caption_en_v1",
        "objects_vi": "shot_objects_vi_v1",
        "objects_en": "shot_objects_en_v1",
        "actions_vi": "shot_actions_vi_v1",
        "actions_en": "shot_actions_en_v1",
        "visible_text_summary_vi": "shot_visible_text_summary_vi_v1",
        "visible_text_summary_en": "shot_visible_text_summary_en_v1",
    },
    "scene_summary_plain_text_v2": {
        "summary_vi": "scene_summary_vi_v2",
        "summary_en": "scene_summary_en_v2",
    },
}

_PROMPT_TEMPLATES: dict[str, str] = {
    "shot_caption_vi_v1": "Mô tả chi tiết nội dung chính của video này bằng tiếng Việt. Tập trung vào chủ thể, sự kiện, không gian, thời gian, và không khí chung.",
    "shot_caption_en_v1": "Describe the main content of this video in English. Focus on subjects, events, settings, time, and overall atmosphere.",
    "shot_objects_vi_v1": "Liệt kê các đối tượng vật lý quan trọng (người, động vật, xe cộ, đồ vật, công trình, v.v.) xuất hiện rõ trong video này bằng tiếng Việt. Mỗi đối tượng hoặc nhóm đối tượng trên một dòng.",
    "shot_objects_en_v1": "List the key physical objects (people, animals, vehicles, items, structures, etc.) clearly visible in this video in English. One object or group per line.",
    "shot_actions_vi_v1": "Mô tả các hành động, chuyển động, hoặc sự kiện cụ thể đang diễn ra trong video này bằng tiếng Việt.",
    "shot_actions_en_v1": "Describe the specific actions, movements, or events happening in this video in English.",
    "shot_visible_text_summary_vi_v1": "Tóm tắt ngắn gọn nội dung của bất kỳ văn bản nào có thể đọc được xuất hiện trong video (bảng hiệu, phụ đề cứng, chữ trên áo, v.v.) bằng tiếng Việt. Nếu không có chữ, trả về 'NONE'.",
    "shot_visible_text_summary_en_v1": "Briefly summarize the content of any readable text appearing in the video (signs, hard subs, text on clothing, etc.) in English. If no text is visible, return 'NONE'.",

    "scene_boundary_primary_label_v2": "You are a video editor. Look at this frame from Shot A and this frame from Shot B. Are they part of the exact same continuous scene/event? Answer strictly with one word: SAME_SCENE or BOUNDARY.",
    "scene_boundary_focused_label_v2": "You are a video editor. Look closely at this frame from Shot A and this frame from Shot B. The context suggests they might be different, but are they physically part of the exact same continuous scene/event? Answer strictly with one word: SAME_SCENE or BOUNDARY.",
    "scene_boundary_consistency_label_v2": "You are a video editor reviewing a sequence. Look at these two consecutive shots (A and B). Is there a clear, definitive scene change between them? Answer strictly with one word: SAME_SCENE or BOUNDARY.",

    "scene_summary_vi_v2": "Dựa trên các hình ảnh từ các phân cảnh trong một video, hãy tóm tắt nội dung chính của toàn bộ chuỗi sự kiện này bằng tiếng Việt trong một đoạn văn duy nhất.",
    "scene_summary_en_v2": "Based on the frames from various shots in a video, summarize the main content of this entire sequence of events in English in a single paragraph.",
}

def build_text_prompt(
    prompt_version: str,
    *,
    variables: Mapping[str, Any] | None = None,
) -> str:
    template = _PROMPT_TEMPLATES.get(prompt_version)
    if not template:
        raise ValueError(f"Unknown prompt_version: {prompt_version}")

    if not variables:
        return template

    result = template
    for key, value in variables.items():
        result = result.replace(f"{{{{{key}}}}}", str(value))
    return result
