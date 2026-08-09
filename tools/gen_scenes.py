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

# 何がどれか分かるように、領域を塗り分ける
SKY = (220, 233, 242)
GROUND = (232, 228, 221)
MOUNTAIN = (108, 132, 148)
BUILDING = (168, 164, 156)
# 面の向きで陰影を付ける。上・左手前から当たる光
LIGHT = (-0.42, 0.25, 0.87)
HAZE_FROM, HAZE_TO = 40.0, 900.0    # この距離で空の色に溶けきる
RIDGE_MIN = 0.05       # ほぼ地平線上の微小な地形ノイズは山として塗らない


def blend(colour, other, t):
    return tuple(round(a + (b - a) * t) for a, b in zip(colour, other))


def tone(colour, level):
    return tuple(min(255, round(c * level)) for c in colour)


def hazed(colour, distance):
    t = min(max((distance - HAZE_FROM) / (HAZE_TO - HAZE_FROM), 0.0), 1.0)
    return "#%02x%02x%02x" % blend(colour, SKY, t * 0.72)


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

    sky = "#%02x%02x%02x" % SKY
    parts = [f'<svg viewBox="0 0 {WIDTH} {HEIGHT}" xmlns="http://www.w3.org/2000/svg">',
             f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{sky}"/>',
             f'<rect y="{CY:.0f}" width="{WIDTH}" height="{HEIGHT}" '
             f'fill="#%02x%02x%02x"/>' % GROUND]

    # 山。**建物を無視した地形だけの稜線**を連続して描く。
    # 尾根は建物の裏でも続いているので、断片で描くと山が切れて見える。
    # 手前の建物は後から重ねるので、隠れるべき部分は自然に隠れる。
    heights = profile.get("ridge") or profile["elevation"]
    run = []
    for offset in list(range(-40, 41)) + [None]:
        height = 0.0
        if offset is not None:
            a = (azimuth + offset) % 360
            height = heights[a]
            if profile["kind"][a] == 2:
                height = max(height, profile["elevation"][a])
        if offset is not None and height > RIDGE_MIN:
            run.append((CX + math.tan(math.radians(offset)) * FOCAL,
                        CY - math.tan(math.radians(height)) * FOCAL))
            continue
        if len(run) > 1:
            ridge = " ".join(f"{x:.0f},{y:.0f}" for x, y in run)
            parts.append(f'<polygon points="{run[0][0]:.0f},{CY:.0f} {ridge} '
                         f'{run[-1][0]:.0f},{CY:.0f}" fill="#%02x%02x%02x"/>' % MOUNTAIN)
            parts.append(f'<polyline points="{ridge}" fill="none" stroke="#3d5a6b" '
                         f'stroke-width="1.6"/>')
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
        nz = np.sum((ex - rx) * (ny_ + ry))
        if ex.mean() * nx + ny_.mean() * nyv > 0:
            continue
        # 面の向きで明るさを決める。屋根は明るく、光に背を向けた壁は暗く
        length = math.sqrt(nx * nx + nyv * nyv + nz * nz) or 1.0
        lambert = max(0.0, (nx * LIGHT[0] + nyv * LIGHT[1] + nz * LIGHT[2]) / length)
        level = 0.62 + 0.44 * lambert

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
        shapes.append((float(depth.mean()), level,
                       " ".join(f"{x:.0f},{y:.0f}" for x, y in zip(xs, ys))))

    # 塗りと線の太さが同じものを <g> でまとめる。1枚ずつ属性を書くと容量が倍増する
    current = None
    for depth, level, points in sorted(shapes, key=lambda s: -s[0]):
        width = "1.2" if depth < 60 else ("0.8" if depth < 150 else "0.5")
        # 明るさも距離も段階に丸める。連続値のままだと面ごとに色が変わり、
        # <g> でまとめられなくなって容量が倍増する
        band = round(depth / RADIUS * 8) / 8 * RADIUS
        fill = hazed(tone(BUILDING, round(level * 10) / 10), band)
        if (fill, width) != current:
            if current is not None:
                parts.append("</g>")
            parts.append(f'<g fill="{fill}" stroke="#4a5058" stroke-linejoin="round" '
                         f'stroke-width="{width}">')
            current = (fill, width)
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
