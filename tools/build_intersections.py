#!/usr/bin/env python3
"""OSM の通り形状から、交差点の座標を出す。

南北の通りと東西の通りの折れ線が実際に交わる点を求める。
これで「どの交差点が実在するか」と「その緯度経度」が同時に決まる。

  python3 tools/fetch_osm_streets.py     # 先にこれ
  python3 tools/build_intersections.py

出力は data/osm/intersections.json（Git管理外）。
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tools" / "kyoto_streets.json"
OSM_DIR = ROOT / "data" / "osm"


def segment_cross(p1, p2, p3, p4):
    """線分 p1-p2 と p3-p4 の交点。交わらなければ None。

    緯度経度をそのまま平面として扱う。洛中の範囲なら誤差は無視できる。
    """
    x1, y1 = p1[1], p1[0]
    x2, y2 = p2[1], p2[0]
    x3, y3 = p3[1], p3[0]
    x4, y4 = p4[1], p4[0]

    denominator = (x2 - x1) * (y4 - y3) - (y2 - y1) * (x4 - x3)
    if denominator == 0:
        return None
    t = ((x3 - x1) * (y4 - y3) - (y3 - y1) * (x4 - x3)) / denominator
    u = ((x3 - x1) * (y2 - y1) - (y3 - y1) * (x2 - x1)) / denominator
    if not (0 <= t <= 1 and 0 <= u <= 1):
        return None
    return [y1 + t * (y2 - y1), x1 + t * (x2 - x1)]


def crossings(lines_a, lines_b):
    """2本の通りが交わる点をすべて返す。"""
    points = []
    for line_a in lines_a:
        for i in range(len(line_a) - 1):
            a1, a2 = line_a[i], line_a[i + 1]
            for line_b in lines_b:
                for j in range(len(line_b) - 1):
                    point = segment_cross(a1, a2, line_b[j], line_b[j + 1])
                    if point:
                        points.append(point)
    return points


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    lines = json.loads((OSM_DIR / "streets.json").read_text(encoding="utf-8"))

    ns_names = [s["name"] for s in source["ns"]]
    ew_names = [s["name"] for s in source["ew"]]

    # 折れ線の座標範囲で粗く弾いてから交点を探す（総当たりは遅い）
    def bounds(name):
        pts = [p for line in lines.get(name, []) for p in line]
        if not pts:
            return None
        lats = [p[0] for p in pts]
        lons = [p[1] for p in pts]
        return min(lats), max(lats), min(lons), max(lons)

    ns_bounds = {n: bounds(n) for n in ns_names}
    ew_bounds = {n: bounds(n) for n in ew_names}

    result = {}
    found = 0
    for ns_index, ns_name in enumerate(ns_names):
        nb = ns_bounds[ns_name]
        if nb is None:
            continue
        for ew_index, ew_name in enumerate(ew_names):
            eb = ew_bounds[ew_name]
            if eb is None:
                continue
            # 範囲が重ならなければ交わりようがない
            if nb[1] < eb[0] or eb[1] < nb[0] or nb[3] < eb[2] or eb[3] < nb[2]:
                continue
            points = crossings(lines[ns_name], lines[ew_name])
            if not points:
                continue
            # 複数出たら中央付近を代表点にする（同じ通りが分割されていることがある）
            points.sort()
            lat, lon = points[len(points) // 2]
            result[f"{ns_index},{ew_index}"] = [round(lat, 7), round(lon, 7)]
            found += 1

    out = OSM_DIR / "intersections.json"
    out.write_text(
        json.dumps(
            {"ns": ns_names, "ew": ew_names, "intersections": result},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    total = len(ns_names) * len(ew_names)
    print(f"交差点 {found} / 組み合わせ {total}（{found / total:.0%}）")
    print(f"wrote {out.relative_to(ROOT)}")

    # 手作りの仮データと突き合わせる
    print("\n手作りの実在マスクとの比較:")
    exists = json.loads((ROOT / "backend/app/data/exists.json").read_text())["exists"]
    agree = disagree_missing = disagree_extra = 0
    for ns_index in range(len(ns_names)):
        for ew_index in range(len(ew_names)):
            guessed = bool(exists[ew_index][ns_index])
            actual = f"{ns_index},{ew_index}" in result
            if guessed == actual:
                agree += 1
            elif guessed:
                disagree_extra += 1
            else:
                disagree_missing += 1
    print(f"  一致            {agree} ({agree / total:.0%})")
    print(f"  仮だけ有り      {disagree_extra}")
    print(f"  OSMだけ有り     {disagree_missing}")


if __name__ == "__main__":
    main()
