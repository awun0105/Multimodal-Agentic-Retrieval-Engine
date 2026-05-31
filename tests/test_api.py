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
