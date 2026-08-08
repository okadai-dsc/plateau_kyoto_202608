#!/usr/bin/env python3
"""PLATEAU の地形と建物から、各交差点で目印が見えるかを計算する。

  python3 tools/fetch_osm_streets.py      # 通りの形状（OSM）
  python3 tools/build_intersections.py    # 交差点の座標
  python3 tools/calc_viewshed.py          # ここ

やっていること:
  1. 地形(dem)と建物(bldg)を、5m四方の「地表面の高さ」グリッドに焼く
     建物の高さは絶対標高なので、地形と同じグリッドに max で重ねられる
  2. 各交差点（目線 1.5m）から目印の頂部へ視線を引き、
     グリッドを辿って遮られていないか調べる

出力は data/osm/viewshed.json。
"""

import json
import math
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
PLATEAU = ROOT / "data" / "plateau" / "udx"
OSM_DIR = ROOT / "data" / "osm"

# 計算範囲。北の比叡山・北山、西の愛宕山まで入れる。
# ここが狭いと「山が無い」のか「範囲外」なのか区別できない。
LAT0, LAT1 = 34.965, 35.105
LON0, LON1 = 135.620, 135.840
CELL = 5.0                      # グリッドの一辺(m)
EYE = 1.5                       # 歩行者の目線(m)

# 緯度経度→メートルの換算（この緯度での近似）
M_PER_LAT = 111_132.0
M_PER_LON = 91_200.0

LANDMARKS = {
    "tower": {
        "name": "京都タワー",
        "lat": 34.9875, "lon": 135.7595,
        "height": 131.0,            # 塔頂。地面からの高さ
        "on_ground": True,          # 地形の標高に足す
    },
    "daimonji": {
        "name": "大文字",
        "lat": 35.0270, "lon": 135.8020,
        "height": 330.0,            # 火床の標高（絶対）
        "on_ground": False,
    },
}

NX = int((LON1 - LON0) * M_PER_LON / CELL)
NY = int((LAT1 - LAT0) * M_PER_LAT / CELL)

POSLIST = re.compile(r"<gml:posList[^>]*>([^<]+)</gml:posList>")
HEIGHT = re.compile(r"<bldg:measuredHeight[^>]*>([\d.]+)</bldg:measuredHeight>")


def to_cell(lat, lon):
    return (
        int((lon - LON0) * M_PER_LON / CELL),
        int((lat - LAT0) * M_PER_LAT / CELL),
    )


def in_range(lat, lon):
    return LAT0 <= lat <= LAT1 and LON0 <= lon <= LON1


def envelope(path):
    head = path.open(encoding="utf-8", errors="replace").read(4000)
    lo = re.search(r"<gml:lowerCorner>([\d.\- ]+)</gml:lowerCorner>", head)
    up = re.search(r"<gml:upperCorner>([\d.\- ]+)</gml:upperCorner>", head)
    if not lo or not up:
        return None
    a = [float(x) for x in lo.group(1).split()]
    b = [float(x) for x in up.group(1).split()]
    return a[0], b[0], a[1], b[1]


def relevant(kind):
    files = []
    for path in sorted((PLATEAU / kind).glob("*.gml")):
        box = envelope(path)
        if not box:
            continue
        if box[1] < LAT0 or box[0] > LAT1 or box[3] < LON0 or box[2] > LON1:
            continue
        files.append(path)
    return files


def scatter_max(grid, xs, ys, zs):
    """同じセルに複数落ちたら高い方を採る。"""
    ok = (xs >= 0) & (xs < NX) & (ys >= 0) & (ys < NY)
    if not ok.any():
        return
    flat = ys[ok] * NX + xs[ok]
    np.maximum.at(grid.reshape(-1), flat, zs[ok])


def burn_terrain(grid):
    """地形の三角形の頂点を撒く。TIN は頂点が密なので十分。"""
    files = relevant("dem")
    print(f"地形: {len(files)}ファイル")
    for index, path in enumerate(files, start=1):
        lats, lons, zs = [], [], []
        with path.open(encoding="utf-8", errors="replace") as handle:
            for chunk in POSLIST.finditer(handle.read()):
                values = chunk.group(1).split()
                for i in range(0, len(values) - 2, 3):
                    lats.append(float(values[i]))
                    lons.append(float(values[i + 1]))
                    zs.append(float(values[i + 2]))
        if not lats:
            continue
        lat = np.asarray(lats); lon = np.asarray(lons); z = np.asarray(zs)
        xs = ((lon - LON0) * M_PER_LON / CELL).astype(np.int32)
        ys = ((lat - LAT0) * M_PER_LAT / CELL).astype(np.int32)
        scatter_max(grid, xs, ys, z.astype(np.float32))
        print(f"  [{index}/{len(files)}] {path.name}  頂点 {len(lats):,}", flush=True)


def burn_buildings(grid):
    """建物の頂点を撒く。LOD1 なので屋根の高さがそのまま絶対標高で入っている。"""
    files = relevant("bldg")
    print(f"建物: {len(files)}ファイル")
    for index, path in enumerate(files, start=1):
        text = path.open(encoding="utf-8", errors="replace").read()
        lats, lons, zs = [], [], []
        for chunk in POSLIST.finditer(text):
            values = chunk.group(1).split()
            for i in range(0, len(values) - 2, 3):
                lats.append(float(values[i]))
                lons.append(float(values[i + 1]))
                zs.append(float(values[i + 2]))
        if not lats:
            continue
        lat = np.asarray(lats); lon = np.asarray(lons); z = np.asarray(zs)
        xs = ((lon - LON0) * M_PER_LON / CELL).astype(np.int32)
        ys = ((lat - LAT0) * M_PER_LAT / CELL).astype(np.int32)
        scatter_max(grid, xs, ys, z.astype(np.float32))
        print(f"  [{index}/{len(files)}] {path.name}  頂点 {len(lats):,}", flush=True)


def sample(grid, x, y):
    if 0 <= x < NX and 0 <= y < NY:
        return grid[y, x]
    return -9999.0


def visible(grid, observer, target, step=CELL):
    """視線が遮られていないか。observer/target は (x, y, z)。"""
    ox, oy, oz = observer
    tx, ty, tz = target
    dx, dy = tx - ox, ty - oy
    distance = math.hypot(dx, dy)
    if distance < 1e-6:
        return True
    steps = int(distance / (step / CELL))
    for i in range(1, steps):
        t = i / steps
        x = ox + dx * t
        y = oy + dy * t
        surface = sample(grid, int(x), int(y))
        if surface <= -9000:
            continue
        # 出発点と目標を結ぶ直線の、その地点での高さ
        if surface > oz + (tz - oz) * t + 0.5:      # 0.5m は測量誤差の余裕
            return False
    return True


def main() -> None:
    print(f"グリッド {NX} x {NY}（{CELL}m 四方、{NX * NY / 1e6:.1f}M セル）\n")
    grid = np.full((NY, NX), -9999.0, dtype=np.float32)

    burn_terrain(grid)
    terrain = grid.copy()
    burn_buildings(grid)

    filled = (grid > -9000).sum()
    print(f"\n高さが入ったセル: {filled:,} / {NX * NY:,}（{filled / (NX * NY):.0%}）")

    data = json.loads((OSM_DIR / "intersections.json").read_text(encoding="utf-8"))
    ns_names, ew_names = data["ns"], data["ew"]
    points = data["intersections"]

    result = {}
    for key, landmark in LANDMARKS.items():
        lx, ly = to_cell(landmark["lat"], landmark["lon"])
        base = sample(terrain, lx, ly)
        if landmark["on_ground"]:
            top = (base if base > -9000 else 30.0) + landmark["height"]
        else:
            top = landmark["height"]

        seen = {}
        for pair, (lat, lon) in points.items():
            if not in_range(lat, lon):
                continue
            px, py = to_cell(lat, lon)
            ground = sample(terrain, px, py)
            if ground <= -9000:
                continue
            seen[pair] = visible(grid, (px, py, ground + EYE), (lx, ly, top))
        result[key] = seen
        n = sum(seen.values())
        print(f"{landmark['name']:<10} 頂部 {top:.0f}m  見える {n}/{len(seen)}"
              f"（{n / max(len(seen), 1):.0%}）")

    out = OSM_DIR / "viewshed.json"
    out.write_text(json.dumps({"ns": ns_names, "ew": ew_names, "visible": result},
                              ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
