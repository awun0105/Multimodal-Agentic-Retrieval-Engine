from pathlib import Path

import numpy as np
import yaml

from system1.scenes.deterministic import (
    SceneParams,
    ShotEvidence,
    group_scenes,
    scene_ids_for_shots,
)

CONFIG = yaml.safe_load((Path(__file__).parents[1] / "configs" / "worker.yaml").read_text())
PARAMS = SceneParams.from_config(CONFIG["scenes"])
FPS = 25


def unit(*values):
    v = np.array(values, dtype=float)
    return v / np.linalg.norm(v)


def shot(n, start, end, image, caption=None, ocr=()):
    return ShotEvidence(
        shot_id=f"V_SH{n:05d}",
        start_frame=int(start * FPS),
        end_frame=int(end * FPS),
        start_sec=start,
        end_sec=end,
        image_vector=image,
        caption_vector=caption,
        ocr_lines=frozenset(ocr),
    )


def assert_tiles(scenes, shots):
    assert sum(s.shot_count for s in scenes) == len(shots)
    position = 0
    for n, scene in enumerate(scenes):
        members = shots[position : position + scene.shot_count]
        assert scene.scene_id == f"V_SC{n:05d}"
        assert scene.start_shot_id == members[0].shot_id
        assert scene.end_shot_id == members[-1].shot_id
        assert scene.start_frame == members[0].start_frame
        assert scene.end_frame == members[-1].end_frame
        assert scene.start_sec == members[0].start_sec
        assert scene.end_sec == members[-1].end_sec
        position += scene.shot_count


def test_from_config_reads_worker_yaml():
    assert PARAMS == SceneParams(0.4, 0.3, 0.2, 0.2, 0.1, 0.55, 2.0, 2.0, 90.0)


def test_empty_shot_list():
    assert group_scenes("V", [], [], PARAMS) == []


def test_two_angles_of_one_situation_join():
    # Two camera angles of a woman weaving a basket, one ASR segment across the cut.
    shots = [
        shot(0, 0.0, 3.0, unit(1, 0.05, 0), unit(1, 0.1, 0)),
        shot(1, 3.0, 6.0, unit(1, 0, 0.05), unit(1, 0, 0.1)),
    ]
    scenes = group_scenes("V", shots, [(1.0, 5.0)], PARAMS)
    assert len(scenes) == 1 and scenes[0].shot_count == 2
    assert_tiles(scenes, shots)
    assert scene_ids_for_shots(scenes, shots) == {"V_SH00000": "V_SC00000", "V_SH00001": "V_SC00000"}


def test_silent_gap_and_visual_change_split():
    shots = [shot(0, 0.0, 5.0, unit(1, 0)), shot(1, 8.0, 13.0, unit(0, 1))]
    scenes = group_scenes("V", shots, [], PARAMS)
    assert [s.shot_count for s in scenes] == [1, 1]
    assert_tiles(scenes, shots)


def test_long_scene_splits_at_weakest_boundary():
    v, w = unit(1, 0), unit(0.9, np.sqrt(1 - 0.81))
    shots = [shot(i, 12.0 * i, 12.0 * (i + 1), v if i < 5 else w) for i in range(10)]
    asr = [(0.0, 120.0)]
    scenes = group_scenes("V", shots, asr, PARAMS)
    assert [s.start_shot_id for s in scenes] == ["V_SH00000", "V_SH00005"]
    assert all(s.end_sec - s.start_sec <= PARAMS.max_scene_sec for s in scenes)
    assert_tiles(scenes, shots)


def test_short_single_shot_merges_into_closer_neighbour():
    shots = [
        shot(0, 0.0, 10.0, unit(1, 0)),
        shot(1, 10.0, 11.0, unit(0.3, 1)),
        shot(2, 11.0, 21.0, unit(0, 1)),
    ]
    scenes = group_scenes("V", shots, [], PARAMS)
    assert [(s.start_shot_id, s.shot_count) for s in scenes] == [("V_SH00000", 1), ("V_SH00001", 2)]
    assert_tiles(scenes, shots)
    assert scene_ids_for_shots(scenes, shots)["V_SH00001"] == "V_SC00001"


def test_without_captions():
    shots = [shot(i, 3.0 * i, 3.0 * (i + 1), unit(1, 0.01 * i)) for i in range(4)]
    scenes = group_scenes("V", shots, [(0.0, 12.0)], PARAMS)
    assert len(scenes) == 1 and scenes[0].shot_count == 4
    assert_tiles(scenes, shots)
