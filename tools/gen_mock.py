#!/usr/bin/env python3
"""仮データとモックJSONを生成する。

生成物:
  mock/grid.json               GET  /api/grid  のモック（フロント用）
  mock/route.json              POST /api/route のモック（フロント用）
  backend/app/data/streets.json   通りの定義   ★実データ受領時に差し替え
  backend/app/data/exists.json    実在マスク   ★実データ受領時に差し替え
  backend/app/data/visible.json   タワー可視性 ★実データ受領時に差し替え

仕様は docs/API.md を参照。通り名は仮名（A通/1通）。
実データが来たら本スクリプトは不要になる。
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --- グリッド定義（仮） -------------------------------------------------
# ns: 南北に走る通り（縦）。index 0 = 最も東、増えるほど西。
# ew: 東西に走る通り（横）。index 0 = 最も北、増えるほど南。
N_NS = 12
N_EW = 16
TOWER_NS = 5
TOWER_EW = 15

NS_NAMES = [f"{chr(ord('A') + i)}通" for i in range(N_NS)]   # A通 .. L通
EW_NAMES = [f"{i + 1}通" for i in range(N_EW)]               # 1通 .. 16通


def build_exists() -> list[list[bool]]:
    """実在マスク。exists[ew][ns]

    フロントの絞り込み処理を検証させるため、意図的に穴を空ける。
    """
    exists = [[True] * N_NS for _ in range(N_EW)]

    # 大きな通り抜け不可の街区（御所・二条城のイメージ）
    for ew in range(3, 6):
        for ns in range(2, 5):
            exists[ew][ns] = False

    # 全区間を走っていない東西の通り（西側で途切れる）
    for ns in range(8, N_NS):
        exists[6][ns] = False

    # 全区間を走っていない南北の通り（北側で途切れる）
    for ew in range(0, 3):
        exists[ew][10] = False

    return exists


def build_visible(exists: list[list[bool]]) -> list[list[bool]]:
    """タワー可視性。visible[ew][ns]

    実際の京都（烏丸通の南北ビスタからタワーが見える）に近い形にして、
    経路選択ロジックの検証に使えるようにする。
    """
    visible = [[False] * N_NS for _ in range(N_EW)]

    # タワーが立つ南北の通り = 見通しが効く（烏丸通のイメージ）
    for ew in range(4, N_EW):
        visible[ew][TOWER_NS] = True

    # タワー周辺は開けている
    for ew in range(TOWER_EW - 2, N_EW):
        for ns in range(TOWER_NS - 2, TOWER_NS + 3):
            if 0 <= ns < N_NS:
                visible[ew][ns] = True

    # 開けた南北の線（鴨川沿いのイメージ）
    for ew in range(8, N_EW):
        visible[ew][1] = True

    # 幅の広い東西の通り（御池通のイメージ）は一部見える
    for ns in range(3, 8):
        visible[7][ns] = True

    # 存在しない交差点では立てないので必ず不可視にする
    for ew in range(N_EW):
        for ns in range(N_NS):
            if not exists[ew][ns]:
                visible[ew][ns] = False

    return visible


# --- 方位の算出（docs/API.md 2.4 / SPEC 4.8.3） -------------------------

BEARING_DEG = {
    "北": 0, "北東": 45, "東": 90, "南東": 135,
    "南": 180, "南西": 225, "西": 270, "北西": 315,
}
DIRECTION_DEG = {"上ル": 0, "東入ル": 90, "下ル": 180, "西入ル": 270}


def tower_bearing(ns: int, ew: int) -> str | None:
    """交差点から見た京都タワーの方角。添字の比較のみで求まる。"""
    vertical = None
    if TOWER_EW > ew:
        vertical = "南"          # ew の添字は北→南に増える
    elif TOWER_EW < ew:
        vertical = "北"

    horizontal = None
    if TOWER_NS > ns:
        horizontal = "西"        # ns の添字は東→西に増える
    elif TOWER_NS < ns:
        horizontal = "東"

    if vertical and horizontal:
        return vertical + horizontal
    return vertical or horizontal  # 同一通り上なら単一方位、足元なら None


def tower_phrase(direction: str, bearing: str | None) -> str | None:
    """タワーを基準にした言い回し（docs/BACKEND.md 4.4）。

    方位を直接言わず「背にして」「右手に見て」と表現する（SPEC 2.1）。
    """
    if bearing is None:
        return None
    diff = (BEARING_DEG[bearing] - DIRECTION_DEG[direction]) % 360
    if diff <= 45 or diff >= 315:
        return "京都タワーに向かって"
    if diff < 135:
        return "京都タワーを右手に見て"
    if diff <= 225:
        return "京都タワーを背にして"
    return "京都タワーを左手に見て"


# --- 経路のモック生成 ---------------------------------------------------

def build_steps(frm, to, vertical_first, visible):
    """経路を手順に分解する。グラフ探索はしない（SPEC 3.5）。"""
    ns_from, ew_from = frm
    ns_to, ew_to = to

    legs = []
    if ew_to != ew_from:
        legs.append(("ew", "上ル" if ew_to < ew_from else "下ル", abs(ew_to - ew_from)))
    if ns_to != ns_from:
        legs.append(("ns", "東入ル" if ns_to < ns_from else "西入ル", abs(ns_to - ns_from)))
    if not vertical_first:
        legs.reverse()

    ns, ew = ns_from, ew_from
    steps = []
    for axis, direction, count in legs:
        # 手順の開始地点で評価する（進んだ後ではない）
        start_ns, start_ew = ns, ew
        bearing = tower_bearing(start_ns, start_ew)
        # タワーが見えない区間では方位の手がかりを付けない（docs/BACKEND.md 4.4）
        visible_here = visible[start_ew][start_ns]
        phrase = tower_phrase(direction, bearing) if visible_here else None

        if axis == "ew":
            ew = ew_to
            street_id, street_name = f"ew-{ew:02d}", EW_NAMES[ew]
        else:
            ns = ns_to
            street_id, street_name = f"ns-{ns:02d}", NS_NAMES[ns]

        instruction = f"{count}本{direction}（{street_name}まで）"
        if phrase:
            instruction = f"{phrase}、{instruction}"

        steps.append({
            "direction": direction,
            "count": count,
            "to_street": street_id,
            "to_street_name": street_name,
            "instruction": instruction,
            "tower_visible": visible_here,
            "tower_bearing": bearing,
        })
    return steps


def route_visible_ratio(frm, to, vertical_first, visible):
    """経路上でタワーが見える交差点の割合。"""
    ns_from, ew_from = frm
    ns_to, ew_to = to
    points = []

    def walk(a, b):
        return range(a, b + 1) if a <= b else range(a, b - 1, -1)

    if vertical_first:
        points += [(ns_from, e) for e in walk(ew_from, ew_to)]
        points += [(n, ew_to) for n in walk(ns_from, ns_to)]
    else:
        points += [(n, ew_from) for n in walk(ns_from, ns_to)]
        points += [(ns_to, e) for e in walk(ew_from, ew_to)]

    uniq = list(dict.fromkeys(points))
    seen = sum(1 for ns, ew in uniq if visible[ew][ns])
    return round(seen / len(uniq), 2)


def main() -> None:
    exists = build_exists()
    visible = build_visible(exists)

    ns_streets = [
        {"id": f"ns-{i:02d}", "axis": "ns", "index": i, "name": NS_NAMES[i]}
        for i in range(N_NS)
    ]
    ew_streets = [
        {"id": f"ew-{i:02d}", "axis": "ew", "index": i, "name": EW_NAMES[i]}
        for i in range(N_EW)
    ]

    grid = {
        "ns_streets": ns_streets,
        "ew_streets": ew_streets,
        "exists": exists,
        "tower": {"ns": f"ns-{TOWER_NS:02d}", "ew": f"ew-{TOWER_EW:02d}"},
    }

    # モックの経路: E通 × 12通 → C通 × 8通（docs/API.md 3.2 の例と同じ）
    frm, to = (5, 11), (2, 7)
    routes = []
    for idx, vertical_first in enumerate([True, False], start=1):
        steps = build_steps(frm, to, vertical_first, visible)
        routes.append({
            "id": f"r{idx}",
            "visible_ratio": route_visible_ratio(frm, to, vertical_first, visible),
            "turns": max(0, len(steps) - 1),
            "steps": steps,
        })
    routes.sort(key=lambda r: (-r["visible_ratio"], r["turns"]))

    start_bearing = tower_bearing(*frm)
    route = {
        "from": {"ns": f"ns-{frm[0]:02d}", "ew": f"ew-{frm[1]:02d}"},
        "to": {"ns": f"ns-{to[0]:02d}", "ew": f"ew-{to[1]:02d}"},
        "start": {
            "tower_visible": visible[frm[1]][frm[0]],
            "tower_bearing": start_bearing,
            "hint": (
                f"京都タワーが{start_bearing}に見えます。"
                if visible[frm[1]][frm[0]]
                else "ここからは京都タワーが見えません。"
            ),
        },
        "routes": routes,
    }

    outputs = {
        ROOT / "mock" / "grid.json": grid,
        ROOT / "mock" / "route.json": route,
        ROOT / "backend" / "app" / "data" / "streets.json": {
            "ns": [{"index": i, "name": NS_NAMES[i]} for i in range(N_NS)],
            "ew": [{"index": i, "name": EW_NAMES[i]} for i in range(N_EW)],
            "tower": {"ns": TOWER_NS, "ew": TOWER_EW},
        },
        ROOT / "backend" / "app" / "data" / "exists.json": {"exists": exists},
        ROOT / "backend" / "app" / "data" / "visible.json": {"visible": visible},
    }

    for path, payload in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {path.relative_to(ROOT)}")

    total = N_NS * N_EW
    n_exists = sum(sum(r) for r in exists)
    n_visible = sum(sum(r) for r in visible)
    print(f"\n交差点 {total} / 実在 {n_exists} / タワー可視 {n_visible} "
          f"({n_visible / n_exists:.0%} of existing)")


if __name__ == "__main__":
    main()
