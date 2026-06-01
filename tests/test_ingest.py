from aic_retrieval.db import connect, init_db
from aic_retrieval.ingest import ingest_manifest
from aic_retrieval.search import search_frames


def test_ingest_manifest_indexes_frames_and_objects(tmp_path) -> None:
    database_path = tmp_path / "app.sqlite"
    init_db(database_path)
    manifest = {
        "videos": [
            {
                "video_id": "L99_V001",
                "path": "raw/videos/L99_V001.mp4",
                "fps": 25,
                "duration": 30,
                "width": 1920,
                "height": 1080,
            }
        ],
        "frames": [
            {
                "video_id": "L99_V001",
                "frame_id": 42,
                "timestamp": 1.68,
                "thumb_path": "processed/thumbs/L99_V001/42.jpg",
                "keyframe_path": "processed/keyframes/L99_V001/42.jpg",
                "caption": "A red bus stopping near a market",
                "objects": [{"name": "Bus", "score": 0.91, "box": [0.1, 0.2, 0.5, 0.7]}],
            }
        ],
    }

    with connect(database_path) as connection:
        stats = ingest_manifest(connection, manifest)
        results = search_frames(connection, "market", 10, ["Bus"])

    assert stats == {"videos": 1, "frames": 1, "objects": 1}
    assert results[0].video_id == "L99_V001"
    assert "Bus" in " ".join(results[0].evidence)
