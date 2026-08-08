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
    """id と添字の相互変換、実在判定。

    通り名や特定の交差点を直接書かない。実データに差し替えても通るよう、
    期待値は読み込んだデータ自身から導く。
    """
    grid = Grid(repo_root / "backend" / "app" / "data")

    assert grid.street_index("ns-05", "ns") == 5
    assert grid.street_id("ns", 2) == "ns-02"

    for axis, streets in (("ns", grid.ns_streets), ("ew", grid.ew_streets)):
        for street in streets:
            assert grid.street_id(axis, street["index"]) == street["id"]
            assert grid.street_index(street["id"], axis) == street["index"]
            assert grid.street_name(axis, street["index"]) == street["name"]

    # exists マスクと exists() の判定が一致すること
    matrix = grid.exists_matrix
    for ew_street in grid.ew_streets:
        for ns_street in grid.ns_streets:
            expected = matrix[ew_street["index"]][ns_street["index"]]
            assert grid.exists({"ns": ns_street["id"], "ew": ew_street["id"]}) is expected

    # 実データには「存在する交差点」と「存在しない交差点」の両方が含まれる
    flat = [cell for row in matrix for cell in row]
    assert any(flat) and not all(flat)


def test_invalid_street_id_is_rejected(repo_root):
    grid = Grid(repo_root / "backend" / "app" / "data")

    with pytest.raises(InvalidStreetId):
        grid.street_index("ns-99", "ns")

    with pytest.raises(InvalidStreetId):
        grid.street_index("ew-01", "ns")
