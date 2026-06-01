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


def test_demo_media_is_served() -> None:
    with TestClient(app) as client:
        response = client.get("/media/keyframes/L21_V001/1")
    assert response.status_code == 200
    assert "svg" in response.headers["content-type"]
