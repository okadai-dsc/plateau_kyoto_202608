from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .grid import DATA_DIR, Grid
from .models import Bearing, Intersection


class LandmarkService:
    def __init__(self, grid: Grid, data_dir: Path | str = DATA_DIR) -> None:
        self.grid = grid
        self.data_dir = Path(data_dir)
        self._visible: list[list[bool]] = self._read_visible()
        self.grid._validate_matrix(self._visible, "visible")

    def tower_visible(self, intersection: Intersection | dict[str, str]) -> bool:
        ns_index, ew_index = self.grid.intersection_indices(intersection)
        return self.tower_visible_indices(ns_index, ew_index)

    def tower_visible_indices(self, ns_index: int, ew_index: int) -> bool:
        self.grid.validate_indices(ns_index, ew_index)
        return bool(self._visible[ew_index][ns_index])

    def tower_bearing(self, intersection: Intersection | dict[str, str]) -> Bearing:
        ns_index, ew_index = self.grid.intersection_indices(intersection)
        return self.tower_bearing_indices(ns_index, ew_index)

    def tower_bearing_indices(self, ns_index: int, ew_index: int) -> Bearing:
        tower_ns, tower_ew = self.grid.tower_indices
        ns_delta = tower_ns - ns_index
        ew_delta = tower_ew - ew_index

        vertical = ""
        horizontal = ""
        if ew_delta < 0:
            vertical = "北"
        elif ew_delta > 0:
            vertical = "南"

        if ns_delta < 0:
            horizontal = "東"
        elif ns_delta > 0:
            horizontal = "西"

        if vertical or horizontal:
            return f"{vertical}{horizontal}"  # type: ignore[return-value]

        # API.md の Bearing 型に合わせるため、足元では南を代表方位として返す。
        return "南"

    def _read_visible(self) -> list[list[bool]]:
        with (self.data_dir / "visible.json").open(encoding="utf-8") as file:
            data: dict[str, Any] = json.load(file)
        return data["visible"]
