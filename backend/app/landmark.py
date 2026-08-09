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
        # peak なら標高(m)、point なら構造物の高さ(m)。仰角の計算に使う
        self.height = float(raw.get("height", 0))
        # kind="street" 用。これより遠いと車の流れを感じ取れないものとして捨てる
        self.max_distance = float(raw.get("max_distance", 600))
        # kind="street" 用。これより狭いと車がまとまって通らない（寺町通・三条通など）
        self.min_width = float(raw.get("min_width", 15))


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

    # ── 山 ──────────────────────────────────────────────────

    # 通りの軸（北/東/南/西）からこれだけ外れた山は、通りの突き当たりに来ない
    AXIS_TOLERANCE = 30.0
    # 幅がこれ以上の通りは空が開けるので、斜めの山も見える
    OPEN_WIDTH = 40.0
    OPEN_TOLERANCE = 60.0
    # 見通しがこれだけ続いていれば、手前の建物より山の方が高く見える
    MIN_CORRIDOR = 400.0

    def peak_visible(self, landmark: Landmark, ns_index: int, ew_index: int) -> bool:
        """山が見えるか。

        PLATEAU の可視マスクがあればそれを使う。無ければ **通りの見通し**から判定する。
        山は仰角4〜5度あるのに対し、京都は高さ規制(15m/31m)が効いていて
        500m先のビルでも3.5度以下。**通りに沿って数百m抜けていれば山は上に出る**。

        逆に言うと、通りの軸から外れた方角の山は突き当たりに来ないので見えない
        （比叡山は北東なのでどの通りの正面にも来ない）。
        幅の広い通りに立っているときだけ、空が開けるぶん斜めも許す。
        """
        if landmark.id in self._visible:
            return self.visible(landmark.id, ns_index, ew_index)

        bearing_angle = self._angle_to(landmark, ns_index, ew_index)
        if bearing_angle is None:
            return False

        widest = max(
            float(self.grid.ns_streets[ns_index]["width"]),
            float(self.grid.ew_streets[ew_index]["width"]),
        )
        tolerance = self.OPEN_TOLERANCE if widest >= self.OPEN_WIDTH else self.AXIS_TOLERANCE

        for axis_angle, has_corridor in (
            (0.0, lambda: self._corridor_ns(ns_index, ew_index, -1)),     # 北
            (90.0, lambda: self._corridor_ew(ns_index, ew_index, -1)),    # 東
            (180.0, lambda: self._corridor_ns(ns_index, ew_index, 1)),    # 南
            (270.0, lambda: self._corridor_ew(ns_index, ew_index, 1)),    # 西
        ):
            gap = abs((bearing_angle - axis_angle + 180) % 360 - 180)
            if gap <= tolerance and has_corridor():
                return True
        return False

    def _angle_to(self, landmark: Landmark, ns_index: int, ew_index: int) -> float | None:
        here_x, here_y = self.grid.position(ns_index, ew_index)
        dx = landmark.x - here_x
        dy = landmark.y - here_y
        if dx == 0 and dy == 0:
            return None
        return math.degrees(math.atan2(-dx, -dy)) % 360

    def _corridor_ns(self, ns_index: int, ew_index: int, step: int) -> bool:
        """南北の通りが、その向きに MIN_CORRIDOR 以上まっすぐ抜けているか。"""
        streets = self.grid.ew_streets
        start = float(streets[ew_index]["pos"])
        index = ew_index
        while 0 <= index + step < len(streets):
            index += step
            if streets[index]["major"] and not self.grid.exists_indices(ns_index, index):
                break
            if abs(float(streets[index]["pos"]) - start) >= self.MIN_CORRIDOR:
                return True
        return False

    def _corridor_ew(self, ns_index: int, ew_index: int, step: int) -> bool:
        """東西の通りが、その向きに MIN_CORRIDOR 以上まっすぐ抜けているか。"""
        streets = self.grid.ns_streets
        start = float(streets[ns_index]["pos"])
        index = ns_index
        while 0 <= index + step < len(streets):
            index += step
            if streets[index]["major"] and not self.grid.exists_indices(index, ew_index):
                break
            if abs(float(streets[index]["pos"]) - start) >= self.MIN_CORRIDOR:
                return True
        return False

    # ── 大きい通り ──────────────────────────────────────────

    def nearest_major_street(
        self,
        ns_index: int,
        ew_index: int,
        max_distance: float = 600.0,
        min_width: float = 15.0,
    ) -> dict[str, Any] | None:
        """その交差点から見て、車がよく通る大通りがどちらにあるか。

        通り名の標識を読ませるのでも、そこまで歩かせるのでもない。
        **立った場所から「あっちは車がよく通ってるな」と分かる**ことを狙う。
        突き当たりを横切る車、空の開け方、車の音のどれかで気づける。

        選ぶ基準は `major` ではなく **幅**。`major` は「通り抜ける主要な通り」の
        意味で、寺町通(8m)や三条通(8m)のように車がほとんど通らないものも含む。

        タワーや山と違って **建物の遮蔽を計算しなくてよい**。通りに沿った視線は
        通りそのものが視線経路なので、建物は遮らないため（docs/SPEC.md 2.4）。
        """
        self.grid.validate_indices(ns_index, ew_index)
        ns_streets = self.grid.ns_streets
        ew_streets = self.grid.ew_streets
        here_x = float(ns_streets[ns_index]["pos"])   # 川端通から西へ
        here_y = float(ew_streets[ew_index]["pos"])   # 今出川通から南へ

        candidates: list[tuple[float, int, str, str]] = []

        # 今いる南北の通りを south/north に見通す → 車の通る東西の通りに気づく
        for index, street in enumerate(ew_streets):
            if index == ew_index or street["width"] < min_width:
                continue
            if not self._clear_along_ns(ns_index, ew_index, index):
                continue
            delta = float(street["pos"]) - here_y
            candidates.append(
                (abs(delta), -int(street["width"]), "南" if delta > 0 else "北", street["name"])
            )

        # 今いる東西の通りを east/west に見通す → 車の通る南北の通りに気づく
        for index, street in enumerate(ns_streets):
            if index == ns_index or street["width"] < min_width:
                continue
            if not self._clear_along_ew(ew_index, ns_index, index):
                continue
            delta = float(street["pos"]) - here_x
            candidates.append(
                (abs(delta), -int(street["width"]), "西" if delta > 0 else "東", street["name"])
            )

        reachable = [item for item in candidates if item[0] <= max_distance]
        if not reachable:
            return None
        # 近い順。同じ距離なら広い方が気づきやすいので優先する
        distance, _, bearing, name = min(reachable)
        return {"name": name, "bearing": bearing, "distance": round(distance)}

    def _clear_along_ns(self, ns_index: int, from_ew: int, to_ew: int) -> bool:
        """南北の通り ns_index を、from_ew から to_ew まで見通せるか。

        検査するのは **大きい東西の通りとの交点だけ**。交点が無いことは
        「細い方がそこまで届いていない」を意味するだけで、見通す側が分断されて
        いるとは限らない。大通りは必ず通り抜けているので、そこが欠けていれば
        見通す側が本当に切れている（御所・二条城など）と判定できる。
        """
        low, high = sorted((from_ew, to_ew))
        streets = self.grid.ew_streets
        return all(
            self.grid.exists_indices(ns_index, i)
            for i in range(low, high + 1)
            if streets[i]["major"] or i == to_ew
        )

    def _clear_along_ew(self, ew_index: int, from_ns: int, to_ns: int) -> bool:
        """東西の通り ew_index を、from_ns から to_ns まで見通せるか。"""
        low, high = sorted((from_ns, to_ns))
        streets = self.grid.ns_streets
        return all(
            self.grid.exists_indices(i, ew_index)
            for i in range(low, high + 1)
            if streets[i]["major"] or i == to_ns
        )

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

    EYE_HEIGHT = 1.5

    def elevation_angle(self, landmark: Landmark, distance: float) -> float | None:
        """目印の見かけの高さ（仰角・度）。

        山は 4〜5度しかないのに角幅は 10〜36度ある。**低くて広い**ので、
        画面に描くときは縦を誇張しないと平らな線にしかならない（docs/SPEC.md 2.6）。

        peak は標高なので地盤高を引く。point（京都タワー）は構造物の高さなので引かない。
        """
        if not landmark.height or distance <= 0:
            return None
        base = self.grid.ground_height if landmark.kind == "peak" else 0.0
        rise = landmark.height - base - self.EYE_HEIGHT
        if rise <= 0:
            return None
        return round(math.degrees(math.atan(rise / distance)), 1)

    def best(self, ns_index: int, ew_index: int) -> dict[str, Any]:
        """その交差点で使える、いちばん精度の高い方角の手がかり。

        精度が高い順に4層。最後の「大きい通り」は遮蔽の計算が要らないので
        どこでも使え、ほぼ必ず何かは返る（docs/SPEC.md 2.4）。
        """
        for landmark in self.landmarks:
            if landmark.kind in ("point", "peak"):
                if landmark.kind == "peak":
                    if not self.peak_visible(landmark, ns_index, ew_index):
                        continue
                elif not self.visible(landmark.id, ns_index, ew_index):
                    continue
                bearing, distance = self.bearing_and_distance(landmark, ns_index, ew_index)
                # 近すぎると見上げる形になり、水平方向が読みにくい
                too_close = distance < landmark.min_distance
                azimuth = self._angle_to(landmark, ns_index, ew_index)
                return {
                    "kind": landmark.kind, "id": landmark.id, "name": landmark.name,
                    "layer": landmark.layer,
                    "bearing": None if too_close else bearing,
                    "distance": round(distance),
                    # 8方位に丸める前の正確な方位。図に置くときはこちらを使う
                    "azimuth": None if azimuth is None else round(azimuth, 1),
                    "elevation": self.elevation_angle(landmark, distance),
                    "height": landmark.height or None,
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

            if landmark.kind == "street":
                found = self.nearest_major_street(
                    ns_index, ew_index, landmark.max_distance, landmark.min_width
                )
                if found is None:
                    continue
                return {
                    "kind": "street", "id": landmark.id, "name": found["name"],
                    "layer": landmark.layer, "bearing": found["bearing"],
                    "distance": found["distance"],
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
