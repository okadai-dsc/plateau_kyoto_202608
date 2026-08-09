#!/usr/bin/env python3
"""全交差点ぶんの線画を書き出す。

  python3 tools/calc_viewshed.py    # 目印が見えるか
  python3 tools/calc_horizon.py     # 地平線プロファイル
  python3 tools/gen_scenes.py       # ここ
  → data/osm/scenes/{ns}_{ew}.svg と index.json

preview_scene.py と同じ絵を、交差点ごとに事前生成する。
GML は一度だけ読んで空間索引に載せる（視点ごとに読むと現実的な時間で終わらない）。
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from calc_viewshed import OSM_DIR, ROOT, to_cell  # noqa: E402
from preview_scene import (  # noqa: E402
    CX, CY, EYE, FOCAL, HEIGHT, MIN_AREA, M_PER_LAT, M_PER_LON, PLATEAU,
    POLYGON, POSLIST, RADIUS, WIDTH, envelope,
)

OUT = ROOT / "backend" / "app" / "data" / "scenes"
BUCKET = 100.0          # 空間索引の升目(m)


def load_rings(box):
    """建物の面を一度だけ読み、頂点をまとめた配列にする。"""
    verts, offsets, total = [], [0], 0
    files = []
    for path in sorted(PLATEAU.glob("*.gml")):
        env = envelope(path)
        if env and not (env[1] < box[0] or env[0] > box[1]
                        or env[3] < box[2] or env[2] > box[3]):
            files.append(path)
    print(f"建物: {len(files)}ファイルを読みます")
    for index, path in enumerate(files, start=1):
        text = path.open(encoding="utf-8", errors="replace").read()
        for chunk in POLYGON.finditer(text):
            match = POSLIST.search(chunk.group(0))
            if not match:
                continue
            values = match.group(1).split()
            n = (len(values)) // 3
            if n < 3:
                continue
            ring = [(float(values[i * 3]), float(values[i * 3 + 1]),
                     float(values[i * 3 + 2])) for i in range(n)]
            if not any(box[0] <= p[0] <= box[1] and box[2] <= p[1] <= box[3]
                       for p in ring):
                continue
            verts.extend(ring)
            total += n
            offsets.append(total)
        print(f"  [{index}/{len(files)}] 面 {len(offsets) - 1:,}", flush=True)
    return np.asarray(verts, dtype=np.float64), np.asarray(offsets, dtype=np.int64)


def build_index(verts, offsets):
    """面の中心を升目に割り当てる。"""
    starts, ends = offsets[:-1], offsets[1:]
    lats = np.add.reduceat(verts[:, 0], starts) / (ends - starts)
    lons = np.add.reduceat(verts[:, 1], starts) / (ends - starts)
    tops = np.maximum.reduceat(verts[:, 2], starts)
    keys_y = np.floor(lats * M_PER_LAT / BUCKET).astype(np.int64)
    keys_x = np.floor(lons * M_PER_LON / BUCKET).astype(np.int64)
    table = {}
    for i, (ky, kx) in enumerate(zip(keys_y, keys_x)):
        table.setdefault((ky, kx), []).append(i)
    return table, lats, lons, tops


def scene(lat, lon, ground, azimuth, profile, verts, offsets, table,
          lats, lons, tops):
    angle = math.radians(azimuth)
    forward = (math.sin(angle), math.cos(angle))
    right = (math.cos(angle), -math.sin(angle))
    eye_z = ground + EYE

    parts = [f'<svg viewBox="0 0 {WIDTH} {HEIGHT}" xmlns="http://www.w3.org/2000/svg">',
             f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#fff"/>']

    # 山の稜線
    run = []
    for offset in list(range(-40, 41)) + [None]:
        if offset is not None and profile["kind"][(azimuth + offset) % 360] == 2:
            a = (azimuth + offset) % 360
            run.append((CX + math.tan(math.radians(offset)) * FOCAL,
                        CY - math.tan(math.radians(profile["elevation"][a])) * FOCAL))
            continue
        if len(run) > 1:
            d = " ".join(f"{x:.0f},{y:.0f}" for x, y in run)
            parts.append(f'<polyline points="{d}" fill="none" stroke="#1c4a5a" '
                         f'stroke-width="2.4"/>')
        run = []

    # 近くの面を索引から集める
    ky = int(math.floor(lat * M_PER_LAT / BUCKET))
    kx = int(math.floor(lon * M_PER_LON / BUCKET))
    span = int(RADIUS / BUCKET) + 1
    candidates = []
    for dy in range(-span, span + 1):
        for dx in range(-span, span + 1):
            candidates.extend(table.get((ky + dy, kx + dx), ()))

    shapes = []
    for index in candidates:
        if tops[index] <= eye_z:
            continue
        north = (lats[index] - lat) * M_PER_LAT
        east = (lons[index] - lon) * M_PER_LON
        if east * forward[0] + north * forward[1] < 1.0:
            continue
        if math.hypot(north, east) > RADIUS:
            continue
        ring = verts[offsets[index]:offsets[index + 1]]
        # 裏を向いた面は手前に隠れるので描かない
        ex = (ring[:, 1] - lon) * M_PER_LON
        ny_ = (ring[:, 0] - lat) * M_PER_LAT
        ez = ring[:, 2]
        rx, ry, rz = np.roll(ex, -1), np.roll(ny_, -1), np.roll(ez, -1)
        nx = np.sum((ny_ - ry) * (ez + rz))
        nyv = np.sum((ez - rz) * (ex + rx))
        if ex.mean() * nx + ny_.mean() * nyv > 0:
            continue

        depth = ex * forward[0] + ny_ * forward[1]
        if np.any(depth < 1.0):
            continue
        side = ex * right[0] + ny_ * right[1]
        xs = CX + side / depth * FOCAL
        ys = CY - (ez - eye_z) / depth * FOCAL
        if xs.max() < 0 or xs.min() > WIDTH or ys.min() > HEIGHT:
            continue
        area = abs(np.sum(xs * np.roll(ys, 1) - np.roll(xs, 1) * ys)) / 2
        if area < MIN_AREA:
            continue
        shapes.append((float(depth.mean()),
                       " ".join(f"{x:.0f},{y:.0f}" for x, y in zip(xs, ys))))

    # 線の太さごとに <g> でまとめる。1枚ずつ属性を書くと容量が倍近くなる
    current = None
    for depth, points in sorted(shapes, key=lambda s: -s[0]):
        width = "1.4" if depth < 60 else ("1" if depth < 150 else ".6")
        if width != current:
            if current is not None:
                parts.append("</g>")
            parts.append(f'<g fill="#fff" stroke="#232a30" stroke-linejoin="round" '
                         f'stroke-width="{width}">')
            current = width
        parts.append(f'<polygon points="{points}"/>')
    if current is not None:
        parts.append("</g>")
    parts.append("</svg>")
    return "".join(parts), len(shapes)


def main() -> int:
    horizon = json.loads((OSM_DIR / "horizon.json").read_text(encoding="utf-8"))["horizon"]
    inter = json.loads((OSM_DIR / "intersections.json").read_text(encoding="utf-8"))
    view = json.loads((OSM_DIR / "viewshed.json").read_text(encoding="utf-8"))["visible"]
    source = json.loads((ROOT / "tools" / "kyoto_streets.json").read_text(encoding="utf-8"))
    points = inter["intersections"]
    landmarks = sorted(source["landmarks"], key=lambda l: l["layer"])
    terrain = np.load(OSM_DIR / "grid_terrain.npy")

    # アプリ側の通り番号（交差点が1つも無い通りを落とした後の番号）
    pairs = [tuple(int(v) for v in k.split(",")) for k in points]
    ns_map = {old: new for new, old in enumerate(sorted({i for i, _ in pairs}))}
    ew_map = {old: new for new, old in enumerate(sorted({j for _, j in pairs}))}

    lat_all = [p[0] for p in points.values()]
    lon_all = [p[1] for p in points.values()]
    margin_lat = RADIUS / M_PER_LAT
    margin_lon = RADIUS / M_PER_LON
    box = (min(lat_all) - margin_lat, max(lat_all) + margin_lat,
           min(lon_all) - margin_lon, max(lon_all) + margin_lon)

    verts, offsets = load_rings(box)
    print(f"面 {len(offsets) - 1:,} / 頂点 {len(verts):,}")
    table, lats, lons, tops = build_index(verts, offsets)

    def azimuth_to(landmark, lat, lon, hits):
        if landmark["kind"] == "range":
            a, b = landmark["ends"]["from"], landmark["ends"]["to"]
            t = (sum(hits) / len(hits)) / 20.0 if hits else 0.5
            target = (a["lat"] + (b["lat"] - a["lat"]) * t,
                      a["lon"] + (b["lon"] - a["lon"]) * t)
        else:
            target = (landmark["lat"], landmark["lon"])
        return int(math.degrees(math.atan2((target[1] - lon) * M_PER_LON,
                                           (target[0] - lat) * M_PER_LAT)) % 360)

    OUT.mkdir(parents=True, exist_ok=True)
    index_out, total_bytes, faces = {}, 0, 0
    keys = [k for k in points if k in horizon]
    for count, key in enumerate(keys, start=1):
        lat, lon = points[key]
        cue = None
        for landmark in landmarks:
            seen = view.get(landmark["id"], {}).get(key)
            if seen:
                hits = seen if isinstance(seen, list) else []
                cue = (landmark, azimuth_to(landmark, lat, lon, hits))
                break
        if cue is None:
            continue
        landmark, azimuth = cue
        px, py = to_cell(lat, lon)
        svg, n = scene(lat, lon, float(terrain[py, px]), azimuth, horizon[key],
                       verts, offsets, table, lats, lons, tops)
        i, j = (int(v) for v in key.split(","))
        name = f"{ns_map[i]}_{ew_map[j]}.svg"
        (OUT / name).write_text(svg, encoding="utf-8")
        index_out[f"{ns_map[i]},{ew_map[j]}"] = {
            "file": name, "landmark": landmark["id"],
            "name": landmark["name"], "azimuth": azimuth,
        }
        total_bytes += len(svg)
        faces += n
        if count % 50 == 0 or count == len(keys):
            print(f"  [{count}/{len(keys)}]", flush=True)

    (OUT / "index.json").write_text(json.dumps(index_out, ensure_ascii=False),
                                    encoding="utf-8")
    n = len(index_out)
    print(f"\n{n} 視点  合計 {total_bytes / 1e6:.1f} MB"
          f"（1視点 {total_bytes / max(n, 1) / 1024:.0f} KB / 面 {faces // max(n, 1)} 枚）")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
