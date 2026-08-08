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

def build_visible_for(landmark, source, exists, ns_at, ew_at) -> list[list[bool]]:
    """ランドマークごとの可視マスク。visible[ew][ns]

    本来は PLATEAU から計算して外部提供される（docs/SPEC.md 4.8.2）。
    受領するまでの仮データをここで作る。
    """
    n_ns, n_ew = len(source["ns"]), len(source["ew"])
    hint = landmark.get("visible_hint", {})
    visible = [[False] * n_ns for _ in range(n_ew)]

    # 見通しの効く南北の通り
    for corridor in hint.get("corridors_ns", []):
        ns = ns_at[corridor["street"]]
        for ew in span_range(corridor["span"], ew_at):
            visible[ew][ns] = True

    # 見通しの効く東西の通り
    for corridor in hint.get("corridors_ew", []):
        ew = ew_at[corridor["street"]]
        for ns in span_range(corridor["span"], ns_at):
            visible[ew][ns] = True

    # 東の山は、幅の広い東西の通り沿いなら見える（東を向いた見通しが取れるため）
    if hint.get("corridors_ew_major"):
        for ew, street in enumerate(source["ew"]):
            if street.get("major"):
                for ns in range(n_ns):
                    visible[ew][ns] = True

    # ランドマークの周辺は開けている
    radius = int(hint.get("around", 0))
    if radius and "ns" in landmark:
        ns0, ew0 = ns_at[landmark["ns"]], ew_at[landmark["ew"]]
        for ew in range(max(0, ew0 - radius), min(n_ew, ew0 + radius + 1)):
            for ns in range(max(0, ns0 - radius), min(n_ns, ns0 + radius + 1)):
                visible[ew][ns] = True

    # 存在しない交差点では立てないので必ず不可視にする
    for ew in range(n_ew):
        for ns in range(n_ns):
            if not exists[ew][ns]:
                visible[ew][ns] = False

    return visible


# ── ランドマークと方位 ──────────────────────────────────
#
# 方位は添字の符号ではなく、実距離（pos）から角度を出して8方位に丸める。
# 符号だけだと、烏丸通の1本隣に立っただけで 2.6km 先のタワーが「南西」になり、
# 実際には真南に見えているのにズレる。

import math

DIRS = ["北", "北東", "東", "南東", "南", "南西", "西", "北西"]

# タワーの方を向いたときに、その向きがどこに当たるか
RELATIVE = {
    0: "正面", 45: "右前", 90: "右手", 135: "右後ろ",
    180: "真後ろ", 225: "左後ろ", 270: "左手", 315: "左前",
}


def landmark_xy(landmark, source, ns_at, ew_at):
    """ランドマークの位置(m)。x = 川端通から西へ、y = 今出川通から南へ。"""
    if "pos" in landmark:
        return float(landmark["pos"]["x"]), float(landmark["pos"]["y"])
    return (
        float(source["ns"][ns_at[landmark["ns"]]]["pos"]),
        float(source["ew"][ew_at[landmark["ew"]]]["pos"]),
    )


def bearing_and_distance(source, ns, ew, target_xy):
    """交差点からランドマークへの方位（8方位）と距離(m)。"""
    x, y = float(source["ns"][ns]["pos"]), float(source["ew"][ew]["pos"])
    dx, dy = target_xy[0] - x, target_xy[1] - y      # 西向き / 南向き
    distance = math.hypot(dx, dy)
    if distance == 0:
        return None, 0.0
    angle = math.degrees(math.atan2(-dx, -dy)) % 360  # 北=0, 東=90
    return DIRS[round(angle / 45) % 8], distance


def start_hint(landmark_name, bearing, distance, min_distance):
    """出発地点での方角の手がかり。

    文面は backend/app/instruction.py と揃える。
    """
    if landmark_name is None:
        return "目印が見えません。通り名の標識で方角を確かめてください。"
    if bearing is None or distance < min_distance:
        return f"{landmark_name}はすぐそこです。見上げる位置なので方角の目印には使えません。"
    relative = RELATIVE[(0 - DIRS.index(bearing) * 45) % 360]
    if relative == "正面":
        return f"{landmark_name}が{bearing}に見えます。{landmark_name}の方が上ルです。"
    return f"{landmark_name}が{bearing}に見えます。{landmark_name}を正面に見て、{relative}が上ルです。"


# ── 「方角 × 本数」の生成 ────────────────────────────────

def build_moves(frm, to, source):
    """経路は指定せず、方角と本数だけを出す（docs/SPEC.md 3.5）。

    本数は通り順の添字の差。実際に横切る本数は通る道で変わるため目安で、
    通り名を正とする。backend/app/router.py と同じ規則。
    """
    ns_from, ew_from = frm
    ns_to, ew_to = to

    moves = []
    if ew_to != ew_from:
        direction = "上ル" if ew_to < ew_from else "下ル"
        name = source["ew"][ew_to]["name"]
        moves.append({
            "direction": direction,
            "count": abs(ew_to - ew_from),
            "to_street": f"ew-{ew_to:02d}",
            "to_street_name": name,
            "instruction": f"{name}まで{direction}（およそ{abs(ew_to - ew_from)}本）",
        })
    if ns_to != ns_from:
        direction = "東入ル" if ns_to < ns_from else "西入ル"
        name = source["ns"][ns_to]["name"]
        moves.append({
            "direction": direction,
            "count": abs(ns_to - ns_from),
            "to_street": f"ns-{ns_to:02d}",
            "to_street_name": name,
            "instruction": f"{name}まで{direction}（およそ{abs(ns_to - ns_from)}本）",
        })
    return moves


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
    spots = build_spots(source, exists, ns_at, ew_at)

    # ランドマークごとに可視マスクを作る。layer が小さいほど優先（精度が高い）
    landmarks = sorted(source["landmarks"], key=lambda l: l["layer"])
    visible = {l["id"]: build_visible_for(l, source, exists, ns_at, ew_at) for l in landmarks}
    landmark_xy_by_id = {l["id"]: landmark_xy(l, source, ns_at, ew_at) for l in landmarks}

    def best_landmark(ns, ew):
        """その交差点から見える、いちばん精度の高いランドマーク。"""
        for l in landmarks:
            if not visible[l["id"]][ew][ns]:
                continue
            bearing, distance = bearing_and_distance(source, ns, ew, landmark_xy_by_id[l["id"]])
            if distance < float(l.get("min_distance", 0)):
                return l, None, distance      # 近すぎて方位に使えない
            return l, bearing, distance
        return None, None, None

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

    start_landmark, start_bearing, start_distance = best_landmark(*frm)
    route = {
        "from": {"ns": f"ns-{frm[0]:02d}", "ew": f"ew-{frm[1]:02d}"},
        "to": {"ns": f"ns-{to[0]:02d}", "ew": f"ew-{to[1]:02d}"},
        "start": {
            "landmark": None if start_landmark is None else {
                "id": start_landmark["id"],
                "name": start_landmark["name"],
                "layer": start_landmark["layer"],
                "bearing": start_bearing,
                "distance": round(start_distance),
            },
            "hint": start_hint(
                None if start_landmark is None else start_landmark["name"],
                start_bearing,
                start_distance if start_distance is not None else 0.0,
                0 if start_landmark is None else float(start_landmark.get("min_distance", 0)),
            ),
        },
        "moves": build_moves(frm, to, source),
    }

    outputs = {
        ROOT / "backend" / "app" / "data" / "streets.json": {
            "ns": street_entries("ns"),
            "ew": street_entries("ew"),
            "tower": {"ns": tower[0], "ew": tower[1]},
            "landmarks": [
                {
                    "id": l["id"], "name": l["name"], "layer": l["layer"],
                    "x": landmark_xy_by_id[l["id"]][0], "y": landmark_xy_by_id[l["id"]][1],
                    "min_distance": l.get("min_distance", 0),
                }
                for l in landmarks
            ],
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
    per_landmark = {lid: sum(sum(row) for row in matrix) for lid, matrix in visible.items()}
    lines = [
        f"\n南北 {len(source['ns'])}本 × 東西 {len(source['ew'])}本 = 交差点 {total}",
        f"  実在  {n_exists}",
        "  目印が見える交差点:",
    ]
    for landmark in landmarks:
        seen = per_landmark[landmark["id"]]
        lines.append(f"    L{landmark['layer']} {landmark['name']:<8} {seen:>4}（実在の {seen / n_exists:.0%}）")
    covered = sum(
        1
        for ew in range(len(source["ew"]))
        for ns in range(len(source["ns"]))
        if exists[ew][ns] and any(visible[l["id"]][ew][ns] for l in landmarks)
    )
    lines.append(f"    どれか1つでも  {covered}（実在の {covered / n_exists:.0%}）")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
