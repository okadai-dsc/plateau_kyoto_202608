from __future__ import annotations

import json

from fastapi.testclient import TestClient

from backend.app.main import app


def test_get_grid_matches_mock(repo_root):
    client = TestClient(app)
    response = client.get("/api/grid")
    mock_grid = json.loads((repo_root / "mock" / "grid.json").read_text(encoding="utf-8"))

    assert response.status_code == 200
    assert response.json() == mock_grid


def test_post_route_matches_mock_response_shape(repo_root):
    client = TestClient(app)
    response = client.post(
        "/api/route",
        json={
            "from": {"ns": "ns-05", "ew": "ew-11"},
            "to": {"ns": "ns-02", "ew": "ew-07"},
        },
    )
    mock_route = json.loads((repo_root / "mock" / "route.json").read_text(encoding="utf-8"))

    assert response.status_code == 200
    body = response.json()
    assert body.keys() == mock_route.keys()
    assert body["start"].keys() == mock_route["start"].keys()
    assert body["routes"][0].keys() == mock_route["routes"][0].keys()
    assert body["routes"][0]["steps"][0].keys() == mock_route["routes"][0]["steps"][0].keys()
    assert body["routes"][0]["visible_ratio"] == 0.88
    assert body["routes"][1]["visible_ratio"] == 0.12


def test_post_route_returns_contract_error_shape():
    client = TestClient(app)
    response = client.post(
        "/api/route",
        json={
            "from": {"ns": "ns-99", "ew": "ew-11"},
            "to": {"ns": "ns-02", "ew": "ew-07"},
        },
    )

    assert response.status_code == 400
    assert response.json().keys() == {"error", "message"}
