from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
from collections import deque
from pathlib import Path

import numpy as np

FRAME_SHAPE = (27, 48, 3)
FRAME_BYTES = 27 * 48 * 3


def _load_model_class(source: Path):
    spec = importlib.util.spec_from_file_location("aic_transnetv2_upstream", source)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load official TransNet source module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TransNetV2


def _load_model(source: Path, weights: Path, device_name: str):
    import torch

    device = "cuda" if device_name == "auto" and torch.cuda.is_available() else "cpu"
    model = _load_model_class(source)()
    try:
        state = torch.load(weights, map_location="cpu", weights_only=True)
    except TypeError:  # pragma: no cover - older supported torch
        state = torch.load(weights, map_location="cpu")
    model.load_state_dict(state)
    model.eval().to(device)
    return model, device


def _predict_window(model, device: str, frames: list[np.ndarray]) -> np.ndarray:
    import torch

    array = np.stack(frames, axis=0)[None, ...]
    with torch.inference_mode():
        single, _many = model(torch.from_numpy(array).to(device))
        return torch.sigmoid(single)[0, 25:75, 0].cpu().numpy()


def _read_frame(stream) -> np.ndarray | None:
    data = stream.read(FRAME_BYTES)
    if not data:
        return None
    if len(data) != FRAME_BYTES:
        raise RuntimeError("ffmpeg returned a partial decoded frame")
    return np.frombuffer(data, dtype=np.uint8).reshape(FRAME_SHAPE).copy()


def predict_video(video: Path, source: Path, weights: Path, device_name: str) -> np.ndarray:
    model, device = _load_model(source, weights, device_name)
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(video),
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        "48x27",
        "pipe:1",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdout is not None
    first = _read_frame(process.stdout)
    if first is None:
        process.kill()
        raise RuntimeError("Video contains no decodable frames")
    window: deque[np.ndarray] = deque([first.copy() for _ in range(25)])
    window.append(first)
    frame_count = 1
    predictions: list[np.ndarray] = []
    last = first
    while True:
        frame = _read_frame(process.stdout)
        if frame is None:
            break
        window.append(frame)
        last = frame
        frame_count += 1
        if len(window) == 100:
            predictions.append(_predict_window(model, device, list(window)))
            for _ in range(50):
                window.popleft()
    stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"ffmpeg decode failed: {stderr.strip()}")
    while len(predictions) * 50 < frame_count:
        while len(window) < 100:
            window.append(last.copy())
        predictions.append(_predict_window(model, device, list(window)))
        for _ in range(min(50, len(window))):
            window.popleft()
    return np.concatenate(predictions)[:frame_count]


def predictions_to_scenes(
    predictions: np.ndarray,
    threshold: float,
    transition_run_boundary: str = "midpoint",
) -> list[list[int]]:
    """Collapse each interior transition span into one contiguous cut.

    TransNet may mark several consecutive frames for a dissolve. Canonical
    shots cannot omit those transition frames, so one midpoint boundary is
    selected for each positive run and the result partitions every frame.
    Runs touching the first or final frame are not treated as cuts.
    """

    if transition_run_boundary != "midpoint":
        raise ValueError(f"Unsupported transition-run policy: {transition_run_boundary}")
    cuts = (predictions > threshold).astype(np.uint8)
    if len(cuts) < 2 or bool(np.all(cuts)):
        return [[0, len(cuts) - 1]]
    runs: list[tuple[int, int]] = []
    index = 0
    while index < len(cuts):
        if cuts[index] == 0:
            index += 1
            continue
        run_start = index
        while index + 1 < len(cuts) and cuts[index + 1] == 1:
            index += 1
        runs.append((run_start, index))
        index += 1
    boundaries = [
        (start + end) // 2
        for start, end in runs
        if start > 0 and end < len(cuts) - 1
    ]
    scenes: list[list[int]] = []
    scene_start = 0
    for boundary in boundaries:
        if boundary >= scene_start:
            scenes.append([scene_start, boundary])
            scene_start = boundary + 1
    scenes.append([scene_start, len(cuts) - 1])
    return scenes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument(
        "--transition-run-boundary", choices=("midpoint",), default="midpoint"
    )
    parser.add_argument("--device", choices=("auto", "cpu"), default="auto")
    args = parser.parse_args()
    predictions = predict_video(args.video, args.source, args.weights, args.device)
    payload = {
        "schema_version": "transnetv2_predictions_v1",
        "frame_count": len(predictions),
        "threshold": args.threshold,
        "predictions_sha256": hashlib.sha256(predictions.astype(np.float32).tobytes()).hexdigest(),
        "transition_run_boundary": args.transition_run_boundary,
        "scenes_inclusive": predictions_to_scenes(
            predictions, args.threshold, args.transition_run_boundary
        ),
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
