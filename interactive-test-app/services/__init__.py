"""
Package services cho Interactive Cockpit Studio.
"""

from .config import (
    PROJECT_ROOT,
    SRC_DIR,
    DATASET_DIR,
    SQLITE_DB_PATH,
    FAISS_INDEX_PATH,
    BENCHMARK_DIR,
    BENCHMARK_CSV,
    BENCHMARK_JSON,
    RAW_VIDEO_DIR,
    KEYFRAMES_OUT_DIR,
    THUMBS_OUT_DIR,
    TARGET_BENCHMARK_VIDEOS,
)

from .model_service import (
    get_clip_model,
    get_local_yolo_model,
    format_timestamp,
    parse_duration_limit,
    pil_to_base64_thumb,
    get_video_metadata,
    get_btc_keyframe_image,
    get_self_extracted_image,
    create_placeholder_keyframe_image,
)

from .appearance_service import (
    get_object_dominant_color_name,
    format_objects_natural_vietnamese,
    format_objects_natural_english,
    extract_detected_objects_with_appearance,
    analyze_image_full_spectrum,
    analyze_text_and_color,
    calculate_sharpness_fast,
    is_blank_or_solid_monochrome,
)

from .caption_service import (
    generate_keyframe_bilingual_captions,
)

from .timeline_service import (
    extract_video_keyframes_for_duration,
    render_side_by_side_comparison,
    _load_cached_self_keyframes,
    _save_cached_self_keyframes,
)

from .persistence_service import (
    get_persistence_summary_table,
    export_persisted_dataset_package,
    clean_storage_cache,
)

from .search_service import (
    run_multimodal_step_inspector,
    export_benchmark_report,
)
