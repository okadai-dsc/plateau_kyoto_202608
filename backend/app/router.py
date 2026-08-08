from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import IntersectionNotFound, RouteNotFound, SameLocation
from .grid import Grid
from .instruction import build_instruction, build_start_hint
from .landmark import LandmarkService
from .models import Axis, Direction, Intersection

VISIBLE_WEIGHT = 100.0
TURN_WEIGHT = 1.0


@dataclass(frozen=True)
class Movement:
    axis: Axis
    direction: Direction
    count: int


class RouteService:
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

        from_payload = self.grid.intersection_from_indices(from_ns, from_ew)
        to_payload = self.grid.intersection_from_indices(to_ns, to_ew)
        candidates = self._candidate_movements(from_ns, from_ew, to_ns, to_ew)

        routes = []
        for movements in candidates:
            route = self._build_candidate(from_ns, from_ew, movements)
            if route is not None:
                routes.append(route)

        if not routes:
            raise RouteNotFound()

        routes.sort(
            key=lambda route: (
                route["visible_ratio"] * VISIBLE_WEIGHT - route["turns"] * TURN_WEIGHT
            ),
            reverse=True,
        )
        for index, route in enumerate(routes, start=1):
            route["id"] = f"r{index}"

        start_visible = self.landmark.tower_visible_indices(from_ns, from_ew)
        start_bearing = self.landmark.tower_bearing_indices(from_ns, from_ew)

        return {
            "from": from_payload,
            "to": to_payload,
            "start": {
                "tower_visible": start_visible,
                "tower_bearing": start_bearing,
                "hint": build_start_hint(start_visible, start_bearing),
            },
            "routes": routes,
        }

    def _candidate_movements(
        self,
        from_ns: int,
        from_ew: int,
        to_ns: int,
        to_ew: int,
    ) -> list[list[Movement]]:
        ns_movement = self._movement_for_axis("ns", from_ns, to_ns)
        ew_movement = self._movement_for_axis("ew", from_ew, to_ew)

        if ns_movement and ew_movement:
            return [[ew_movement, ns_movement], [ns_movement, ew_movement]]
        if ew_movement:
            return [[ew_movement]]
        if ns_movement:
            return [[ns_movement]]
        return []

    def _movement_for_axis(self, axis: Axis, current: int, target: int) -> Movement | None:
        diff = target - current
        if diff == 0:
            return None
        if axis == "ew":
            direction: Direction = "下ル" if diff > 0 else "上ル"
        else:
            direction = "西入ル" if diff > 0 else "東入ル"
        return Movement(axis=axis, direction=direction, count=abs(diff))

    def _build_candidate(
        self,
        start_ns: int,
        start_ew: int,
        movements: list[Movement],
    ) -> dict[str, Any] | None:
        current_ns = start_ns
        current_ew = start_ew
        points = [(current_ns, current_ew)]
        steps = []

        for movement in movements:
            step_start_ns = current_ns
            step_start_ew = current_ew
            target_ns, target_ew = self._target_after_movement(
                current_ns, current_ew, movement
            )

            traversed = self._traverse_points(
                current_ns, current_ew, target_ns, target_ew, movement.axis
            )
            if traversed is None:
                return None

            points.extend(traversed)
            current_ns = target_ns
            current_ew = target_ew
            to_axis = movement.axis
            to_index = current_ns if to_axis == "ns" else current_ew
            start_visible = self.landmark.tower_visible_indices(step_start_ns, step_start_ew)
            start_bearing = self.landmark.tower_bearing_indices(step_start_ns, step_start_ew)
            to_street_name = self.grid.street_name(to_axis, to_index)

            steps.append(
                {
                    "direction": movement.direction,
                    "count": movement.count,
                    "to_street": self.grid.street_id(to_axis, to_index),
                    "to_street_name": to_street_name,
                    "instruction": build_instruction(
                        movement.direction,
                        movement.count,
                        to_street_name,
                        start_visible,
                        start_bearing,
                    ),
                    "tower_visible": start_visible,
                    "tower_bearing": start_bearing,
                }
            )

        visible_count = sum(
            1
            for ns_index, ew_index in points
            if self.landmark.tower_visible_indices(ns_index, ew_index)
        )
        visible_ratio = round(visible_count / len(points), 2)

        return {
            "id": "",
            "visible_ratio": visible_ratio,
            "turns": self._turn_count(steps),
            "steps": steps,
        }

    def _target_after_movement(
        self,
        current_ns: int,
        current_ew: int,
        movement: Movement,
    ) -> tuple[int, int]:
        if movement.axis == "ew":
            step = -1 if movement.direction == "上ル" else 1
            return current_ns, current_ew + step * movement.count
        step = -1 if movement.direction == "東入ル" else 1
        return current_ns + step * movement.count, current_ew

    def _traverse_points(
        self,
        current_ns: int,
        current_ew: int,
        target_ns: int,
        target_ew: int,
        axis: Axis,
    ) -> list[tuple[int, int]] | None:
        traversed: list[tuple[int, int]] = []
        if axis == "ew":
            step = 1 if target_ew > current_ew else -1
            for ew_index in range(current_ew + step, target_ew + step, step):
                if not self.grid.exists_indices(current_ns, ew_index):
                    return None
                traversed.append((current_ns, ew_index))
        else:
            step = 1 if target_ns > current_ns else -1
            for ns_index in range(current_ns + step, target_ns + step, step):
                if not self.grid.exists_indices(ns_index, current_ew):
                    return None
                traversed.append((ns_index, current_ew))
        return traversed

    def _turn_count(self, steps: list[dict[str, Any]]) -> int:
        if not steps:
            return 0
        turns = 0
        previous = steps[0]["direction"]
        for step in steps[1:]:
            if step["direction"] != previous:
                turns += 1
            previous = step["direction"]
        return turns
