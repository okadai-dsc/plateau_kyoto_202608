from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from backend.app.grid import Grid
from backend.app.landmark import LandmarkService
from backend.app.router import RouteService


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def write_grid_data(
    data_dir: Path,
    ns_count: int,
    ew_count: int,
    tower: tuple[int, int],
    exists: list[list[bool]] | None = None,
    visible: list[list[bool]] | None = None,
) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    streets = {
        "ns": [{"index": index, "name": f"N{index}通"} for index in range(ns_count)],
        "ew": [{"index": index, "name": f"E{index}通"} for index in range(ew_count)],
        "tower": {"ns": tower[0], "ew": tower[1]},
    }
    exists_matrix = exists or [[True for _ in range(ns_count)] for _ in range(ew_count)]
    visible_matrix = visible or [[False for _ in range(ns_count)] for _ in range(ew_count)]

    (data_dir / "streets.json").write_text(
        json.dumps(streets, ensure_ascii=False),
        encoding="utf-8",
    )
    (data_dir / "exists.json").write_text(
        json.dumps({"exists": exists_matrix}, ensure_ascii=False),
        encoding="utf-8",
    )
    (data_dir / "visible.json").write_text(
        json.dumps({"visible": visible_matrix}, ensure_ascii=False),
        encoding="utf-8",
    )


def make_route_service(data_dir: Path) -> RouteService:
    grid = Grid(data_dir)
    landmark = LandmarkService(grid, data_dir)
    return RouteService(grid, landmark)
