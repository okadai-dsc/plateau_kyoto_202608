#!/usr/bin/env python3
"""国土地理院の標高タイルを取得して、地形グリッドの穴を埋める。

なぜ要るか（docs/SPEC.md 2.5）:
  PLATEAU の地形(dem)は市域を二次メッシュ単位で切ったもので、
  **愛宕山(135.632)も比叡山(135.833)も入っていない**。
  実測した dem の西端は 135.650、東端は 135.825 で、1km前後届かない。

  建物(bldg)は PLATEAU にしか無いので主役は変わらない。
  遠方の地形だけをここで補う。

  タイルは 10mメッシュ(DEM10B)、zoom 14、256x256 の CSV。
  値が "e" のセルはデータ無し。

  python3 tools/fetch_gsi_dem.py
"""

from __future__ import annotations

import math
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "gsi" / "dem"
ZOOM = 14
URL = "https://cyberjapandata.gsi.go.jp/xyz/dem/{z}/{x}/{y}.txt"

# 地形の計算範囲。北山（天ヶ岳 35.150）まで入れるので calc_viewshed より広い
LAT0, LAT1 = 34.940, 35.200
LON0, LON1 = 135.590, 135.860


def tile_xy(lat: float, lon: float, z: int = ZOOM) -> tuple[int, int]:
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    r = math.radians(lat)
    y = int((1.0 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2.0 * n)
    return x, y


def tile_bounds(x: int, y: int, z: int = ZOOM) -> tuple[float, float, float, float]:
    """タイルの (lat上, lat下, lon左, lon右)。"""
    n = 2 ** z

    def lat_of(row: int) -> float:
        t = math.pi * (1 - 2 * row / n)
        return math.degrees(math.atan(math.sinh(t)))

    return lat_of(y), lat_of(y + 1), x / n * 360.0 - 180.0, (x + 1) / n * 360.0 - 180.0


def tiles_for_range() -> list[tuple[int, int]]:
    x0, y0 = tile_xy(LAT1, LON0)      # 北西
    x1, y1 = tile_xy(LAT0, LON1)      # 南東
    return [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]


def fetch(xy: tuple[int, int]) -> str:
    x, y = xy
    path = CACHE / str(ZOOM) / str(x) / f"{y}.txt"
    if path.exists():
        return "cached"
    path.parent.mkdir(parents=True, exist_ok=True)
    url = URL.format(z=ZOOM, x=x, y=y)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                path.write_bytes(response.read())
            return "ok"
        except urllib.error.HTTPError as error:
            if error.code == 404:
                # 海上など標高データが無いタイル。空で記録して再取得を避ける
                path.write_text("")
                return "none"
            time.sleep(1 + attempt)
        except Exception:
            time.sleep(1 + attempt)
    return "failed"


def main() -> int:
    targets = tiles_for_range()
    print(f"範囲 lat {LAT0}–{LAT1} / lon {LON0}–{LON1}")
    print(f"zoom {ZOOM} のタイル {len(targets)} 枚を取得します\n")

    done = {"ok": 0, "cached": 0, "none": 0, "failed": 0}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for index, status in enumerate(pool.map(fetch, targets), start=1):
            done[status] += 1
            if index % 20 == 0 or index == len(targets):
                print(f"  [{index}/{len(targets)}] {done}", flush=True)

    print(f"\n保存先 {CACHE.relative_to(ROOT)}")
    return 1 if done["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
