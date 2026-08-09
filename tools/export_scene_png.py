#!/usr/bin/env python3
"""線画を PNG に書き出す。説明資料に貼ったり、画像生成に渡したりするため。

  python3 tools/export_scene_png.py            # 目印ごとに代表を数枚
  python3 tools/export_scene_png.py --all      # 全319視点
  python3 tools/export_scene_png.py 12,5 3,8   # 交差点を指定

→ data/osm/scenes_png/

**アプリでは使わない。** アプリが出すのは線画そのもの。
画像生成でリアルにしたものは実在しない建物を描くので、
実景と見比べる道具としては成立しない（docs/SPEC.md 2.6）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cairosvg

ROOT = Path(__file__).resolve().parent.parent
SCENES = ROOT / "backend" / "app" / "data" / "scenes"
OUT = ROOT / "data" / "osm" / "scenes_png"
WIDTH = 1400
PER_LANDMARK = 3


def main() -> int:
    index = json.loads((SCENES / "index.json").read_text(encoding="utf-8"))
    streets = json.loads((ROOT / "backend" / "app" / "data" / "streets.json")
                         .read_text(encoding="utf-8"))
    ns_names = {s["index"]: s["name"] for s in streets["ns"]}
    ew_names = {s["index"]: s["name"] for s in streets["ew"]}

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        keys = [k for k in args if k in index]
        missing = [k for k in args if k not in index]
        for k in missing:
            print(f"  {k}: 線画がありません")
    elif "--all" in sys.argv:
        keys = list(index)
    else:
        # 目印ごとに、面の多い（＝情報量のある）ものから数枚
        by_landmark: dict[str, list[str]] = {}
        for key, entry in index.items():
            by_landmark.setdefault(entry["landmark"], []).append(key)
        keys = []
        for landmark, group in by_landmark.items():
            group.sort(key=lambda k: -(SCENES / index[k]["file"]).stat().st_size)
            keys.extend(group[:PER_LANDMARK])

    OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    for count, key in enumerate(keys, start=1):
        entry = index[key]
        ns_index, ew_index = (int(v) for v in key.split(","))
        label = f"{ns_names[ns_index]}x{ew_names[ew_index]}_{entry['name']}"
        path = OUT / f"{label}.png"
        cairosvg.svg2png(url=str(SCENES / entry["file"]), write_to=str(path),
                         output_width=WIDTH, background_color="white")
        total += path.stat().st_size
        if len(keys) <= 30:
            print(f"  {label}  方位{entry['azimuth']}°")
        elif count % 50 == 0 or count == len(keys):
            print(f"  [{count}/{len(keys)}]", flush=True)

    print(f"\n{len(keys)} 枚  合計 {total / 1e6:.1f} MB")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
