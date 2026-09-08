"""System 1 scenes package."""

__all__ = []
from .grouping import (
    BoundaryDecision,
    BoundaryVote,
    FocusWindow,
    SceneBoundaryJudge,
    SceneGroupingResult,
    ScenePartitionQuality,
    ScenePartitionQualityError,
    assess_partition_quality,
    group_scenes,
    partition_scenes,
    plan_focus_windows,
    vote_weight,
)
from .speech import (
    SpeechGapEvidence,
    build_speech_gap_evidence,
    render_speech_evidence,
    speech_diagnostics,
    validate_speech_policy,
)

__all__ = [
    "BoundaryDecision",
    "BoundaryVote",
    "FocusWindow",
    "SceneBoundaryJudge",
    "SceneGroupingResult",
    "ScenePartitionQuality",
    "ScenePartitionQualityError",
    "SpeechGapEvidence",
    "assess_partition_quality",
    "build_speech_gap_evidence",
    "group_scenes",
    "partition_scenes",
    "plan_focus_windows",
    "render_speech_evidence",
    "speech_diagnostics",
    "validate_speech_policy",
    "vote_weight",
]
