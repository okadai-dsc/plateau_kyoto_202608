from __future__ import annotations

from .models import Bearing, Direction

BEARING_ANGLE: dict[Bearing, int] = {
    "北": 0,
    "北東": 45,
    "東": 90,
    "南東": 135,
    "南": 180,
    "南西": 225,
    "西": 270,
    "北西": 315,
}

DIRECTION_ANGLE: dict[Direction, int] = {
    "上ル": 0,
    "東入ル": 90,
    "下ル": 180,
    "西入ル": 270,
}


def build_start_hint(tower_visible: bool, tower_bearing: Bearing) -> str:
    if tower_visible:
        return f"京都タワーが{tower_bearing}に見えます。"
    return "京都タワーは見えません。通り名を確認して進んでください。"


def build_instruction(
    direction: Direction,
    count: int,
    to_street_name: str,
    tower_visible: bool,
    tower_bearing: Bearing,
) -> str:
    body = f"{count}本{direction}（{to_street_name}まで）"
    if not tower_visible:
        return body
    return f"{_tower_phrase(direction, tower_bearing)}、{body}"


def _tower_phrase(direction: Direction, tower_bearing: Bearing) -> str:
    relative_angle = (BEARING_ANGLE[tower_bearing] - DIRECTION_ANGLE[direction]) % 360
    if relative_angle == 0:
        return "京都タワーに向かって"
    if relative_angle == 180:
        return "京都タワーを背にして"
    if relative_angle in (45, 90, 135):
        return "京都タワーを右手に見て"
    return "京都タワーを左手に見て"
