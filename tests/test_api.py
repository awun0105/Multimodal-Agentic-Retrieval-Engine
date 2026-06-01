from fastapi.testclient import TestClient

from aic_retrieval.main import app


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_search_returns_demo_results() -> None:
    with TestClient(app) as client:
        response = client.post("/search", json={"query": "lantern city", "limit": 5})
    assert response.status_code == 200
    payload = response.json()
    assert payload["results"]
    assert payload["results"][0]["video_id"] == "L21_V001"


def test_search_supports_object_filter() -> None:
    with TestClient(app) as client:
        filters = client.get("/filters/objects")
        response = client.post(
            "/search",
            json={"query": "city", "limit": 5, "object_filters": ["Bicycle"]},
        )
    assert filters.status_code == 200
    assert "Bicycle" in filters.json()
    assert response.status_code == 200
    payload = response.json()
    assert payload["results"]
    assert all("Bicycle" in " ".join(result["evidence"]) for result in payload["results"])


def test_dataset_and_video_listing() -> None:
    with TestClient(app) as client:
        datasets = client.get("/datasets")
        videos = client.get("/videos")
        frames = client.get("/videos/L21_V001/frames")
    assert datasets.status_code == 200
    assert datasets.json()[0]["frame_count"] >= 1
    assert videos.status_code == 200
    assert any(video["video_id"] == "L21_V001" for video in videos.json())
    assert frames.status_code == 200
    assert frames.json()[0]["video_id"] == "L21_V001"


def test_query_session_tracks_progressive_clues() -> None:
    with TestClient(app) as client:
        session = client.post("/sessions", json={"title": "final query", "query_type": "tkis"})
        session_id = session.json()["id"]
        clue = client.post(f"/sessions/{session_id}/clues", json={"text": "A lantern appears"})
        detail = client.get(f"/sessions/{session_id}")
        sessions = client.get("/sessions")
    assert session.status_code == 200
    assert clue.status_code == 200
    assert clue.json()["order_index"] == 1
    assert detail.status_code == 200
    assert detail.json()["clues"][0]["text"] == "A lantern appears"
    assert sessions.status_code == 200
    assert any(item["id"] == session_id for item in sessions.json())


def test_candidate_rows_can_be_updated_for_export() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/candidates",
            json={"video_id": "L21_V001", "frame_id": 1, "timestamp": 0.04},
        )
        candidate_id = created.json()["id"]
        updated = client.patch(
            f"/candidates/{candidate_id}",
            json={"answer": "L21_V001,1", "rank": 1, "note": "best frame"},
        )
        exported = client.post("/export", json={})
    assert created.status_code == 200
    assert updated.status_code == 200
    assert updated.json()["rank"] == 1
    assert exported.status_code == 200
    assert any(row["answer"] == "L21_V001,1" for row in exported.json()["rows"])


def test_demo_media_is_served() -> None:
    with TestClient(app) as client:
        response = client.get("/media/keyframes/L21_V001/1")
    assert response.status_code == 200
    assert "svg" in response.headers["content-type"]


def test_missing_raw_video_returns_404() -> None:
    with TestClient(app) as client:
        response = client.get("/media/videos/L21_V001")
    assert response.status_code == 404
