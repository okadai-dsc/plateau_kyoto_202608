from __future__ import annotations

import json

import pytest

from backend.app.errors import InvalidStreetId
from backend.app.grid import Grid


def test_grid_response_matches_mock_shape_and_data(repo_root):
    grid = Grid(repo_root / "backend" / "app" / "data")
    mock_grid = json.loads((repo_root / "mock" / "grid.json").read_text(encoding="utf-8"))

    assert grid.to_response() == mock_grid


def test_street_id_index_conversion_and_exists_mask(repo_root):
    grid = Grid(repo_root / "backend" / "app" / "data")

    assert grid.street_index("ns-05", "ns") == 5
    assert grid.street_index("ew-15", "ew") == 15
    assert grid.street_id("ns", 2) == "ns-02"
    assert grid.street_name("ew", 7) == "8通"
    assert grid.exists({"ns": "ns-05", "ew": "ew-11"})
    assert not grid.exists({"ns": "ns-10", "ew": "ew-00"})


def test_invalid_street_id_is_rejected(repo_root):
    grid = Grid(repo_root / "backend" / "app" / "data")

    with pytest.raises(InvalidStreetId):
        grid.street_index("ns-99", "ns")

    with pytest.raises(InvalidStreetId):
        grid.street_index("ew-01", "ns")
