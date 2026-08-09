#!/usr/bin/env python3
"""各交差点から見た地平線の形（シルエット）を計算する。

なぜ要るか:
  「東に山が見えます」だけでは、三方が山の京都では絞れない。
  見回すと複数の方角に山があり、どれが東かユーザーには分からない。
  **形を見せれば一致させられる** ので、方角ではなく輪郭を渡す。

やっていること:
  1. 地表面グリッド（地形＋建物、calc_viewshed.py が作る）を読む
  2. 各交差点の目線1.5mから、方位1度ごとにレイを飛ばす
  3. 各方位で仰角が最大になる点を拾う ＝ そこが地平線
  4. その高さを作ったのが地形なら「山」、建物なら「建物」

出力 data/osm/horizon.json:
  交差点ごとに 360個の仰角(度) と、その正体（0=空/1=建物/2=山）
  さらに ridge として、建物を無視した地形だけの稜線も持つ

  python3 tools/calc_horizon.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from calc_viewshed import (
    CELL, EYE, FNX, FNY, LAT0, LON0, M_PER_LAT, M_PER_LON, NX, NY, OSM_DIR, ROOT,
    sample_line, to_cell,
)

AZIMUTHS = 360          # 1度きざみ
MAX_RANGE = 25_000.0    # 遠くの山まで届く距離(m)
# 近くは 1m きざみ。5m だと幅4mの通りが建物で埋まり、見通しが消える
# （calc_viewshed.py の FINE_CELL と同じ理由）。遠くは粗くてよい。
STEPS = np.unique(np.concatenate([
    np.arange(3.0, 400.0, 1.0),
    np.arange(400.0, 3000.0, 20.0),
    np.arange(3000.0, MAX_RANGE, 100.0),
]))

# 地形と地表面の差がこれ以下なら「地形＝山」とみなす
BUILDING_EPS = 1.0
# 近くの地面の凹凸ではなく、京都の方角判断に使う山並みとして扱う地形。
RIDGE_MIN_ELEVATION = 150.0
RIDGE_MIN_DISTANCE = 800.0


def main() -> int:
    terrain = np.load(OSM_DIR / "grid_terrain.npy")
    surface = np.load(OSM_DIR / "grid_surface.npy")
    if terrain.shape != (NY, NX):
        print("グリッドの大きさが計算範囲と合いません。"
              "先に python3 tools/calc_viewshed.py --rebuild を実行してください")
        return 1

    data = json.loads((OSM_DIR / "intersections.json").read_text(encoding="utf-8"))
    points = data["intersections"]

    fine = np.load(OSM_DIR / "grid_fine.npy")
    if fine.shape != (FNY, FNX):
        print("細かいグリッドが計算範囲と合いません。calc_viewshed.py を先に実行してください")
        return 1

    angles = np.deg2rad(np.arange(AZIMUTHS))
    # 方位は北=0で時計回り
    dlat = np.cos(angles)[:, None] * STEPS[None, :] / M_PER_LAT
    dlon = np.sin(angles)[:, None] * STEPS[None, :] / M_PER_LON
    distance = STEPS[None, :]

    out = {}
    total = len(points)
    for index, (key, (lat, lon)) in enumerate(points.items(), start=1):
        px, py = to_cell(lat, lon)
        if not (0 <= px < NX and 0 <= py < NY):
            continue
        ground = terrain[py, px]
        if ground <= -9000:
            continue
        eye = ground + EYE

        lats = lat + dlat
        lons = lon + dlon
        # 近くは1mグリッド、遠くは5mグリッドから採る
        top = sample_line(surface, fine, lats.ravel(), lons.ravel()).reshape(lats.shape)
        cx = np.clip(((lons - LON0) * M_PER_LON / CELL).astype(np.int32), 0, NX - 1)
        cy = np.clip(((lats - LAT0) * M_PER_LAT / CELL).astype(np.int32), 0, NY - 1)
        base = terrain[cy, cx]

        valid = top > -9000
        elevation = np.where(valid, np.degrees(np.arctan((top - eye) / distance)), -90.0)
        best = elevation.argmax(axis=1)
        rows = np.arange(AZIMUTHS)

        peak = elevation[rows, best]
        # その高さを作ったのは建物か地形か
        is_building = (top[rows, best] - base[rows, best]) > BUILDING_EPS
        kind = np.where(peak <= 0.05, 0, np.where(is_building, 1, 2))

        # 建物を無視した、地形だけの山稜線。
        # 尾根は建物の裏でも続いているので、絵では連続して描いて建物を上に重ねる。
        ridge_source = valid & (base > RIDGE_MIN_ELEVATION) & (distance > RIDGE_MIN_DISTANCE)
        ground_only = np.where(ridge_source,
                               np.degrees(np.arctan((base - eye) / distance)), -90.0)
        ridge = np.maximum(ground_only.max(axis=1), 0.0)

        out[key] = {
            "elevation": [round(float(v), 1) for v in np.maximum(peak, 0.0)],
            "kind": [int(v) for v in kind],
            # 地平線を作っている地物までの距離(m)。遠いほど霞ませて奥行きを出す
            "distance": [int(STEPS[b]) for b in best],
            # 建物を無視した地形だけの山稜線。建物に隠れる部分も含めて連続している
            "ridge": [round(float(v), 1) for v in ridge],
        }
        if index % 50 == 0 or index == total:
            print(f"  [{index}/{total}]", flush=True)

    path = OSM_DIR / "horizon.json"
    path.write_text(json.dumps({"azimuths": AZIMUTHS, "horizon": out},
                               ensure_ascii=False), encoding="utf-8")
    size = path.stat().st_size / 1e6
    sky = sum(sum(1 for v in h["kind"] if v == 2) for h in out.values())
    print(f"\n交差点 {len(out)}  山が地平線を作る方位 {sky:,} / {len(out) * AZIMUTHS:,}"
          f"（{sky / max(len(out) * AZIMUTHS, 1):.0%}）")
    print(f"wrote {path.relative_to(ROOT)}  {size:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.exit(main())
