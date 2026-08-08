from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .grid import DATA_DIR, Grid
from .models import Bearing

DIRECTIONS: list[Bearing] = ["北", "北東", "東", "南東", "南", "南西", "西", "北西"]


class Landmark:
    """方角を知るための目印。layer が小さいほど精度が高い。"""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.id = str(raw["id"])
        self.name = str(raw["name"])
        self.layer = int(raw["layer"])
        self.kind = str(raw.get("kind", "point"))
        self.x = float(raw.get("x", 0))     # 最も東の通りから西へ(m)
        self.y = float(raw.get("y", 0))     # 最も北の通りから南へ(m)
        self.min_distance = float(raw.get("min_distance", 0))


class LandmarkService:
    """交差点から、どの目印がどちらに見えるかを返す。

    方位は添字の符号ではなく **実距離から角度を出して** 8方位に丸める。
    符号だけで判定すると、烏丸通の1本隣に立っただけで 2.6km 先のタワーが
    「南西」になってしまう（実際には真南に見えている）。
    """

    def __init__(self, grid: Grid, data_dir: Path | str = DATA_DIR) -> None:
        self.grid = grid
        self.data_dir = Path(data_dir)
        self._visible = self._read_visible()
        self.landmarks = sorted(
            (Landmark(raw) for raw in grid.landmarks), key=lambda item: item.layer
        )
        # 行列で持つのは点の目印だけ。稜線は交差点ごとの辞書で持つ
        for key, matrix in self._visible.items():
            if isinstance(matrix, list):
                self.grid._validate_matrix(matrix, f"visible[{key}]")

    # ── 可視判定 ────────────────────────────────────────────

    def visible(self, landmark_id: str, ns_index: int, ew_index: int) -> bool:
        self.grid.validate_indices(ns_index, ew_index)
        matrix = self._visible.get(landmark_id)
        if matrix is None:
            return False
        return bool(matrix[ew_index][ns_index])

    def skyline(self, ns_index: int, ew_index: int) -> dict[str, int]:
        """その交差点から見える山の稜線。{方角: 何m歩けば見えるか}"""
        self.grid.validate_indices(ns_index, ew_index)
        data = self._visible.get("skyline")
        if not isinstance(data, dict):
            return {}
        return data.get(f"{ns_index},{ew_index}", {})

    # ── 方位と距離 ──────────────────────────────────────────

    def bearing_and_distance(
        self,
        landmark: Landmark,
        ns_index: int,
        ew_index: int,
    ) -> tuple[Bearing | None, float]:
        here_x, here_y = self.grid.position(ns_index, ew_index)
        dx = landmark.x - here_x        # 西向き
        dy = landmark.y - here_y        # 南向き
        distance = math.hypot(dx, dy)
        if distance == 0:
            return None, 0.0
        angle = math.degrees(math.atan2(-dx, -dy)) % 360   # 北=0、東=90
        return DIRECTIONS[round(angle / 45) % 8], distance

    def best(self, ns_index: int, ew_index: int) -> dict[str, Any]:
        """その交差点で使える、いちばん精度の高い方角の手がかり。

        精度が高い順に4層。最後の「街区の形」はどこでも使えるので、
        必ず何かは返る（docs/SPEC.md 2.4）。
        """
        for landmark in self.landmarks:
            if landmark.kind == "point":
                if not self.visible(landmark.id, ns_index, ew_index):
                    continue
                bearing, distance = self.bearing_and_distance(landmark, ns_index, ew_index)
                # 近すぎると見上げる形になり、水平方向が読みにくい
                too_close = distance < landmark.min_distance
                return {
                    "kind": "point", "id": landmark.id, "name": landmark.name,
                    "layer": landmark.layer,
                    "bearing": None if too_close else bearing,
                    "distance": round(distance),
                }

            if landmark.kind == "skyline":
                seen = self.skyline(ns_index, ew_index)
                if not seen:
                    continue
                # いちばん近くで見える方角を選ぶ（0m = その場で見える）
                bearing, walk = min(seen.items(), key=lambda item: (item[1], item[0]))
                return {
                    "kind": "skyline", "id": landmark.id, "name": landmark.name,
                    "layer": landmark.layer, "bearing": bearing,
                    "walk": int(walk), "directions": dict(seen),
                }

            if landmark.kind == "block":
                block = self.grid.block
                return {
                    "kind": "block", "id": landmark.id, "name": landmark.name,
                    "layer": landmark.layer, "bearing": None,
                    "ns_spacing": int(block.get("ns_spacing", 0)),
                    "ew_spacing": int(block.get("ew_spacing", 0)),
                }
        return {"kind": "none", "layer": 99, "bearing": None}

    def _read_visible(self) -> dict[str, list[list[bool]]]:
        with (self.data_dir / "visible.json").open(encoding="utf-8") as file:
            data: dict[str, Any] = json.load(file)
        visible = data["visible"]
        # 単一の目印しか無かった頃の形（行列そのもの）にも一応対応する
        if isinstance(visible, list):
            return {"tower": visible}
        return visible
