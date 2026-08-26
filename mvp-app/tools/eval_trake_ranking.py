#!/usr/bin/env python3
"""Score the TRAKE ranking objective against the synthetic benchmark.

Mirrors production: the DP runs per video slice, then videos compete on the
objective. Running one DP over the whole matrix would let a path hop between
videos, which production never does.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import numpy as np

DEFAULT_RELEASE_DIR = Path("data/aic25-b1-v1")

NEG = -1e9


def load_data(db_path: str, embeddings_path: str):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    rows = conn.execute(
        "SELECT vector_id, video_id FROM keyframes ORDER BY video_id, keyframe_no"
    ).fetchall()
    conn.close()

    vector_ids = np.array([r[0] for r in rows])
    names = [r[1] for r in rows]
    slices = []
    start = 0
    for i in range(1, len(names) + 1):
        if i == len(names) or names[i] != names[start]:
            slices.append((names[start], start, i))
            start = i

    embeddings = np.asarray(
        np.load(embeddings_path, mmap_mode="r", allow_pickle=False), dtype=np.float32
    )
    return embeddings, vector_ids, slices


def dp_path_scores(sub: np.ndarray, objective: str) -> list[float] | None:
    """Per-event scores of the best path under `objective` ('sum' or 'min')."""
    length, events = sub.shape
    if length < events:
        return None
    dp = np.full((length, events), NEG, dtype=np.float64)
    backtrack = np.full((length, events), -1, dtype=np.int64)
    dp[:, 0] = sub[:, 0]
    for j in range(1, events):
        best, best_idx = NEG, -1
        for i in range(length):
            if i >= j and best > NEG:
                dp[i, j] = min(sub[i, j], best) if objective == "min" else sub[i, j] + best
                backtrack[i, j] = best_idx
            if dp[i, j - 1] > best:
                best, best_idx = dp[i, j - 1], i
    end = int(np.argmax(dp[:, events - 1]))
    if dp[end, events - 1] <= NEG:
        return None
    indices = [0] * events
    node = end
    for j in range(events - 1, -1, -1):
        indices[j] = node
        if j > 0:
            node = int(backtrack[node, j])
    return [float(sub[indices[j], j]) for j in range(events)]


OBJECTIVES = {
    "sum": (lambda p: sum(p), "sum"),
    "min": (lambda p: min(p), "min"),
    "sum_minus_spread": (lambda p: sum(p) - 2 * (max(p) - min(p)), "sum"),
}


def best_video(embeddings, vector_ids, slices, query_vector_ids, objective):
    key, dp_mode = OBJECTIVES[objective]
    scores = embeddings @ embeddings[np.array(query_vector_ids)].T
    best_name, best_value = None, None
    for name, start, end in slices:
        per_event = dp_path_scores(scores[vector_ids[start:end]], dp_mode)
        if per_event is None:
            continue
        value = key(per_event)
        if best_value is None or value > best_value:
            best_value, best_name = value, name
    return best_name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release-dir",
        type=Path,
        default=DEFAULT_RELEASE_DIR,
        help="Built release folder containing metadata/, index/ and reports/",
    )
    parser.add_argument(
        "--benchmark",
        type=Path,
        help="Override the benchmark JSON path (default: <release-dir>/reports/trake-benchmark.json)",
    )
    parser.add_argument(
        "objectives",
        nargs="*",
        default=None,
        help="Objectives to score; defaults to all of them",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    objectives = args.objectives if args.objectives else list(OBJECTIVES)
    db_path = str(args.release_dir / "metadata" / "runtime.sqlite")
    embeddings_path = str(args.release_dir / "index" / "embeddings.f16.npy")
    benchmark_path = args.benchmark or (
        args.release_dir / "reports" / "trake-benchmark.json"
    )
    embeddings, vector_ids, slices = load_data(db_path, embeddings_path)
    with open(benchmark_path, encoding="utf-8") as handle:
        benchmark = json.load(handle)
    items = benchmark if isinstance(benchmark, list) else benchmark.get("items", [])

    print(f"Benchmark: {len(items)} cases, {len(slices)} videos\n")
    print(f"{'objective':<20} {'positive':<18} {'distractor':<18}")
    for objective in objectives:
        hits = {"positive": 0, "distractor": 0}
        totals = {"positive": 0, "distractor": 0}
        for item in items:
            category = item["category"]
            expected = item["expected_video_id"]
            totals[category] += 1
            picked = best_video(
                embeddings, vector_ids, slices, item["query_vector_ids"], objective
            )
            # Distractor's expected_video_id is the video MISSING an event, so
            # ranking it first is the failure being measured.
            ok = picked == expected if category == "positive" else picked != expected
            hits[category] += int(ok)
        print(
            "%-20s %5.1f%% (%2d/%2d)     %5.1f%% (%2d/%2d)"
            % (
                objective,
                hits["positive"] / max(1, totals["positive"]) * 100,
                hits["positive"],
                totals["positive"],
                hits["distractor"] / max(1, totals["distractor"]) * 100,
                hits["distractor"],
                totals["distractor"],
            )
        )
    print("\npositive: found the right video. distractor: rejected the incomplete one.")


if __name__ == "__main__":
    main()
