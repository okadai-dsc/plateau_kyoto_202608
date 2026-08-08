from __future__ import annotations

import pytest

from backend.app.errors import RouteNotFound, SameLocation
from backend.app.grid import Grid
from backend.app.landmark import LandmarkService
from backend.app.router import RouteService
from .conftest import make_route_service, write_grid_data


def test_route_sample_generates_multiple_candidates_ordered_by_visibility(repo_root):
    grid = Grid(repo_root / "backend" / "app" / "data")
    landmark = LandmarkService(grid, repo_root / "backend" / "app" / "data")
    service = RouteService(grid, landmark)

    response = service.build_route_response(
        {"ns": "ns-05", "ew": "ew-11"},
        {"ns": "ns-02", "ew": "ew-07"},
    )

    assert response["from"] == {"ns": "ns-05", "ew": "ew-11"}
    assert response["to"] == {"ns": "ns-02", "ew": "ew-07"}
    assert response["start"]["tower_visible"] is True
    assert len(response["routes"]) == 2
    assert response["routes"][0]["id"] == "r1"
    assert response["routes"][0]["visible_ratio"] == 0.88
    assert response["routes"][1]["visible_ratio"] == 0.12
    assert response["routes"][0]["visible_ratio"] > response["routes"][1]["visible_ratio"]
    assert [step["direction"] for step in response["routes"][0]["steps"]] == ["上ル", "東入ル"]


def test_route_filters_candidates_that_cross_missing_intersections(repo_root):
    grid = Grid(repo_root / "backend" / "app" / "data")
    landmark = LandmarkService(grid, repo_root / "backend" / "app" / "data")
    service = RouteService(grid, landmark)

    response = service.build_route_response(
        {"ns": "ns-01", "ew": "ew-03"},
        {"ns": "ns-05", "ew": "ew-07"},
    )

    assert len(response["routes"]) == 1
    assert response["routes"][0]["steps"][0]["direction"] == "下ル"


def test_route_errors_when_no_direct_candidate_can_avoid_missing_intersections(repo_root):
    grid = Grid(repo_root / "backend" / "app" / "data")
    landmark = LandmarkService(grid, repo_root / "backend" / "app" / "data")
    service = RouteService(grid, landmark)

    with pytest.raises(RouteNotFound):
        service.build_route_response(
            {"ns": "ns-01", "ew": "ew-03"},
            {"ns": "ns-05", "ew": "ew-03"},
        )


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
