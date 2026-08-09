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


def build_start_hint(cue: dict | None) -> str:
    """出発地点での方角の手がかり。

    目印は経路を選ぶためではなく、**どちらが上ルかを知るため**にある。
    精度が高い順に4層あり、最後の「大きい通り」は
    車がよく通っている方角で気づかせるのでどこでも使える（docs/SPEC.md 2.4）。
    """
    if not cue or cue.get("kind") in (None, "none"):
        return "通り名の標識で方角を確かめてください。"

    kind = cue.get("kind")

    # 稜線は「山の稜線」という名前をそのまま文に入れると硬いので短くする
    name = "山" if kind == "skyline" else (cue.get("name") or "目印")
    bearing = cue.get("bearing")

    if bearing is None:
        return f"{name}はすぐそこです。見上げる位置なので方角の目印には使えません。"

    relative = RELATIVE[(0 - DIRECTIONS.index(bearing) * 45) % 360]
    facing = f"{name}の方が上ルです。" if relative == "正面" else f"{name}を正面に見て、{relative}が上ルです。"

    if kind == "skyline":
        walk = int(cue.get("walk", 0))
        if walk > 0:
            return f"{bearing}へ{walk}mほど歩くと山が見えます。{facing}"
        return f"{bearing}に山が見えます。{facing}"

    if kind == "range":
        # 連なりは「正面に見て」が成り立たない。個別の山も名指ししない
        if relative == "正面":
            return f"{bearing}に{name}の山並みが広がっています。そちらが上ルです。"
        return f"{bearing}に{name}の山並みが広がっています。そちらを向くと、{relative}が上ルです。"

    if kind == "street":
        # そこまで歩かせない。立った場所から「あっちは車がよく通ってるな」で気づかせる
        return f"{bearing}の方を車がよく通っています。あちらが{name}です。{facing}"

    return f"{name}が{bearing}に見えます。{facing}"


def build_move_instruction(direction: str, count: int, to_street_name: str) -> str:
    """1方向ぶんの指示。

    順番は指定しない（docs/SPEC.md 3.5）ため、区間ごとの言い回しはしない。
    本数は通る道によって変わるので目安として示し、通り名を正とする。
    """
    return f"{to_street_name}まで{direction}（およそ{count}本）"
