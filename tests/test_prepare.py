import json

from aic_retrieval.db import connect
from aic_retrieval.prepare import build_manifest, prepare_dataset
from aic_retrieval.search import search_frames


def test_build_manifest_from_dataset_folders(tmp_path) -> None:
    data_root = tmp_path / "data"
    video_path = data_root / "raw" / "videos" / "L21_V001.mp4"
    keyframe_path = data_root / "processed" / "keyframes" / "L21_V001" / "001.jpg"
    object_path = data_root / "objects" / "L21_V001" / "001.json"
    video_path.parent.mkdir(parents=True)
    keyframe_path.parent.mkdir(parents=True)
    object_path.parent.mkdir(parents=True)
    video_path.write_bytes(b"")
    keyframe_path.write_bytes(b"image")
    object_path.write_text(
        json.dumps(
            {
                "detection_scores": ["0.79", "0.1"],
                "detection_class_entities": ["Lantern", "Ignored"],
                "detection_boxes": [[[0.1, 0.2, 0.3, 0.4]], []],
            }
        ),
        encoding="utf-8",
    )

    manifest = build_manifest(data_root, fps=25.0, object_score_min=0.2)

    assert manifest["videos"][0]["video_id"] == "L21_V001"
    assert manifest["frames"][0]["frame_id"] == 1
    assert manifest["frames"][0]["thumb_path"] == "processed/keyframes/L21_V001/001.jpg"
    assert manifest["frames"][0]["objects"][0]["name"] == "Lantern"
    assert len(manifest["frames"][0]["objects"]) == 1


def test_prepare_dataset_writes_manifest_and_database(tmp_path) -> None:
    data_root = tmp_path / "data"
    keyframe_path = data_root / "keyframes" / "L05_V010" / "250.jpg"
    object_path = data_root / "objects" / "L05_V010" / "250.json"
    keyframe_path.parent.mkdir(parents=True)
    object_path.parent.mkdir(parents=True)
    keyframe_path.write_bytes(b"image")
    object_path.write_text(
        json.dumps(
            {
                "detection_scores": ["0.91"],
                "detection_class_entities": ["Bicycle"],
                "detection_boxes": [[]],
            }
        ),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    database_path = tmp_path / "app.sqlite"

    stats = prepare_dataset(data_root, manifest_path, database_path)

    assert stats == {"videos": 1, "frames": 1, "objects": 1}
    assert manifest_path.exists()
    with connect(database_path) as connection:
        results = search_frames(connection, "Bicycle", 5)
    assert results[0].video_id == "L05_V010"
