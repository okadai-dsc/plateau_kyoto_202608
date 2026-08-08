#!/usr/bin/env python3
"""京都の通りデータから、バックエンドのデータとモックJSONを生成する。

入力:
  tools/kyoto_streets.json   通りの並び順・延び方・京都タワーの位置（手で編集できる仮データ）

生成物:
  backend/app/data/streets.json   通りの定義   ★実データ受領時に差し替え
  backend/app/data/exists.json    実在マスク   ★実データ受領時に差し替え
  backend/app/data/visible.json   タワー可視性 ★実データ受領時に差し替え
  mock/grid.json                  GET  /api/grid  のモック（フロント単体開発用）
  mock/route.json                 POST /api/route のモック（フロント単体開発用）

仕様は docs/API.md を参照。
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path(__file__).resolve().parent / "kyoto_streets.json"


# ── 元データの読み込み ──────────────────────────────────────

def load_source() -> dict:
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def index_map(streets: list[dict]) -> dict[str, int]:
    return {street["name"]: i for i, street in enumerate(streets)}


def span_range(span: list[str], lookup: dict[str, int]) -> range:
    """span（通り名の組）を添字の範囲に直す。"""
    start, end = lookup[span[0]], lookup[span[1]]
    return range(min(start, end), max(start, end) + 1)


# ── 実在マスク ──────────────────────────────────────────────

def build_exists(source: dict, ns_at: dict[str, int], ew_at: dict[str, int]) -> list[list[bool]]:
    """exists[ew_index][ns_index]

    交差点が存在するのは、両方の通りが互いの位置をまたいでいるとき。
    そのうえで blocked（二条城など）の矩形を落とす。
    """
    n_ns, n_ew = len(source["ns"]), len(source["ew"])

    # ns の通りが届く ew の範囲 / ew の通りが届く ns の範囲
    ns_reach = [set(span_range(s["span"], ew_at)) for s in source["ns"]]
    ew_reach = [set(span_range(s["span"], ns_at)) for s in source["ew"]]

    exists = [
        [(ew in ns_reach[ns]) and (ns in ew_reach[ew]) for ns in range(n_ns)]
        for ew in range(n_ew)
    ]

    for area in source.get("blocked", []):
        for ew in span_range(area["ew"], ew_at):
            for ns in span_range(area["ns"], ns_at):
                exists[ew][ns] = False

    return exists


# ── タワー可視性（実データ受領までの仮データ） ──────────────

def build_visible(
    source: dict,
    exists: list[list[bool]],
    ns_at: dict[str, int],
    ew_at: dict[str, int],
    tower: tuple[int, int],
) -> list[list[bool]]:
    n_ns, n_ew = len(source["ns"]), len(source["ew"])
    hint = source["visible_hint"]
    visible = [[False] * n_ns for _ in range(n_ew)]

    # 見通しの効く南北の通り（烏丸通の南北ビスタなど）
    for corridor in hint.get("corridors_ns", []):
        ns = ns_at[corridor["street"]]
        for ew in span_range(corridor["span"], ew_at):
            visible[ew][ns] = True

    # 見通しの効く東西の通り
    for corridor in hint.get("corridors_ew", []):
        ew = ew_at[corridor["street"]]
        for ns in span_range(corridor["span"], ns_at):
            visible[ew][ns] = True

    # タワーの周辺は開けている
    radius = int(hint.get("around_tower", 0))
    tower_ns, tower_ew = tower
    for ew in range(max(0, tower_ew - radius), min(n_ew, tower_ew + radius + 1)):
        for ns in range(max(0, tower_ns - radius), min(n_ns, tower_ns + radius + 1)):
            visible[ew][ns] = True

    # 存在しない交差点では立てないので必ず不可視にする
    for ew in range(n_ew):
        for ns in range(n_ns):
            if not exists[ew][ns]:
                visible[ew][ns] = False

    return visible


# ── 方位の算出（docs/API.md 2.4 / docs/SPEC.md 4.8.3） ───────

BEARING_DEG = {
    "北": 0, "北東": 45, "東": 90, "南東": 135,
    "南": 180, "南西": 225, "西": 270, "北西": 315,
}
DIRECTION_DEG = {"上ル": 0, "東入ル": 90, "下ル": 180, "西入ル": 270}


def tower_bearing(ns: int, ew: int, tower: tuple[int, int]) -> str | None:
    """交差点から見た京都タワーの方角。添字の比較のみで求まる。"""
    tower_ns, tower_ew = tower

    vertical = None
    if tower_ew > ew:
        vertical = "南"          # ew の添字は北→南に増える
    elif tower_ew < ew:
        vertical = "北"

    horizontal = None
    if tower_ns > ns:
        horizontal = "西"        # ns の添字は東→西に増える
    elif tower_ns < ns:
        horizontal = "東"

    if vertical and horizontal:
        return vertical + horizontal
    return vertical or horizontal  # 同一通り上なら単一方位、足元なら None


def tower_phrase(direction: str, bearing: str | None) -> str | None:
    """タワーを基準にした言い回し（docs/BACKEND.md 4.4）。

    方位を直接言わず「背にして」「右手に見て」と表現する（docs/SPEC.md 2.1）。
    """
    if bearing is None:
        return None
    diff = (BEARING_DEG[bearing] - DIRECTION_DEG[direction]) % 360
    if diff == 0:
        return "京都タワーに向かって"
    if diff == 180:
        return "京都タワーを背にして"
    if diff in (45, 90, 135):
        return "京都タワーを右手に見て"
    return "京都タワーを左手に見て"


# ── 経路のモック生成 ────────────────────────────────────────

def build_route(frm, to, vertical_first, source, exists, visible, tower):
    """経路を手順に分解する。グラフ探索はしない（docs/SPEC.md 3.5）。

    交差点が無い場所は通行を妨げない（横切る通りが1本減るだけ）。
    ただし区間の終点は実在しなければならない。backend/app/router.py と同じ規則。
    通れない場合は None を返す。
    """
    ns_from, ew_from = frm
    ns_to, ew_to = to

    legs = []
    if ew_to != ew_from:
        legs.append(("ew", "上ル" if ew_to < ew_from else "下ル"))
    if ns_to != ns_from:
        legs.append(("ns", "東入ル" if ns_to < ns_from else "西入ル"))
    if not vertical_first:
        legs.reverse()

    ns, ew = ns_from, ew_from
    points = [(ns_from, ew_from)]
    steps = []

    for axis, direction in legs:
        start_ns, start_ew = ns, ew
        bearing = tower_bearing(start_ns, start_ew, tower)
        # タワーが見えない区間では方位の手がかりを付けない（docs/BACKEND.md 4.4）
        visible_here = visible[start_ew][start_ns]
        phrase = tower_phrase(direction, bearing) if visible_here else None

        if axis == "ew":
            if not exists[ew_to][ns]:
                return None                       # 終点で曲がれない
            step = 1 if ew_to > ew else -1
            crossed = [(ns, e) for e in range(ew + step, ew_to + step, step) if exists[e][ns]]
            ew = ew_to
            street_id, street_name = f"ew-{ew:02d}", source["ew"][ew]["name"]
        else:
            if not exists[ew][ns_to]:
                return None
            step = 1 if ns_to > ns else -1
            crossed = [(n, ew) for n in range(ns + step, ns_to + step, step) if exists[ew][n]]
            ns = ns_to
            street_id, street_name = f"ns-{ns:02d}", source["ns"][ns]["name"]

        points.extend(crossed)
        count = len(crossed)   # 「N本」は添字の差ではなく実際に横切る通りの本数

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

    turns = sum(1 for a, b in zip(steps, steps[1:]) if a["direction"] != b["direction"])
    seen = sum(1 for ns_i, ew_i in points if visible[ew_i][ns_i])

    return {
        "id": "",
        "visible_ratio": round(seen / len(points), 2),
        "turns": turns,
        "steps": steps,
    }


# ── 出力 ────────────────────────────────────────────────────

def build_spots(source: dict, exists: list[list[bool]],
                ns_at: dict[str, int], ew_at: dict[str, int]) -> list[dict]:
    """グリッド上に表示する観光地。代表する交差点は実在していなければならない。"""
    spots = []
    for spot in source.get("spots", []):
        ns, ew = ns_at[spot["at"][0]], ew_at[spot["at"][1]]
        if not exists[ew][ns]:
            raise ValueError(
                f"{spot['name']} の代表交差点 {spot['at'][0]} × {spot['at'][1]} は存在しません"
            )
        entry = {"name": spot["name"], "ns": ns, "ew": ew}
        if "area" in spot:
            ns_from, ns_to = (ns_at[n] for n in spot["area"]["ns"])
            ew_from, ew_to = (ew_at[e] for e in spot["area"]["ew"])
            entry["area"] = {
                "ns": [min(ns_from, ns_to), max(ns_from, ns_to)],
                "ew": [min(ew_from, ew_to), max(ew_from, ew_to)],
            }
        spots.append(entry)
    return spots


def main() -> None:
    source = load_source()
    ns_at, ew_at = index_map(source["ns"]), index_map(source["ew"])
    tower = (ns_at[source["tower"]["ns"]], ew_at[source["tower"]["ew"]])

    exists = build_exists(source, ns_at, ew_at)
    visible = build_visible(source, exists, ns_at, ew_at, tower)
    spots = build_spots(source, exists, ns_at, ew_at)

    def street_entries(axis: str) -> list[dict]:
        return [
            {
                "index": i,
                "name": s["name"],
                "major": bool(s.get("major")),
                # 見た目を実際の街の比率に合わせるための実寸（表示専用）
                "pos": int(s["pos"]),
                "width": int(s["width"]),
            }
            for i, s in enumerate(source[axis])
        ]

    ns_streets = [
        {"id": f"ns-{i:02d}", "axis": "ns", **entry}
        for i, entry in enumerate(street_entries("ns"))
    ]
    ew_streets = [
        {"id": f"ew-{i:02d}", "axis": "ew", **entry}
        for i, entry in enumerate(street_entries("ew"))
    ]

    def spot_payload(spot: dict) -> dict:
        entry = {
            "name": spot["name"],
            "at": {"ns": f"ns-{spot['ns']:02d}", "ew": f"ew-{spot['ew']:02d}"},
        }
        if "area" in spot:
            entry["area"] = {
                "ns": [f"ns-{i:02d}" for i in spot["area"]["ns"]],
                "ew": [f"ew-{i:02d}" for i in spot["area"]["ew"]],
            }
        return entry

    grid = {
        "ns_streets": ns_streets,
        "ew_streets": ew_streets,
        "exists": exists,
        "tower": {"ns": f"ns-{tower[0]:02d}", "ew": f"ew-{tower[1]:02d}"},
        "spots": [spot_payload(s) for s in spots],
    }

    # モックの経路: 四条 × 河原町 → 三条 × 烏丸
    frm = (ns_at["河原町通"], ew_at["四条通"])
    to = (ns_at["烏丸通"], ew_at["三条通"])

    # 並べ替えの基準は backend/app/router.py と揃える
    VISIBLE_WEIGHT, TURN_WEIGHT = 100.0, 1.0
    routes = [
        route for route in (
            build_route(frm, to, vertical_first, source, exists, visible, tower)
            for vertical_first in (False, True)
        ) if route is not None
    ]
    routes.sort(
        key=lambda r: r["visible_ratio"] * VISIBLE_WEIGHT - r["turns"] * TURN_WEIGHT,
        reverse=True,
    )
    for index, route in enumerate(routes, start=1):
        route["id"] = f"r{index}"

    start_visible = visible[frm[1]][frm[0]]
    start_bearing = tower_bearing(frm[0], frm[1], tower)
    route = {
        "from": {"ns": f"ns-{frm[0]:02d}", "ew": f"ew-{frm[1]:02d}"},
        "to": {"ns": f"ns-{to[0]:02d}", "ew": f"ew-{to[1]:02d}"},
        "start": {
            "tower_visible": start_visible,
            "tower_bearing": start_bearing,
            # 文面は backend/app/instruction.py の build_start_hint と揃える
            "hint": (
                f"京都タワーが{start_bearing}に見えます。"
                if start_visible
                else "京都タワーは見えません。通り名を確認して進んでください。"
            ),
        },
        "routes": routes,
    }

    outputs = {
        ROOT / "backend" / "app" / "data" / "streets.json": {
            "ns": street_entries("ns"),
            "ew": street_entries("ew"),
            "tower": {"ns": tower[0], "ew": tower[1]},
            "spots": spots,
        },
        ROOT / "backend" / "app" / "data" / "exists.json": {"exists": exists},
        ROOT / "backend" / "app" / "data" / "visible.json": {"visible": visible},
        ROOT / "mock" / "grid.json": grid,
        ROOT / "mock" / "route.json": route,
    }

    for path, payload in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {path.relative_to(ROOT)}")

    total = len(source["ns"]) * len(source["ew"])
    n_exists = sum(sum(row) for row in exists)
    n_visible = sum(sum(row) for row in visible)
    print(
        f"\n南北 {len(source['ns'])}本 × 東西 {len(source['ew'])}本 = 交差点 {total}\n"
        f"  実在        {n_exists}\n"
        f"  タワー可視  {n_visible}（実在の {n_visible / n_exists:.0%}）\n"
        f"  京都タワー  {source['tower']['ns']} × {source['tower']['ew']}"
    )


if __name__ == "__main__":
    main()
