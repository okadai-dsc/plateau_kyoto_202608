#!/usr/bin/env python3
"""交差点の1点ではなく「通りを少し歩く範囲」で山が見えるかを計算する。

このアプリは交差点で立ち止まるのではなく通りを歩くので、
「その交差点の周辺を歩けば方角が分かるか」が正しい判定単位になる。

交差点から通り沿いに ±WALK まで数点サンプリングし、
どこかで稜線が見えれば「見える」とする。何m歩けばよいかも記録する。

  python3 tools/calc_skyline.py        # 先にグリッドを作る（キャッシュされる）
  python3 tools/calc_skyline_walk.py

出力は data/osm/skyline_walk.json。
"""

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OSM_DIR = ROOT / "data" / "osm"

from calc_viewshed import CELL, EYE, LAT0, LAT1, LON0, LON1, NX, NY, sample, to_cell  # noqa: E402
from calc_skyline import (  # noqa: E402
    DIRECTIONS, MAX_RANGE, MIN_DISTANCE, MOUNTAIN_ELEVATION, build_grids,
)

FAN_DEGREES = 40
FAN_STEPS = 5                  # 扇の本数。歩行サンプルを増やすぶん減らす
WALK_METERS = [0, 40, 80]      # 交差点から通り沿いに歩く距離


def skyline_visible(terrain, surface, ox, oy, oz, bearing_deg):
    steps = int(MAX_RANGE / CELL)
    i = np.arange(1, steps, dtype=np.float32)
    distance = i * CELL

    for offset in np.linspace(-FAN_DEGREES, FAN_DEGREES, FAN_STEPS):
        angle = math.radians(bearing_deg + offset)
        dx, dy = math.sin(angle), math.cos(angle)
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

        is_mountain = (
            known
            & (ground > MOUNTAIN_ELEVATION)
            & (distance > MIN_DISTANCE)
            & (ground >= top - 1.0)
        )
        if np.any((elevation > previous) & is_mountain):
            return True
    return False


def walk_points(px, py):
    """交差点から通り沿い（南北・東西）に歩いた地点。京都の通りは軸に揃っている。"""
    points = [(px, py, 0)]
    for meters in WALK_METERS[1:]:
        cells = int(meters / CELL)
        points += [
            (px + cells, py, meters), (px - cells, py, meters),
            (px, py + cells, meters), (px, py - cells, meters),
        ]
    return points


def main() -> None:
    terrain, surface = build_grids()

    data = json.loads((OSM_DIR / "intersections.json").read_text(encoding="utf-8"))
    points = data["intersections"]
    print(f"\n交差点 {len(points)}箇所 × 歩行 {len(WALK_METERS)}段階 × {len(DIRECTIONS)}方位")

    result = {}
    for index, (pair, (lat, lon)) in enumerate(points.items(), start=1):
        if not (LAT0 <= lat <= LAT1 and LON0 <= lon <= LON1):
            continue
        px, py = to_cell(lat, lon)

        best: dict[str, int] = {}
        for ox, oy, meters in walk_points(px, py):
            ground = sample(terrain, ox, oy)
            if ground <= -9000:
                continue
            eye = ground + EYE
            for name, bearing in DIRECTIONS.items():
                if name in best:                     # もっと近くで見えている
                    continue
                if skyline_visible(terrain, surface, ox, oy, eye, bearing):
                    best[name] = meters
        if best:
            result[pair] = best
        if index % 50 == 0:
            print(f"  {index}/{len(points)}", flush=True)

    out = OSM_DIR / "skyline_walk.json"
    out.write_text(json.dumps({"ns": data["ns"], "ew": data["ew"], "skyline": result},
                              ensure_ascii=False), encoding="utf-8")

    total = len(points)
    at_spot = sum(1 for v in result.values() if any(m == 0 for m in v.values()))
    print(f"\n交差点で見える            {at_spot}/{total}（{at_spot / total:.0%}）")
    print(f"少し歩けば見える          {len(result)}/{total}（{len(result) / total:.0%}）")

    counts: dict[str, int] = {}
    for names in result.values():
        for name in names:
            counts[name] = counts.get(name, 0) + 1
    print()
    for name in DIRECTIONS:
        n = counts.get(name, 0)
        print(f"  {name:<4} {n:>4}（{n / total:.0%}）")
    print(f"\nwrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
