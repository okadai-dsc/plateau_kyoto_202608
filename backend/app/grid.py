from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .errors import InvalidStreetId
from .models import Axis, Intersection

DATA_DIR = Path(__file__).resolve().parent / "data"
STREET_ID_RE = re.compile(r"^(ns|ew)-(\d+)$")


class Grid:
    def __init__(self, data_dir: Path | str = DATA_DIR) -> None:
        self.data_dir = Path(data_dir)
        streets_data = self._read_json("streets.json")
        exists_data = self._read_json("exists.json")

        self._streets: dict[str, list[dict[str, Any]]] = {
            "ns": self._build_streets("ns", streets_data["ns"]),
            "ew": self._build_streets("ew", streets_data["ew"]),
        }
        self._exists: list[list[bool]] = exists_data["exists"]
        self._tower_indices = {
            "ns": int(streets_data["tower"]["ns"]),
            "ew": int(streets_data["tower"]["ew"]),
        }

        self._validate_streets()
        self._validate_matrix(self._exists, "exists")
        self.validate_indices(self._tower_indices["ns"], self._tower_indices["ew"])

    @property
    def ns_streets(self) -> list[dict[str, Any]]:
        return [street.copy() for street in self._streets["ns"]]

    @property
    def ew_streets(self) -> list[dict[str, Any]]:
        return [street.copy() for street in self._streets["ew"]]

    @property
    def exists_matrix(self) -> list[list[bool]]:
        return [row.copy() for row in self._exists]

    @property
    def tower_indices(self) -> tuple[int, int]:
        return self._tower_indices["ns"], self._tower_indices["ew"]

    def to_response(self) -> dict[str, Any]:
        return {
            "ns_streets": self.ns_streets,
            "ew_streets": self.ew_streets,
            "exists": self.exists_matrix,
            "tower": self.intersection_from_indices(*self.tower_indices),
        }

    def street_id(self, axis: Axis, index: int) -> str:
        self._validate_axis_index(axis, index)
        return f"{axis}-{index:02d}"

    def street_index(self, street_id: str, expected_axis: Axis | None = None) -> int:
        axis, index = self.parse_street_id(street_id)
        if expected_axis is not None and axis != expected_axis:
            raise InvalidStreetId(street_id)
        self._validate_axis_index(axis, index)
        return index

    def street_name(self, axis: Axis, index: int) -> str:
        self._validate_axis_index(axis, index)
        return self._streets[axis][index]["name"]

    def parse_street_id(self, street_id: str) -> tuple[Axis, int]:
        match = STREET_ID_RE.match(street_id)
        if not match:
            raise InvalidStreetId(street_id)
        axis = match.group(1)
        index = int(match.group(2))
        if axis not in ("ns", "ew"):
            raise InvalidStreetId(street_id)
        return axis, index

    def intersection_indices(self, intersection: Intersection | dict[str, str]) -> tuple[int, int]:
        ns_id = intersection.ns if isinstance(intersection, Intersection) else intersection["ns"]
        ew_id = intersection.ew if isinstance(intersection, Intersection) else intersection["ew"]
        ns_index = self.street_index(ns_id, "ns")
        ew_index = self.street_index(ew_id, "ew")
        return ns_index, ew_index

    def intersection_from_indices(self, ns_index: int, ew_index: int) -> dict[str, str]:
        self.validate_indices(ns_index, ew_index)
        return {"ns": self.street_id("ns", ns_index), "ew": self.street_id("ew", ew_index)}

    def validate_indices(self, ns_index: int, ew_index: int) -> None:
        self._validate_axis_index("ns", ns_index)
        self._validate_axis_index("ew", ew_index)

    def exists(self, intersection: Intersection | dict[str, str]) -> bool:
        ns_index, ew_index = self.intersection_indices(intersection)
        return self.exists_indices(ns_index, ew_index)

    def exists_indices(self, ns_index: int, ew_index: int) -> bool:
        self.validate_indices(ns_index, ew_index)
        return bool(self._exists[ew_index][ns_index])

    def _read_json(self, name: str) -> Any:
        with (self.data_dir / name).open(encoding="utf-8") as file:
            return json.load(file)

    def _build_streets(self, axis: Axis, raw_streets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "id": f"{axis}-{int(street['index']):02d}",
                "axis": axis,
                "index": int(street["index"]),
                "name": str(street["name"]),
            }
            for street in sorted(raw_streets, key=lambda item: int(item["index"]))
        ]

    def _validate_streets(self) -> None:
        for axis in ("ns", "ew"):
            indexes = [street["index"] for street in self._streets[axis]]
            expected = list(range(len(indexes)))
            if indexes != expected:
                raise ValueError(f"{axis} street indexes must be contiguous from 0")

    def _validate_matrix(self, matrix: list[list[bool]], name: str) -> None:
        expected_rows = len(self._streets["ew"])
        expected_cols = len(self._streets["ns"])
        if len(matrix) != expected_rows:
            raise ValueError(f"{name} must have {expected_rows} ew rows")
        for row in matrix:
            if len(row) != expected_cols:
                raise ValueError(f"{name} rows must have {expected_cols} ns columns")

    def _validate_axis_index(self, axis: Axis, index: int) -> None:
        if axis not in ("ns", "ew"):
            raise InvalidStreetId(f"{axis}-{index:02d}")
        if index < 0 or index >= len(self._streets[axis]):
            raise InvalidStreetId(f"{axis}-{index:02d}")
