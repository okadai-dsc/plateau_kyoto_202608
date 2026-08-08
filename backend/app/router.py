from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import IntersectionNotFound, RouteNotFound, SameLocation
from .grid import Grid
from .instruction import build_move_instruction, build_start_hint
from .landmark import LandmarkService
from .models import Axis, Direction, Intersection


@dataclass(frozen=True)
class Movement:
    axis: Axis
    direction: Direction
    count: int


class RouteService:
    """現在地と目的地から「方角 × 本数」を出す。

    経路は指定しない。碁盤の目では **上ル/下ル と 東入ル/西入ル を
    どの順に消化しても着く** ので、覚えるのは方角2つと本数2つで足りる。
    ここが本企画の核であり、順番まで決めると普通のナビになる（docs/SPEC.md 3.5）。
    """

    def __init__(self, grid: Grid, landmark: LandmarkService) -> None:
        self.grid = grid
        self.landmark = landmark

    def build_route_response(
        self,
        from_intersection: Intersection | dict[str, str],
        to_intersection: Intersection | dict[str, str],
    ) -> dict[str, Any]:
        from_ns, from_ew = self.grid.intersection_indices(from_intersection)
        to_ns, to_ew = self.grid.intersection_indices(to_intersection)

        if (from_ns, from_ew) == (to_ns, to_ew):
            raise SameLocation()
        if not self.grid.exists_indices(from_ns, from_ew):
            raise IntersectionNotFound()
        if not self.grid.exists_indices(to_ns, to_ew):
            raise IntersectionNotFound()

        # 順番は自由だが、少なくとも1通りは通り抜けられる必要がある
        if not self._walkable(from_ns, from_ew, to_ns, to_ew):
            raise RouteNotFound()

        start_visible = self.landmark.tower_visible_indices(from_ns, from_ew)
        start_bearing = self.landmark.tower_bearing_indices(from_ns, from_ew)

        return {
            "from": self.grid.intersection_from_indices(from_ns, from_ew),
            "to": self.grid.intersection_from_indices(to_ns, to_ew),
            "start": {
                "tower_visible": start_visible,
                "tower_bearing": start_bearing,
                "hint": build_start_hint(start_visible, start_bearing),
            },
            "moves": self._moves(from_ns, from_ew, to_ns, to_ew),
        }

    # ── 方角と本数 ──────────────────────────────────────────

    def _moves(
        self,
        from_ns: int,
        from_ew: int,
        to_ns: int,
        to_ew: int,
    ) -> list[dict[str, Any]]:
        movements = [
            self._movement_for_axis("ew", from_ew, to_ew),
            self._movement_for_axis("ns", from_ns, to_ns),
        ]

        moves = []
        for movement in movements:
            if movement is None:
                continue
            index = to_ew if movement.axis == "ew" else to_ns
            name = self.grid.street_name(movement.axis, index)
            moves.append(
                {
                    "direction": movement.direction,
                    "count": movement.count,
                    "to_street": self.grid.street_id(movement.axis, index),
                    "to_street_name": name,
                    "instruction": build_move_instruction(
                        movement.direction, movement.count, name
                    ),
                }
            )
        return moves

    def _movement_for_axis(self, axis: Axis, current: int, target: int) -> Movement | None:
        """本数は通り順（数え歌の並び）での差。

        実際に横切る本数は通る道によって変わる。届いていない小路があるためで、
        順番を決めない以上ひとつには定まらない。
        そこで本数は目安として出し、**通り名を正とする**。
        """
        diff = target - current
        if diff == 0:
            return None
        if axis == "ew":
            direction: Direction = "下ル" if diff > 0 else "上ル"
        else:
            direction = "西入ル" if diff > 0 else "東入ル"
        return Movement(axis=axis, direction=direction, count=abs(diff))

    # ── 通れるかどうか ──────────────────────────────────────

    def _walkable(self, from_ns: int, from_ew: int, to_ns: int, to_ew: int) -> bool:
        """縦から先・横から先のどちらかで通り抜けられるか。

        曲がる地点に交差点が無ければ、その順序では曲がれない。
        途中に交差点が無いのは構わない（その通り自体は歩ける）。
        """
        turn_points = [
            (from_ns, to_ew),   # 先に 上ル/下ル してから 東入ル/西入ル
            (to_ns, from_ew),   # 先に 東入ル/西入ル してから 上ル/下ル
        ]
        return any(self.grid.exists_indices(ns, ew) for ns, ew in turn_points)
