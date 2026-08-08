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


def test_post_route_matches_mock_response(repo_root):
    """モックと同じ入力なら、同じレスポンスを返すこと。

    通り名や本数を直接書かない。実データに差し替えても、
    mock/route.json を再生成すればそのまま通る。
    """
    mock_route = json.loads((repo_root / "mock" / "route.json").read_text(encoding="utf-8"))

    client = TestClient(app)
    response = client.post(
        "/api/route",
        json={"from": mock_route["from"], "to": mock_route["to"]},
    )

    assert response.status_code == 200
    assert response.json() == mock_route


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
