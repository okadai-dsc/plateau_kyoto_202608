#!/usr/bin/env python3
"""各交差点から、どの方角に「山の稜線」が見えるかを計算する。

京都は三方を山に囲まれた盆地なので、点の目印（京都タワー・大文字の火床）が
見えなくても、**稜線のどこかが建物の上に出ていれば方角は分かる**。
点で判定すると厳しすぎるので、扇状に視線を飛ばして稜線を探す。

  python3 tools/calc_skyline.py

グリッドは data/osm/grid_*.npy にキャッシュする（作るのに10分ほどかかるため）。
出力は data/osm/skyline.json。
"""

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OSM_DIR = ROOT / "data" / "osm"

from calc_viewshed import (  # noqa: E402
    CELL, EYE, LAT0, LAT1, LON0, LON1, M_PER_LAT, M_PER_LON, NX, NY,
    burn_buildings, burn_terrain, sample, to_cell,
)

# 山とみなす条件
MOUNTAIN_ELEVATION = 150.0     # これより高い地形を山とみなす（洛中の地面は 20〜60m）
MIN_DISTANCE = 800.0           # これより遠いこと（近所の高台を山と誤認しない）

FAN_DEGREES = 40               # 方角ごとに ±この角度で扇状に探す
FAN_STEPS = 9                  # 扇の中で飛ばす視線の本数
MAX_RANGE = 16000.0            # 視線の最大長(m)。愛宕山まで約13km

DIRECTIONS = {
    "北": 0, "北東": 45, "東": 90, "南東": 135,
    "南": 180, "南西": 225, "西": 270, "北西": 315,
}


def build_grids():
    terrain_path = OSM_DIR / "grid_terrain.npy"
    surface_path = OSM_DIR / "grid_surface.npy"
    if terrain_path.exists() and surface_path.exists():
        print("キャッシュしたグリッドを読み込み")
        return np.load(terrain_path), np.load(surface_path)

    grid = np.full((NY, NX), -9999.0, dtype=np.float32)
    burn_terrain(grid)
    terrain = grid.copy()
    burn_buildings(grid)
    OSM_DIR.mkdir(parents=True, exist_ok=True)
    np.save(terrain_path, terrain)
    np.save(surface_path, grid)
    print("グリッドをキャッシュしました")
    return terrain, grid


def skyline_visible(terrain, surface, ox, oy, oz, bearing_deg):
    """その方角に山の稜線が見えるか。

    視線を外へ伸ばしながら「これまでに見えた一番高い仰角」を更新していき、
    それを超える地形（＝手前の建物より上に出ている）が現れたら見えたとみなす。
    山は点ではなく面なので、扇状に複数の視線を飛ばす。

    1本あたり数千セルを辿るため、numpy でまとめて計算する。
    """
    steps = int(MAX_RANGE / CELL)
    i = np.arange(1, steps, dtype=np.float32)
    distance = i * CELL

    for offset in np.linspace(-FAN_DEGREES, FAN_DEGREES, FAN_STEPS):
        angle = math.radians(bearing_deg + offset)
        dx, dy = math.sin(angle), math.cos(angle)      # 北=0、東=90
        xs = (ox + dx * i).astype(np.int32)
        ys = (oy + dy * i).astype(np.int32)

        inside = (xs >= 0) & (xs < NX) & (ys >= 0) & (ys < NY)
        if not inside.any():
            continue
        xs = np.clip(xs, 0, NX - 1)
        ys = np.clip(ys, 0, NY - 1)

        top = surface[ys, xs]
        ground = terrain[ys, xs]
        known = inside & (top > -9000)

        elevation = np.where(known, (top - oz) / distance, -np.inf)
        running = np.maximum.accumulate(elevation)
        previous = np.concatenate(([-np.inf], running[:-1]))

        # 手前のどれよりも高く見えている＝稜線に出ている
        on_skyline = elevation > previous
        # 建物ではなく地形そのもの、かつ十分に高く遠い
        is_mountain = (
            known
            & (ground > MOUNTAIN_ELEVATION)
            & (distance > MIN_DISTANCE)
            & (ground >= top - 1.0)
        )
        if np.any(on_skyline & is_mountain):
            return True
    return False


def main() -> None:
    terrain, surface = build_grids()

    data = json.loads((OSM_DIR / "intersections.json").read_text(encoding="utf-8"))
    points = data["intersections"]
    print(f"\n交差点 {len(points)}箇所 × {len(DIRECTIONS)}方位 を判定")

    result = {}
    for index, (pair, (lat, lon)) in enumerate(points.items(), start=1):
        if not (LAT0 <= lat <= LAT1 and LON0 <= lon <= LON1):
            continue
        px, py = to_cell(lat, lon)
        ground = sample(terrain, px, py)
        if ground <= -9000:
            continue
        eye = ground + EYE
        seen = [name for name, bearing in DIRECTIONS.items()
                if skyline_visible(terrain, surface, px, py, eye, bearing)]
        if seen:
            result[pair] = seen
        if index % 100 == 0:
            print(f"  {index}/{len(points)}", flush=True)

    out = OSM_DIR / "skyline.json"
    out.write_text(json.dumps({"ns": data["ns"], "ew": data["ew"], "skyline": result},
                              ensure_ascii=False), encoding="utf-8")

    total = len(points)
    print(f"\n山の稜線がどこかに見える交差点: {len(result)}/{total}（{len(result)/total:.0%}）")
    counts = {}
    for names in result.values():
        for name in names:
            counts[name] = counts.get(name, 0) + 1
    for name in DIRECTIONS:
        n = counts.get(name, 0)
        print(f"  {name:<4} {n:>4}（{n/total:.0%}）")
    print(f"\nwrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
