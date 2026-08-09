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
    major_ns: list[int] | None = None,
    major_ew: list[int] | None = None,
    landmarks: list[dict] | None = None,
) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    # pos は通り同士の相対距離(m)。方位の計算に使う（docs/API.md 2.1）
    step = 120
    major_ns_set = set(major_ns or [])
    major_ew_set = set(major_ew or [])
    streets = {
        # 大通りは車が通る幅にする。L4 の手がかりは major ではなく width で選ぶため
        "ns": [
            {"index": i, "name": f"N{i}通", "pos": i * step,
             "width": 22 if i in major_ns_set else 8, "major": i in major_ns_set}
            for i in range(ns_count)
        ],
        "ew": [
            {"index": i, "name": f"E{i}通", "pos": i * step,
             "width": 22 if i in major_ew_set else 8, "major": i in major_ew_set}
            for i in range(ew_count)
        ],
        "tower": {"ns": tower[0], "ew": tower[1]},
        "landmarks": landmarks if landmarks is not None else [
            {
                "id": "tower",
                "name": "京都タワー",
                "layer": 1,
                "x": tower[0] * step,
                "y": tower[1] * step,
                "min_distance": 0,
            }
        ],
    }
    exists_matrix = exists or [[True for _ in range(ns_count)] for _ in range(ew_count)]
    # 既定では全交差点から目印が見えることにする（方位の検証をしやすくするため）
    visible_matrix = visible or [[True for _ in range(ns_count)] for _ in range(ew_count)]

    (data_dir / "streets.json").write_text(
        json.dumps(streets, ensure_ascii=False),
        encoding="utf-8",
    )
    (data_dir / "exists.json").write_text(
        json.dumps({"exists": exists_matrix}, ensure_ascii=False),
        encoding="utf-8",
    )
    (data_dir / "visible.json").write_text(
        json.dumps({"visible": {"tower": visible_matrix}}, ensure_ascii=False),
        encoding="utf-8",
    )


def make_route_service(data_dir: Path) -> RouteService:
    grid = Grid(data_dir)
    landmark = LandmarkService(grid, data_dir)
    return RouteService(grid, landmark)
