from __future__ import annotations

import gc
import hashlib
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from huggingface_hub import snapshot_download

from .alignment import (
    ALIGNMENT_METHOD,
    ALIGNMENT_VERSION,
    AsrAlignmentError,
    align_nemo_hypothesis_words,
)
from .contracts import AsrResult
from .quality import (
    alignment_metrics,
    evaluate_transcript,
    low_information_text,
    normalize_for_comparison,
)
from .runtime import has_audio_stream, is_retryable_local_error, release_gpu_memory
from .timing import index_frame_timeline, time_range_to_frames
from .vad import SpeechRange, detect_speech_ranges


class AsrResourceError(RuntimeError):
    """Retryable ASR resource failure that must not silently change decoding."""


def transcribe_video(
    video_path: Path | str,
    *,
    video_id: str,
    frame_timeline: list[dict[str, Any]],
    config: Mapping[str, Any],
    model_factory: Callable[..., Any] | None = None,
    audio_present: bool | None = None,
    pre_load_callback: Callable[[str], None] | None = None,
    speech_range_detector: Callable[..., list[SpeechRange]] | None = None,
) -> AsrResult:
    present = has_audio_stream(video_path) if audio_present is None else audio_present
    if not present:
        return AsrResult(
            status="no_audio",
            segment_rows=[],
            word_rows=[],
            compute_type=None,
            attempts=0,
            detected_language=None,
            status_details={
                "decoder": _decoder_identity(config),
                **_alignment_status_details([], [], rejected=0),
            },
        )

    video_path = Path(video_path)
    duration = _media_duration(video_path) or _timeline_duration(frame_timeline)
    detector = speech_range_detector or detect_speech_ranges
    segmentation = _mapping(config, "segmentation")
    ranges = detector(
        video_path,
        duration_seconds=duration,
        config=segmentation,
    )
    if not ranges:
        return AsrResult(
            status="no_speech",
            segment_rows=[],
            word_rows=[],
            compute_type=None,
            attempts=0,
            detected_language=str(config.get("language", "vi")),
            status_details={
                "decoder": _decoder_identity(config),
                "speech_range_count": 0,
                "accepted_segment_count": 0,
                "rejected_segment_count": 0,
                **_alignment_status_details([], [], rejected=0),
            },
        )

    factory = model_factory or _load_pinned_nemo_model
    total_attempts = int(config.get("total_attempts", 2))
    last_error: Exception | None = None
    for attempt in range(1, total_attempts + 1):
        model = None
        try:
            device = _device()
            if pre_load_callback is not None:
                pre_load_callback("nemo_flashlight_beam64")
            model = factory(str(config["model_id"]), config=config)
            if hasattr(model, "to"):
                model = model.to(device)
            if hasattr(model, "eval"):
                model.eval()
            segment_rows, word_rows, diagnostics = _transcribe_streaming(
                model,
                video_path,
                ranges=ranges,
                video_id=video_id,
                frame_timeline=frame_timeline,
                config=config,
            )
            rejected = sum(not bool(item["accepted"]) for item in diagnostics)
            return AsrResult(
                status="pass" if segment_rows else "low_confidence",
                segment_rows=segment_rows,
                word_rows=word_rows,
                compute_type=str(device),
                attempts=attempt,
                detected_language=str(config.get("language", "vi")),
                diagnostics=diagnostics,
                status_details={
                    "decoder": _decoder_identity(config),
                    "speech_range_count": len(ranges),
                    "accepted_segment_count": len(segment_rows),
                    "rejected_segment_count": rejected,
                    **_alignment_status_details(
                        segment_rows, word_rows, rejected=rejected
                    ),
                },
            )
        except AsrAlignmentError:
            raise
        except Exception as exc:
            last_error = exc
            if not is_retryable_local_error(exc):
                raise
            if attempt >= total_attempts:
                break
        finally:
            del model
            release_gpu_memory()
    raise AsrResourceError(
        "NeMo Flashlight ASR resource failure after "
        f"{total_attempts} attempt(s); greedy decoding is forbidden: {last_error}"
    ) from last_error


def _transcribe_streaming(
    model: Any,
    video_path: Path,
    *,
    ranges: list[SpeechRange],
    video_id: str,
    frame_timeline: list[dict[str, Any]],
    config: Mapping[str, Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    quality_config = _mapping(config, "quality_gate")
    diagnostics: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    previous_text = ""
    blank_index = _ctc_blank_index(model)
    timeline_index = index_frame_timeline(frame_timeline)

    with tempfile.TemporaryDirectory(prefix="system1_nemo_asr_") as temporary:
        temp_dir = Path(temporary)
        for speech_range in ranges:
            wav_path = temp_dir / f"segment_{speech_range.segment_index:05d}.wav"
            _extract_audio_segment(
                video_path,
                wav_path,
                start_sec=speech_range.start_sec,
                duration_sec=speech_range.end_sec - speech_range.start_sec,
            )
            hypothesis: Any = None
            try:
                hypothesis = _transcribe_one(model, wav_path)
                text = _transcription_text(hypothesis)
                if speech_range.overlap_seconds > 0 and previous_text:
                    text = _remove_forced_overlap(previous_text, text)
                acoustic = alignment_metrics(hypothesis, blank_index=blank_index)
                decision = evaluate_transcript(
                    text,
                    duration_seconds=speech_range.end_sec - speech_range.start_sec,
                    acoustic_metrics=acoustic,
                    config=quality_config,
                )
                diagnostic = {
                    "segment_index": speech_range.segment_index,
                    "start_sec": speech_range.start_sec,
                    "end_sec": speech_range.end_sec,
                    "forced_split": speech_range.forced_split,
                    "overlap_seconds": speech_range.overlap_seconds,
                    "text": text,
                    "accepted": decision.accepted,
                    "reason_codes": list(decision.reason_codes),
                    "metrics": decision.metrics,
                    "alignment_status": "not_required",
                    "alignment_method": ALIGNMENT_METHOD,
                    "alignment_version": ALIGNMENT_VERSION,
                    "alignment_frame_count": decision.metrics.get("alignment_frames"),
                    "aligned_word_count": 0,
                    "alignment_error": None,
                }
                segment_id = f"{video_id}_ASR{speech_range.segment_index:05d}"
                aligned_words: list[dict[str, Any]] = []
                if decision.accepted:
                    aligned_words = align_nemo_hypothesis_words(
                        hypothesis,
                        model,
                        text=text,
                        segment_id=segment_id,
                        video_id=video_id,
                        segment_start_sec=float(speech_range.start_sec),
                        segment_end_sec=float(speech_range.end_sec),
                        frame_timeline=timeline_index,
                        provider="nemo",
                        model_name=str(config["model_id"]),
                        model_version=str(config["model_revision"]),
                    )
                    diagnostic["alignment_status"] = "aligned"
                    diagnostic["aligned_word_count"] = len(aligned_words)
                diagnostics.append(diagnostic)
                candidates.append(
                    {
                        "range": speech_range,
                        "text": text,
                        "accepted": decision.accepted,
                        "diagnostic": diagnostic,
                        "words": aligned_words,
                    }
                )
                if text:
                    previous_text = text
            finally:
                wav_path.unlink(missing_ok=True)
                del hypothesis
                gc.collect()

    _apply_adjacent_repetition_gate(candidates, quality_config)
    rows: list[dict[str, Any]] = []
    word_rows: list[dict[str, Any]] = []
    for candidate in candidates:
        if not candidate["accepted"]:
            continue
        speech_range = candidate["range"]
        start_frame, end_frame = time_range_to_frames(
            speech_range.start_sec,
            speech_range.end_sec,
            timeline_index,
        )
        rows.append(
            {
                "asr_segment_id": (
                    f"{video_id}_ASR{speech_range.segment_index:05d}"
                ),
                "video_id": video_id,
                "start_sec": float(speech_range.start_sec),
                "end_sec": float(speech_range.end_sec),
                "start_frame": start_frame,
                "end_frame": end_frame,
                "text": candidate["text"],
                "language": str(config.get("language", "vi")),
                "confidence": None,
                "avg_logprob": None,
                "no_speech_prob": None,
                "provider": "nemo",
                "model_name": str(config["model_id"]),
                "model_version": str(config["model_revision"]),
                "status": "pass",
            }
        )
        word_rows.extend(candidate["words"])
    return rows, word_rows, diagnostics


def _transcribe_one(model: Any, wav_path: Path) -> Any:
    try:
        result = model.transcribe(
            [str(wav_path)],
            batch_size=1,
            return_hypotheses=True,
            verbose=False,
        )
    except TypeError as exc:
        raise RuntimeError(
            "Pinned NeMo runtime must support return_hypotheses for ASR quality gates"
        ) from exc
    return _first_hypothesis(result)


def _first_hypothesis(result: Any) -> Any:
    values = list(result)
    if not values:
        return ""
    value = values[0]
    hypotheses = getattr(value, "n_best_hypotheses", None)
    if hypotheses:
        return hypotheses[0]
    return value


def _load_pinned_nemo_model(
    model_id: str,
    *,
    config: Mapping[str, Any] | None = None,
) -> Any:
    try:
        import nemo.collections.asr as nemo_asr
        from omegaconf import OmegaConf
    except ImportError as exc:  # pragma: no cover - production preflight
        raise RuntimeError("nemo_toolkit[asr] is required for NeMo Phase01 ASR") from exc

    model_config = config or {}
    revision = str(model_config.get("model_revision", "")).strip()
    model_file = str(model_config.get("model_file", "")).strip()
    decoder = _mapping(model_config, "decoder")
    lm_file = str(decoder.get("language_model_file", "")).strip()
    lexicon_file = str(decoder.get("lexicon_file", "")).strip()
    if not revision or not model_file or not lm_file or not lexicon_file:
        raise RuntimeError("Pinned NeMo model, language model, and lexicon are required")

    snapshot_dir = Path(
        snapshot_download(
            repo_id=model_id,
            revision=revision,
            allow_patterns=[model_file, lm_file, lexicon_file],
        )
    )
    _verify_artifact(snapshot_dir / model_file, str(model_config["model_sha256"]))
    _verify_artifact(snapshot_dir / lm_file, str(decoder["language_model_sha256"]))
    _verify_artifact(snapshot_dir / lexicon_file, str(decoder["lexicon_sha256"]))
    model = nemo_asr.models.ASRModel.restore_from(str(snapshot_dir / model_file))
    _configure_flashlight_decoder(
        model,
        decoder,
        lm_path=snapshot_dir / lm_file,
        lexicon_path=snapshot_dir / lexicon_file,
        omega_conf=OmegaConf,
    )
    return model


def _configure_flashlight_decoder(
    model: Any,
    decoder: Mapping[str, Any],
    *,
    lm_path: Path,
    lexicon_path: Path,
    omega_conf: Any,
) -> None:
    if str(decoder.get("strategy")) != "flashlight":
        raise RuntimeError("Production NeMo ASR requires Flashlight decoding")
    decoding_cfg = omega_conf.create(
        {
            "strategy": "flashlight",
            "preserve_alignments": True,
            "compute_timestamps": False,
            "beam": {
                "beam_size": int(decoder.get("beam_size", 64)),
                "search_type": "flashlight",
                "ngram_lm_model": str(lm_path),
                "ngram_lm_alpha": float(decoder.get("beam_alpha", 0.3)),
                "beam_beta": float(decoder.get("beam_beta", 0.5)),
                "flashlight_cfg": {
                    "lexicon_path": str(lexicon_path),
                    "beam_size_token": int(decoder.get("beam_size_token", 32)),
                    "beam_threshold": float(decoder.get("beam_threshold", 20.0)),
                },
            },
        }
    )
    model.change_decoding_strategy(decoding_cfg)


def _decoder_identity(config: Mapping[str, Any]) -> dict[str, Any]:
    decoder = _mapping(config, "decoder")
    return {
        "strategy": decoder.get("strategy"),
        "beam_size": decoder.get("beam_size"),
        "beam_alpha": decoder.get("beam_alpha"),
        "beam_beta": decoder.get("beam_beta"),
        "beam_size_token": decoder.get("beam_size_token"),
        "beam_threshold": decoder.get("beam_threshold"),
        "language_model_sha256": decoder.get("language_model_sha256"),
        "lexicon_sha256": decoder.get("lexicon_sha256"),
    }


def _apply_adjacent_repetition_gate(
    candidates: list[dict[str, Any]],
    config: Mapping[str, Any],
) -> None:
    threshold = int(config.get("max_adjacent_low_information_repeats", 2))
    maximum_chars = int(config.get("low_information_max_chars", 12))
    maximum_tokens = int(config.get("low_information_max_tokens", 3))
    previous = ""
    run: list[dict[str, Any]] = []
    for candidate in candidates:
        text = str(candidate["text"])
        normalized = normalize_for_comparison(text)
        is_low_information = low_information_text(
            text,
            max_chars=maximum_chars,
            max_tokens=maximum_tokens,
        )
        if normalized and normalized == previous and is_low_information:
            run.append(candidate)
        else:
            run = [candidate]
            previous = normalized
        if len(run) <= threshold:
            continue
        for repeated in run:
            repeated["accepted"] = False
            diagnostic = repeated["diagnostic"]
            diagnostic["accepted"] = False
            reasons = list(diagnostic["reason_codes"])
            if "adjacent_low_information_repetition" not in reasons:
                reasons.append("adjacent_low_information_repetition")
            diagnostic["reason_codes"] = reasons


def _remove_forced_overlap(previous_text: str, current_text: str) -> str:
    previous = previous_text.split()
    current = current_text.split()
    maximum = min(12, len(previous), len(current))
    for count in range(maximum, 0, -1):
        left = normalize_for_comparison(" ".join(previous[-count:]))
        right = normalize_for_comparison(" ".join(current[:count]))
        if left and left == right:
            return " ".join(current[count:]).strip()
    return current_text.strip()


def _extract_audio_segment(
    video_path: Path,
    output_path: Path,
    *,
    start_sec: float,
    duration_sec: float,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-ss",
            f"{start_sec:.3f}",
            "-i",
            str(video_path),
            "-t",
            f"{duration_sec:.3f}",
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(output_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg ASR segment extraction failed: {result.stderr[-1000:]}")


def _transcription_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return str(getattr(value, "text", "")).strip()


def _ctc_blank_index(model: Any) -> int | None:
    tokenizer = getattr(model, "tokenizer", None)
    if tokenizer is not None:
        vocabulary = getattr(tokenizer, "vocab", None)
        if vocabulary is not None:
            return len(vocabulary)
    decoder = getattr(model, "decoder", None)
    vocabulary = getattr(decoder, "vocabulary", None)
    if vocabulary is not None:
        return len(vocabulary)
    return None


def _alignment_status_details(
    segment_rows: list[dict[str, Any]],
    word_rows: list[dict[str, Any]],
    *,
    rejected: int,
) -> dict[str, Any]:
    accepted = len(segment_rows)
    aligned = len({str(row["asr_segment_id"]) for row in word_rows})
    return {
        "accepted_segment_count": accepted,
        "rejected_segment_count": rejected,
        "word_count": len(word_rows),
        "aligned_segment_count": aligned,
        "alignment_failed_segment_count": 0,
        "word_alignment_coverage": aligned / accepted if accepted else 1.0,
        "alignment_method": ALIGNMENT_METHOD,
        "alignment_version": ALIGNMENT_VERSION,
    }


def _verify_artifact(path: Path, expected_sha256: str) -> None:
    if not path.is_file():
        raise RuntimeError(f"Pinned ASR artifact is missing: {path.name}")
    actual = _sha256_file(path)
    if actual != expected_sha256:
        raise RuntimeError(f"Pinned ASR artifact checksum mismatch: {path.name}")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _media_duration(video_path: Path) -> float | None:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def _timeline_duration(frame_timeline: list[dict[str, Any]]) -> float:
    if not frame_timeline:
        return 0.0
    last = frame_timeline[-1]
    return float(last["pts_time"]) + float(last.get("duration_time") or 0.0)


def _device() -> str:
    try:
        import torch

        return "cuda:0" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


def _mapping(config: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = config.get(key, {})
    if not isinstance(value, Mapping):
        raise TypeError(f"NeMo ASR {key} config must be a mapping")
    return value
