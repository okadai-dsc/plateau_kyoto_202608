#!/usr/bin/env python3
"""OSM と PLATEAU から出した実データを、アプリのデータに差し込む。

  tools/fetch_osm_streets.py     通りの形状（OSM）
  tools/build_intersections.py   交差点の実座標
  tools/calc_viewshed.py         京都タワー・大文字の可視（PLATEAU）
  tools/calc_skyline_walk.py     山の稜線の可視（PLATEAU）
  tools/apply_real_data.py       ← ここ

方角の手がかりは4層。精度が高い順に使い、最後は必ず何か言える。

  L1 京都タワー   点。方角そのもの
  L2 大文字       点。方角そのもの
  L3 山の稜線     方角そのもの。面なので点より広く見える
  L4 街区の形     軸だけ（南北か東西か）。**どこでも使える**

出力:
  backend/app/data/{streets,exists,visible}.json
  mock/{grid,route}.json
"""

import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OSM = ROOT / "data" / "osm"
SOURCE = ROOT / "tools" / "kyoto_streets.json"

M_PER_LAT = 111_132.0
M_PER_LON = 91_200.0


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    inter = json.loads((OSM / "intersections.json").read_text(encoding="utf-8"))
    viewshed = json.loads((OSM / "viewshed.json").read_text(encoding="utf-8"))["visible"]
    skyline = json.loads((OSM / "skyline_walk.json").read_text(encoding="utf-8"))["skyline"]

    old_ns, old_ew = inter["ns"], inter["ew"]
    points = {tuple(int(v) for v in k.split(",")): xy
              for k, xy in inter["intersections"].items()}

    # 交差点が1つも無い通りは落とす（OSM に無かったもの）
    ns_used = sorted({i for i, _ in points})
    ew_used = sorted({j for _, j in points})
    print(f"通り: 南北 {len(ns_used)}/{len(old_ns)}  東西 {len(ew_used)}/{len(old_ew)}")
    dropped = ([old_ns[i] for i in range(len(old_ns)) if i not in ns_used]
               + [old_ew[j] for j in range(len(old_ew)) if j not in ew_used])
    if dropped:
        print(f"  落とした通り: {' '.join(dropped)}")

    ns_map = {old: new for new, old in enumerate(ns_used)}
    ew_map = {old: new for new, old in enumerate(ew_used)}
    n_ns, n_ew = len(ns_used), len(ew_used)

    meta = {s["name"]: s for s in source["ns"] + source["ew"]}

    # 位置は実測座標から。x = 最も東の通りから西へ(m)、y = 最も北の通りから南へ(m)
    lon_by_ns = {i: statistics.median([points[(a, b)][1] for a, b in points if a == i])
                 for i in ns_used}
    lat_by_ew = {j: statistics.median([points[(a, b)][0] for a, b in points if b == j])
                 for j in ew_used}
    # 経度は東が大きい。x は最も東の通りから西へ測るので、基準は最大値
    lon_ref = max(lon_by_ns.values())
    lat_ref = max(lat_by_ew.values())

    def street(name, pos):
        info = meta.get(name, {})
        return {"index": 0, "name": name, "major": bool(info.get("major")),
                "pos": int(round(pos)), "width": int(info.get("width", 6))}

    ns_streets = []
    for old in ns_used:
        entry = street(old_ns[old], (lon_ref - lon_by_ns[old]) * M_PER_LON)
        entry["index"] = ns_map[old]
        ns_streets.append(entry)
    ew_streets = []
    for old in ew_used:
        entry = street(old_ew[old], (lat_ref - lat_by_ew[old]) * M_PER_LAT)
        entry["index"] = ew_map[old]
        ew_streets.append(entry)

    # ── 実在マスクと可視マスク ──────────────────────────────
    exists = [[False] * n_ns for _ in range(n_ew)]
    tower = [[False] * n_ns for _ in range(n_ew)]
    daimonji = [[False] * n_ns for _ in range(n_ew)]
    sky = {}

    for (i, j), _ in points.items():
        ni, nj = ns_map[i], ew_map[j]
        exists[nj][ni] = True
        key = f"{i},{j}"
        tower[nj][ni] = bool(viewshed["tower"].get(key))
        daimonji[nj][ni] = bool(viewshed["daimonji"].get(key))
        if key in skyline:
            sky[f"{ni},{nj}"] = skyline[key]

    # ── 街区の間隔（4層目の手がかり） ───────────────────────
    def gaps(streets):
        ordered = sorted(streets, key=lambda s: s["index"])
        return [b["pos"] - a["pos"] for a, b in zip(ordered, ordered[1:])
                if 0 < b["pos"] - a["pos"] < 400]
    ns_gap = int(round(statistics.median(gaps(ns_streets))))
    ew_gap = int(round(statistics.median(gaps(ew_streets))))
    print(f"街区: 南北の通り {ns_gap}m 間隔 / 東西の通り {ew_gap}m 間隔")

    # ── 目印（4層） ─────────────────────────────────────────
    def position(name_ns, name_ew):
        i = next(s for s in ns_streets if s["name"] == name_ns)
        j = next(s for s in ew_streets if s["name"] == name_ew)
        return float(i["pos"]), float(j["pos"])

    tower_xy = position("烏丸通", "塩小路通")
    # 大文字は洛中の外。実座標から同じ基準で換算する
    daimonji_xy = ((lon_ref - 135.8020) * M_PER_LON, (lat_ref - 35.0270) * M_PER_LAT)

    landmarks = [
        {"id": "tower", "name": "京都タワー", "layer": 1, "kind": "point",
         "x": round(tower_xy[0]), "y": round(tower_xy[1]), "min_distance": 200},
        {"id": "daimonji", "name": "大文字", "layer": 2, "kind": "point",
         "x": round(daimonji_xy[0]), "y": round(daimonji_xy[1]), "min_distance": 0},
        {"id": "skyline", "name": "山の稜線", "layer": 3, "kind": "skyline"},
        {"id": "block", "name": "街区の形", "layer": 4, "kind": "block"},
    ]

    # ── 観光地（実在する交差点だけ残す） ────────────────────
    spots = []
    for spot in source.get("spots", []):
        try:
            i = next(s for s in ns_streets if s["name"] == spot["at"][0])
            j = next(s for s in ew_streets if s["name"] == spot["at"][1])
        except StopIteration:
            continue
        if not exists[j["index"]][i["index"]]:
            continue
        entry = {"name": spot["name"], "ns": i["index"], "ew": j["index"]}
        if "area" in spot:
            try:
                a = [next(s for s in ns_streets if s["name"] == n)["index"]
                     for n in spot["area"]["ns"]]
                b = [next(s for s in ew_streets if s["name"] == n)["index"]
                     for n in spot["area"]["ew"]]
                entry["area"] = {"ns": [min(a), max(a)], "ew": [min(b), max(b)]}
            except StopIteration:
                pass
        spots.append(entry)
    print(f"観光地: {len(spots)}/{len(source.get('spots', []))}")

    data_dir = ROOT / "backend" / "app" / "data"
    write(data_dir / "streets.json", {
        "ns": ns_streets, "ew": ew_streets,
        "tower": {"ns": next(s["index"] for s in ns_streets if s["name"] == "烏丸通"),
                  "ew": next(s["index"] for s in ew_streets if s["name"] == "塩小路通")},
        "landmarks": landmarks,
        # 緯度経度から内部のメートル座標へ寄せるための基準点。
        # 基準は最も東の南北通り × 最も北の東西通り（pos の原点）。
        "geo": {"reference": {
            "ns": ns_streets[0]["index"], "ew": ew_streets[0]["index"],
            "lat": round(lat_ref, 7), "lng": round(lon_ref, 7),
        }},
        "block": {"ns_spacing": ns_gap, "ew_spacing": ew_gap},
        "spots": spots,
    })
    write(data_dir / "exists.json", {"exists": exists})
    write(data_dir / "visible.json",
          {"visible": {"tower": tower, "daimonji": daimonji, "skyline": sky}})

    total = n_ns * n_ew
    n_exists = sum(sum(r) for r in exists)
    n_tower = sum(sum(r) for r in tower)
    n_dai = sum(sum(r) for r in daimonji)
    covered = sum(1 for j in range(n_ew) for i in range(n_ns)
                  if exists[j][i] and (tower[j][i] or daimonji[j][i] or f"{i},{j}" in sky))
    print(f"\n交差点 {n_exists}/{total}")
    print(f"  L1 京都タワー {n_tower:>4}（{n_tower / n_exists:.0%}）")
    print(f"  L2 大文字     {n_dai:>4}（{n_dai / n_exists:.0%}）")
    print(f"  L3 山の稜線   {len(sky):>4}（{len(sky) / n_exists:.0%}）")
    print(f"  L1〜L3 合計   {covered:>4}（{covered / n_exists:.0%}）")
    print(f"  L4 街区       {n_exists:>4}（100%・どこでも使える）")

    write_mocks()


def write_mocks() -> None:
    """モックはバックエンド自身に作らせる。手で書くと形がずれるため。"""
    import sys
    sys.path.insert(0, str(ROOT))
    from backend.app.grid import Grid              # noqa: PLC0415
    from backend.app.landmark import LandmarkService  # noqa: PLC0415
    from backend.app.router import RouteService    # noqa: PLC0415

    grid = Grid()
    service = RouteService(grid, LandmarkService(grid))

    def street_id(axis, name):
        streets = grid.ns_streets if axis == "ns" else grid.ew_streets
        return next(s["id"] for s in streets if s["name"] == name)

    write(ROOT / "mock" / "grid.json", grid.to_response())
    write(ROOT / "mock" / "route.json", service.build_route_response(
        {"ns": street_id("ns", "河原町通"), "ew": street_id("ew", "四条通")},
        {"ns": street_id("ns", "烏丸通"), "ew": street_id("ew", "三条通")},
    ))


def write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
