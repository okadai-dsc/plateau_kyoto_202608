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

# タワーの方を向いたときに、その向きがどこに当たるか
RELATIVE: dict[int, str] = {
    0: "正面",
    45: "右前",
    90: "右手",
    135: "右後ろ",
    180: "真後ろ",
    225: "左後ろ",
    270: "左手",
    315: "左前",
}


def build_start_hint(tower_visible: bool, tower_bearing: Bearing | None) -> str:
    """出発地点での方角の手がかり。

    京都タワーは経路を選ぶためではなく、**どちらが上ルかを知るため**にある。
    タワーを正面に見たとき上ルがどちらに当たるかを言えば、
    方位を意識しなくても四方向が決まる（docs/SPEC.md 2.1）。
    """
    if not tower_visible or tower_bearing is None:
        return "京都タワーは見えません。通り名の標識で方角を確かめてください。"

    relative = RELATIVE[(DIRECTION_ANGLE["上ル"] - BEARING_ANGLE[tower_bearing]) % 360]
    if relative == "正面":
        return f"京都タワーが{tower_bearing}に見えます。タワーの方が上ルです。"
    return f"京都タワーが{tower_bearing}に見えます。タワーを正面に見て、{relative}が上ルです。"


def build_move_instruction(
    direction: Direction,
    count: int,
    to_street_name: str,
) -> str:
    """1方向ぶんの指示。

    順番は指定しない（docs/SPEC.md 3.5）ため、区間ごとの言い回しはしない。
    本数は通る道によって変わるので目安として示し、通り名を正とする。
    """
    return f"{to_street_name}まで{direction}（およそ{count}本）"
