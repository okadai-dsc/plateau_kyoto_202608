from __future__ import annotations

import pytest

from backend.app.errors import RouteNotFound, SameLocation
from backend.app.grid import Grid
from backend.app.landmark import LandmarkService
from backend.app.router import RouteService
from .conftest import make_route_service, write_grid_data


def test_route_candidates_are_ordered_by_visibility(tmp_path):
    """タワーが見える経路が優先されること。

    実データに依存しないよう、可視性を仕込んだ小さなグリッドで検証する。
    ns-01 の縦一列だけタワーが見える。
    """
    visible = [
        [False, True, False, False],
        [False, True, False, False],
        [False, True, False, False],
        [False, True, False, False],
    ]
    write_grid_data(tmp_path, ns_count=4, ew_count=4, tower=(1, 3), visible=visible)
    service = make_route_service(tmp_path)

    response = service.build_route_response(
        {"ns": "ns-01", "ew": "ew-03"},
        {"ns": "ns-03", "ew": "ew-00"},
    )

    assert response["from"] == {"ns": "ns-01", "ew": "ew-03"}
    assert response["to"] == {"ns": "ns-03", "ew": "ew-00"}
    assert response["start"]["tower_visible"] is True
    assert len(response["routes"]) == 2
    assert response["routes"][0]["id"] == "r1"
    # 見える縦の通りを先に進む経路が上に来る
    assert response["routes"][0]["visible_ratio"] > response["routes"][1]["visible_ratio"]
    assert [step["direction"] for step in response["routes"][0]["steps"]] == ["上ル", "西入ル"]


def test_route_rejects_candidates_whose_turn_point_is_missing(tmp_path):
    """曲がる地点の交差点が無い候補は落とされること。"""
    exists = [[True] * 3 for _ in range(3)]
    exists[2][0] = False   # exists[ew][ns]。横から先に折れる候補の曲がり角
    write_grid_data(tmp_path, ns_count=3, ew_count=3, tower=(1, 2), exists=exists)
    service = make_route_service(tmp_path)

    response = service.build_route_response(
        {"ns": "ns-02", "ew": "ew-02"},
        {"ns": "ns-00", "ew": "ew-00"},
    )

    assert len(response["routes"]) == 1
    assert response["routes"][0]["steps"][0]["direction"] == "上ル"


def test_route_errors_when_every_turn_point_is_missing(tmp_path):
    """どちらの順序でも曲がれないときはエラーになること。"""
    exists = [[True] * 3 for _ in range(3)]
    exists[2][0] = False   # 横から先に折れる候補の曲がり角
    exists[0][2] = False   # 縦から先に折れる候補の曲がり角
    write_grid_data(tmp_path, ns_count=3, ew_count=3, tower=(1, 2), exists=exists)
    service = make_route_service(tmp_path)

    with pytest.raises(RouteNotFound):
        service.build_route_response(
            {"ns": "ns-02", "ew": "ew-02"},
            {"ns": "ns-00", "ew": "ew-00"},
        )


def test_missing_intersection_does_not_block_passing_through(tmp_path):
    """交差点が無い場所は通行を妨げず、横切る通りの本数だけが減ること。

    河原町通を四条から三条へ上がるとき、錦小路通は河原町通まで届いていないが
    河原町通は普通に歩ける ── という実際の京都の事情に対応する。
    """
    exists = [[True] * 3 for _ in range(4)]
    exists[1][2] = False   # 途中の交差点だけを落とす（終点ではない）
    write_grid_data(tmp_path, ns_count=3, ew_count=4, tower=(1, 3), exists=exists)
    service = make_route_service(tmp_path)

    response = service.build_route_response(
        {"ns": "ns-02", "ew": "ew-03"},
        {"ns": "ns-02", "ew": "ew-00"},
    )

    assert len(response["routes"]) == 1
    step = response["routes"][0]["steps"][0]
    assert step["direction"] == "上ル"
    # 添字の差は 3 だが、実在する交差点は 2 本ぶんしかない
    assert step["count"] == 2
    assert "2本上ル" in step["instruction"]


def test_route_does_not_depend_on_default_grid_size(tmp_path):
    visible = [
        [True, True, True],
        [False, True, False],
        [False, True, False],
    ]
    write_grid_data(tmp_path, ns_count=3, ew_count=3, tower=(1, 1), visible=visible)
    service = make_route_service(tmp_path)

    response = service.build_route_response(
        {"ns": "ns-02", "ew": "ew-02"},
        {"ns": "ns-00", "ew": "ew-00"},
    )

    assert len(response["routes"]) == 2
    assert response["routes"][0]["steps"][0]["count"] == 2
    assert {step["to_street"] for step in response["routes"][0]["steps"]} == {"ns-00", "ew-00"}


def test_same_location_is_rejected(repo_root):
    grid = Grid(repo_root / "backend" / "app" / "data")
    landmark = LandmarkService(grid, repo_root / "backend" / "app" / "data")
    service = RouteService(grid, landmark)

    with pytest.raises(SameLocation):
        service.build_route_response(
            {"ns": "ns-05", "ew": "ew-11"},
            {"ns": "ns-05", "ew": "ew-11"},
        )
