from __future__ import annotations

from .models import Bearing

DIRECTIONS: list[Bearing] = ["北", "北東", "東", "南東", "南", "南西", "西", "北西"]

# 目印の方を向いたときに、その向きがどこに当たるか
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


def build_start_hint(
    landmark_name: str | None,
    bearing: Bearing | None,
    distance: float | None = None,
    min_distance: float = 0,
) -> str:
    """出発地点での方角の手がかり。

    目印は経路を選ぶためではなく、**どちらが上ルかを知るため**にある。
    目印を正面に見たとき上ルがどちらに当たるかを言えば、
    方位を意識しなくても四方向が決まる（docs/SPEC.md 2.1）。
    """
    if landmark_name is None:
        return "目印が見えません。通り名の標識で方角を確かめてください。"

    # 近すぎると見上げる形になり、水平方向が読みにくい
    if bearing is None or (distance is not None and distance < min_distance):
        return f"{landmark_name}はすぐそこです。見上げる位置なので方角の目印には使えません。"

    relative = RELATIVE[(0 - DIRECTIONS.index(bearing) * 45) % 360]
    if relative == "正面":
        return f"{landmark_name}が{bearing}に見えます。{landmark_name}の方が上ルです。"
    return f"{landmark_name}が{bearing}に見えます。{landmark_name}を正面に見て、{relative}が上ルです。"


def build_move_instruction(direction: str, count: int, to_street_name: str) -> str:
    """1方向ぶんの指示。

    順番は指定しない（docs/SPEC.md 3.5）ため、区間ごとの言い回しはしない。
    本数は通る道によって変わるので目安として示し、通り名を正とする。
    """
    return f"{to_street_name}まで{direction}（およそ{count}本）"
