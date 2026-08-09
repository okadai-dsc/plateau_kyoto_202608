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

# 計算範囲。北の北山(天ヶ岳 35.150)、西の愛宕山(135.632)まで入れる。
# ここが狭いと「山が無い」のか「範囲外」なのか区別できない。
LAT0, LAT1 = 34.940, 35.200
LON0, LON1 = 135.590, 135.860

# 建物を焼く範囲。建物が視線を遮るのは近傍だけなので、全域では読まない。
# 高さ31mのビルは 3km 先で仰角0.6度。山は3〜5度あるので影響しない。
BLDG_LAT0, BLDG_LAT1 = 34.955, 35.090
BLDG_LON0, BLDG_LON1 = 135.660, 135.850

CELL = 5.0                      # グリッドの一辺(m)
EYE = 1.5                       # 歩行者の目線(m)

# 近くの建物だけ 1m の細かい格子で持つ。
# 5m だと幅4〜5mの通りが両側の建物で埋まり、見通しが消えてしまう
# （堺町通のストリートビューで確認。実際は数百m先まで抜けている）。
# 遠くの地形は粗くてよいので、近=1m / 遠=5m の2段構えにする。
FINE_CELL = 1.0
FINE_LAT0, FINE_LAT1 = 34.968, 35.054
FINE_LON0, FINE_LON1 = 135.724, 135.783
GSI_DEM = ROOT / "data" / "gsi" / "dem"
GSI_ZOOM = 14

# 緯度経度→メートルの換算（この緯度での近似）
M_PER_LAT = 111_132.0
M_PER_LON = 91_200.0

# 目印の定義は tools/kyoto_streets.json が唯一のソース（apply_real_data.py も同じものを読む）
SOURCE = ROOT / "tools" / "kyoto_streets.json"
LANDMARKS = {
    lm["id"]: lm
    for lm in json.loads(SOURCE.read_text(encoding="utf-8"))["landmarks"]
}

# 連なりは尾根に沿って何点か置き、どれか見えれば「見える」とする。
# 見えた点の方位から、実際に見えている範囲（角幅）も出せる。
RANGE_SAMPLES = 21

NX = int((LON1 - LON0) * M_PER_LON / CELL)
NY = int((LAT1 - LAT0) * M_PER_LAT / CELL)
FNX = int((FINE_LON1 - FINE_LON0) * M_PER_LON / FINE_CELL)
FNY = int((FINE_LAT1 - FINE_LAT0) * M_PER_LAT / FINE_CELL)

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


def relevant(kind, bounds=None):
    lat0, lat1, lon0, lon1 = bounds or (LAT0, LAT1, LON0, LON1)
    files = []
    for path in sorted((PLATEAU / kind).glob("*.gml")):
        box = envelope(path)
        if not box:
            continue
        if box[1] < lat0 or box[0] > lat1 or box[3] < lon0 or box[2] > lon1:
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


def burn_gsi(grid):
    """国土地理院の標高タイルを撒く。PLATEAU の地形が届かない遠方を埋める。

    PLATEAU の dem は市域を切ったもので、愛宕山も比叡山も入っていない
    （docs/SPEC.md 2.5）。建物は PLATEAU にしか無いので主役は変わらない。
    """
    files = sorted(GSI_DEM.glob(f"{GSI_ZOOM}/*/*.txt"))
    print(f"地形(国土地理院): {len(files)}タイル")
    n = 2 ** GSI_ZOOM
    for index, path in enumerate(files, start=1):
        text = path.read_text()
        if not text.strip():
            continue
        x = int(path.parent.name)
        y = int(path.stem)
        # タイルの緯度経度の範囲（Webメルカトル）
        top = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
        bottom = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
        left = x / n * 360.0 - 180.0
        right = (x + 1) / n * 360.0 - 180.0

        rows = text.strip().split("\n")
        values = np.array([[float("nan") if v == "e" else float(v)
                            for v in row.split(",")] for row in rows], dtype=np.float32)
        size = values.shape[0]
        # セル中心の緯度経度。メルカトルの歪みはこの範囲では無視できる
        lats = top + (bottom - top) * (np.arange(size) + 0.5) / size
        lons = left + (right - left) * (np.arange(size) + 0.5) / size
        lon_mesh, lat_mesh = np.meshgrid(lons, lats)
        ok = ~np.isnan(values)
        if not ok.any():
            continue
        xs = ((lon_mesh[ok] - LON0) * M_PER_LON / CELL).astype(np.int32)
        ys = ((lat_mesh[ok] - LAT0) * M_PER_LAT / CELL).astype(np.int32)
        scatter_max(grid, xs, ys, values[ok])
        if index % 50 == 0 or index == len(files):
            print(f"  [{index}/{len(files)}]", flush=True)


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
    files = relevant("bldg", (BLDG_LAT0, BLDG_LAT1, BLDG_LON0, BLDG_LON1))
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


def to_fine_cell(lat, lon):
    return (
        int((lon - FINE_LON0) * M_PER_LON / FINE_CELL),
        int((lat - FINE_LAT0) * M_PER_LAT / FINE_CELL),
    )


def build_fine(terrain):
    """洛中まわりだけ 1m の地表面グリッドを作る。

    地形は粗いグリッドから引き伸ばす（洛中はほぼ平坦なので十分）。
    そこに建物を 1m で焼くと、幅4mの通りでも中心3mぶんが空いたまま残る。
    """
    print(f"細かいグリッド {FNX} x {FNY}（{FINE_CELL}m 四方、{FNX * FNY / 1e6:.0f}M セル）")
    ys, xs = np.meshgrid(np.arange(FNY), np.arange(FNX), indexing="ij")
    lat = FINE_LAT0 + (ys + 0.5) * FINE_CELL / M_PER_LAT
    lon = FINE_LON0 + (xs + 0.5) * FINE_CELL / M_PER_LON
    cx = np.clip(((lon - LON0) * M_PER_LON / CELL).astype(np.int32), 0, NX - 1)
    cy = np.clip(((lat - LAT0) * M_PER_LAT / CELL).astype(np.int32), 0, NY - 1)
    fine = terrain[cy, cx].copy()
    del ys, xs, lat, lon, cx, cy

    files = relevant("bldg", (FINE_LAT0, FINE_LAT1, FINE_LON0, FINE_LON1))
    print(f"建物(1m): {len(files)}ファイル")
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
        la = np.asarray(lats); lo = np.asarray(lons); z = np.asarray(zs, dtype=np.float32)
        fx = ((lo - FINE_LON0) * M_PER_LON / FINE_CELL).astype(np.int32)
        fy = ((la - FINE_LAT0) * M_PER_LAT / FINE_CELL).astype(np.int32)
        ok = (fx >= 0) & (fx < FNX) & (fy >= 0) & (fy < FNY)
        if ok.any():
            np.maximum.at(fine.reshape(-1), fy[ok] * FNX + fx[ok], z[ok])
        if index % 40 == 0 or index == len(files):
            print(f"  [{index}/{len(files)}]", flush=True)
    return fine


def sample(grid, x, y):
    if 0 <= x < NX and 0 <= y < NY:
        return grid[y, x]
    return -9999.0


# 視線をたどる刻み。近くは1m（細い通りの見通しを潰さないため）、遠くは5m
RAY_STEPS = np.concatenate([
    np.arange(2.0, 400.0, 1.0),
    np.arange(400.0, 26_000.0, 5.0),
])


def sample_line(coarse, fine, lats, lons):
    """複数地点の地表面の高さ。細かいグリッドの中ならそちらを優先する。"""
    out = np.full(lats.shape, -9999.0, dtype=np.float32)
    inside = ((lats >= FINE_LAT0) & (lats <= FINE_LAT1)
              & (lons >= FINE_LON0) & (lons <= FINE_LON1))
    if inside.any():
        fx = ((lons[inside] - FINE_LON0) * M_PER_LON / FINE_CELL).astype(np.int32)
        fy = ((lats[inside] - FINE_LAT0) * M_PER_LAT / FINE_CELL).astype(np.int32)
        np.clip(fx, 0, FNX - 1, out=fx)
        np.clip(fy, 0, FNY - 1, out=fy)
        out[inside] = fine[fy, fx]
    rest = ~inside
    if rest.any():
        cx = ((lons[rest] - LON0) * M_PER_LON / CELL).astype(np.int32)
        cy = ((lats[rest] - LAT0) * M_PER_LAT / CELL).astype(np.int32)
        ok = (cx >= 0) & (cx < NX) & (cy >= 0) & (cy < NY)
        values = np.full(cx.shape, -9999.0, dtype=np.float32)
        values[ok] = coarse[cy[ok], cx[ok]]
        out[rest] = values
    return out


def visible(coarse, fine, observer, target):
    """視線が遮られていないか。observer/target は (lat, lon, z)。"""
    olat, olon, oz = observer
    tlat, tlon, tz = target
    dlat, dlon = tlat - olat, tlon - olon
    distance = math.hypot(dlat * M_PER_LAT, dlon * M_PER_LON)
    if distance < 2.0:
        return True
    steps = RAY_STEPS[RAY_STEPS < distance]
    if steps.size == 0:
        return True
    t = steps / distance
    surface = sample_line(coarse, fine, olat + dlat * t, olon + dlon * t)
    # 出発点と目標を結ぶ直線の、その地点での高さ。0.5m は測量誤差の余裕
    line = oz + (tz - oz) * t + 0.5
    return not bool(np.any((surface > -9000) & (surface > line)))


def main() -> None:
    print(f"グリッド {NX} x {NY}（{CELL}m 四方、{NX * NY / 1e6:.1f}M セル）\n")
    terrain_path = OSM_DIR / "grid_terrain.npy"
    surface_path = OSM_DIR / "grid_surface.npy"
    cached = (terrain_path.exists() and surface_path.exists()
              and np.load(terrain_path, mmap_mode="r").shape == (NY, NX))

    if cached and "--rebuild" not in sys.argv:
        print("グリッドはキャッシュを使います（作り直すには --rebuild）\n")
        terrain = np.load(terrain_path)
        grid = np.load(surface_path)
    else:
        grid = np.full((NY, NX), -9999.0, dtype=np.float32)
        # 国土地理院で全域を埋めてから、PLATEAU の地形を重ねる（高い方を採る）。
        # PLATEAU は市域しか無いので、遠方の山は国土地理院の値がそのまま残る。
        burn_gsi(grid)
        burn_terrain(grid)
        terrain = grid.copy()
        burn_buildings(grid)
        np.save(terrain_path, terrain)
        np.save(surface_path, grid)

    fine_path = OSM_DIR / "grid_fine.npy"
    if fine_path.exists() and np.load(fine_path, mmap_mode="r").shape == (FNY, FNX) \
            and "--rebuild" not in sys.argv:
        fine = np.load(fine_path)
    else:
        fine = build_fine(terrain)
        np.save(fine_path, fine)

    filled = (grid > -9000).sum()
    print(f"\n高さが入ったセル: {filled:,} / {NX * NY:,}（{filled / (NX * NY):.0%}）"
          f"  最高 {grid.max():.0f}m")

    data = json.loads((OSM_DIR / "intersections.json").read_text(encoding="utf-8"))
    ns_names, ew_names = data["ns"], data["ew"]
    points = data["intersections"]

    def targets_of(landmark):
        """目印の「狙う点」。単独峰は1点、連なりは尾根に沿って複数点。"""
        if landmark["kind"] == "range":
            a, b = landmark["ends"]["from"], landmark["ends"]["to"]
            out = []
            for i in range(RANGE_SAMPLES):
                t = i / (RANGE_SAMPLES - 1)
                lat = a["lat"] + (b["lat"] - a["lat"]) * t
                lon = a["lon"] + (b["lon"] - a["lon"]) * t
                # 尾根の高さは実際の地形から採る。両端を結ぶ直線は谷を横切ることも
                # あるので、近傍の最高点を尾根の高さとみなす
                cx, cy = to_cell(lat, lon)
                radius = int(400 / CELL)
                window = terrain[max(cy - radius, 0):cy + radius,
                                 max(cx - radius, 0):cx + radius]
                usable = window[window > -9000]
                top = float(usable.max()) if usable.size else landmark["height"]
                out.append((lat, lon, max(top, landmark["height"] * 0.5)))
            return out
        lx, ly = to_cell(landmark["lat"], landmark["lon"])
        base = sample(terrain, lx, ly)
        if landmark.get("on_ground"):
            top = (base if base > -9000 else 30.0) + landmark["height"]
        else:
            top = landmark["height"]
        return [(landmark["lat"], landmark["lon"], top)]

    result = {}
    for key, landmark in LANDMARKS.items():
        spots = targets_of(landmark)

        seen = {}
        for pair, (lat, lon) in points.items():
            if not in_range(lat, lon):
                continue
            px, py = to_cell(lat, lon)
            ground = sample(terrain, px, py)
            if ground <= -9000:
                continue
            eye = (lat, lon, ground + EYE)
            hits = [i for i, spot in enumerate(spots)
                    if visible(grid, fine, eye, spot)]
            if landmark["kind"] == "range":
                # 見えた尾根上の点の番号。空なら見えない
                seen[pair] = hits
            else:
                seen[pair] = bool(hits)
        result[key] = seen
        n = sum(1 for v in seen.values() if v)
        top_text = f"{spots[0][2]:.0f}m" if len(spots) == 1 else f"尾根{len(spots)}点"
        print(f"{landmark['name']:<10} {top_text:<10} 見える {n}/{len(seen)}"
              f"（{n / max(len(seen), 1):.0%}）")

    out = OSM_DIR / "viewshed.json"
    out.write_text(json.dumps({"ns": ns_names, "ew": ew_names, "visible": result},
                              ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
