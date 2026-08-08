from __future__ import annotations

from backend.app.grid import Grid
from backend.app.landmark import LandmarkService
from .conftest import write_grid_data


def test_tower_bearing_covers_eight_directions_and_tower_foot(tmp_path):
    write_grid_data(tmp_path, ns_count=3, ew_count=3, tower=(1, 1))
    grid = Grid(tmp_path)
    landmark = LandmarkService(grid, tmp_path)

    cases = {
        (1, 0): "南",
        (1, 2): "北",
        (0, 1): "西",
        (2, 1): "東",
        (0, 0): "南西",
        (2, 0): "南東",
        (0, 2): "北西",
        (2, 2): "北東",
        (1, 1): "南",
    }

    for (ns_index, ew_index), expected in cases.items():
        assert landmark.tower_bearing_indices(ns_index, ew_index) == expected


def test_tower_visible_uses_visible_json(tmp_path):
    visible = [
        [False, True],
        [False, False],
    ]
    write_grid_data(tmp_path, ns_count=2, ew_count=2, tower=(1, 1), visible=visible)
    grid = Grid(tmp_path)
    landmark = LandmarkService(grid, tmp_path)

    assert landmark.tower_visible({"ns": "ns-01", "ew": "ew-00"})
    assert not landmark.tower_visible({"ns": "ns-00", "ew": "ew-00"})
