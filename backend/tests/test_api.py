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


def test_resolve_destination_returns_nearest_intersection():
    client = TestClient(app)
    response = client.post(
        "/api/resolve-destination",
        json={"url": "https://www.google.com/maps/@35.003678,135.759637,17z"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["destination"] == {"ns": "ns-12", "ew": "ew-12"}
    assert data["label"] == "烏丸通 × 四条通 付近"


def test_scene_is_served_as_svg():
    """線画は SVG として返る（docs/SPEC.md 2.6）。"""
    client = TestClient(app)
    grid = client.get("/api/grid").json()

    # 線画がある交差点を1つ探す
    from backend.app.scene import SceneLibrary
    library = SceneLibrary()
    assert library.count > 0, "線画が1件も無い。tools/gen_scenes.py を実行すること"

    ns_index, ew_index = next(
        (int(v) for v in key.split(","))
        for key in [next(iter(library._index))]
    ), None
    key = next(iter(library._index))
    ns_index, ew_index = (int(v) for v in key.split(","))

    response = client.get(f"/api/scene/{ns_index}/{ew_index}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.text.startswith("<svg")
    assert len(grid["ns_streets"]) > ns_index


def test_scene_is_absent_where_no_landmark_is_visible():
    """稜線や大きい通りが手がかりの交差点には線画が無い。文章だけで歩く。"""
    from backend.app.grid import Grid
    from backend.app.scene import SceneLibrary
    grid = Grid()
    library = SceneLibrary()

    missing = [
        (ns, ew)
        for ew in range(len(grid.ew_streets))
        for ns in range(len(grid.ns_streets))
        if grid.exists_indices(ns, ew) and library.info(ns, ew) is None
    ]
    assert missing, "全交差点に線画がある想定ではない"

    client = TestClient(app)
    ns_index, ew_index = missing[0]
    assert client.get(f"/api/scene/{ns_index}/{ew_index}").status_code == 404
