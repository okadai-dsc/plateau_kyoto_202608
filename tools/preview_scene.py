#!/usr/bin/env python3
"""交差点に立って目印の方を見た景色を、線画で描く。

  python3 tools/calc_horizon.py     # 先に地平線プロファイル
  python3 tools/preview_scene.py    # ここ
  → data/osm/scene_preview.html をブラウザで開く

PLATEAU の LOD1 は建物を箱として持っているので、目線1.5mの位置から
透視投影すればそのまま線画になる。両側の建物が奥へ狭まり、突き当たりに
山が出る ── ストリートビューと同じ構図。

隠面は画家のアルゴリズム（遠い面から白く塗りつぶす）で処理する。
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLATEAU = ROOT / "data" / "plateau" / "udx" / "bldg"
OSM = ROOT / "data" / "osm"

M_PER_LAT = 111_132.0
M_PER_LON = 91_200.0

RADIUS = 180.0         # 描く範囲(m)。これ以上遠い建物は線が潰れる
MIN_AREA = 30.0        # 画面上でこれ以下(px^2)の面は捨てる
EYE = 1.5
HFOV = 72.0            # 横の視野角（人の視野に近い）
WIDTH, HEIGHT = 900, 480
CX, CY = WIDTH / 2, HEIGHT * 0.62      # 消失点。少し下げると見上げる感じになる
FOCAL = (WIDTH / 2) / math.tan(math.radians(HFOV / 2))
RIDGE_MIN = 0.05
RIDGE_BRIDGE_GAP = 10

POLYGON = re.compile(r"<gml:Polygon\b.*?</gml:Polygon>", re.S)
POSLIST = re.compile(r"<gml:posList[^>]*>([^<]+)</gml:posList>")
ENVELOPE = re.compile(r"<gml:(lower|upper)Corner>([\d.\- ]+)</gml:\1Corner>")


def envelope(path):
    head = path.open(encoding="utf-8", errors="replace").read(4000)
    found = ENVELOPE.findall(head)
    if len(found) < 2:
        return None
    a = [float(v) for v in found[0][1].split()]
    b = [float(v) for v in found[1][1].split()]
    return a[0], b[0], a[1], b[1]


def faces_near(lat, lon):
    """視点のまわりの建物の面を集める。"""
    dlat = RADIUS / M_PER_LAT
    dlon = RADIUS / M_PER_LON
    box = (lat - dlat, lat + dlat, lon - dlon, lon + dlon)
    out = []
    for path in sorted(PLATEAU.glob("*.gml")):
        env = envelope(path)
        if not env or env[1] < box[0] or env[0] > box[1] \
                or env[3] < box[2] or env[2] > box[3]:
            continue
        text = path.open(encoding="utf-8", errors="replace").read()
        for chunk in POLYGON.finditer(text):
            match = POSLIST.search(chunk.group(0))
            if not match:
                continue
            values = match.group(1).split()
            ring = [(float(values[i]), float(values[i + 1]), float(values[i + 2]))
                    for i in range(0, len(values) - 2, 3)]
            if len(ring) < 3:
                continue
            if not any(box[0] <= p[0] <= box[1] and box[2] <= p[1] <= box[3]
                       for p in ring):
                continue
            out.append(ring)
    return out


def facing_away(ring, lat, lon):
    """視点に背を向けている面か。CityGML の外周は外から見て反時計回り。

    奥の壁は必ず手前の壁に隠れるので、描かなくても絵は変わらない。
    """
    nx = ny = nz = 0.0
    for a, b in zip(ring, ring[1:] + ring[:1]):
        ax, ay, az = (a[1] - lon) * M_PER_LON, (a[0] - lat) * M_PER_LAT, a[2]
        bx, by, bz = (b[1] - lon) * M_PER_LON, (b[0] - lat) * M_PER_LAT, b[2]
        nx += (ay - by) * (az + bz)
        ny += (az - bz) * (ax + bx)
        nz += (ax - bx) * (ay + by)
    # 面の中心へのベクトルと法線が同じ向き＝裏
    cx = sum((p[1] - lon) * M_PER_LON for p in ring) / len(ring)
    cy = sum((p[0] - lat) * M_PER_LAT for p in ring) / len(ring)
    return cx * nx + cy * ny > 0


def project(point, origin, ground, forward, right):
    """緯度経度標高 → 画面座標。カメラの後ろなら None。"""
    north = (point[0] - origin[0]) * M_PER_LAT
    east = (point[1] - origin[1]) * M_PER_LON
    depth = east * forward[0] + north * forward[1]
    if depth < 1.0:
        return None
    side = east * right[0] + north * right[1]
    up = point[2] - (ground + EYE)
    return (CX + side / depth * FOCAL, CY - up / depth * FOCAL, depth)


def ridge_heights(profile, azimuth):
    heights = profile.get("ridge") or profile["elevation"]
    offsets = list(range(-40, 41))
    values = []
    for offset in offsets:
        a = (azimuth + offset) % 360
        height = heights[a]
        if profile["kind"][a] == 2:
            height = max(height, profile["elevation"][a])
        values.append(height if height > RIDGE_MIN else 0.0)

    index = 0
    while index < len(values):
        if values[index] > 0.0:
            index += 1
            continue
        start = index
        while index < len(values) and values[index] == 0.0:
            index += 1
        gap = index - start
        if start == 0 or index == len(values) or gap > RIDGE_BRIDGE_GAP:
            continue
        left, right = values[start - 1], values[index]
        for step in range(gap):
            t = (step + 1) / (gap + 1)
            values[start + step] = left + (right - left) * t
    return zip(offsets, values)


def draw(lat, lon, ground, azimuth, profile, label):
    angle = math.radians(azimuth)
    forward = (math.sin(angle), math.cos(angle))
    right = (math.cos(angle), -math.sin(angle))

    parts = [f'<svg viewBox="0 0 {WIDTH} {HEIGHT}" class="scene">',
             f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#fff"/>']

    # 山の稜線。建物を無視した地形だけの稜線を同じカメラに乗せる
    ridge = []
    for offset, height in ridge_heights(profile, azimuth):
        if height <= RIDGE_MIN:
            ridge.append(None)
            continue
        x = CX + math.tan(math.radians(offset)) * FOCAL
        y = CY - math.tan(math.radians(height)) * FOCAL
        ridge.append((x, y))
    run = []
    for point in ridge + [None]:
        if point is None:
            if len(run) > 1:
                d = " ".join(f"{x:.1f},{y:.1f}" for x, y in run)
                parts.append(f'<polyline points="{d}" class="ridge"/>')
            run = []
        else:
            run.append(point)

    # 建物。遠い面から白く塗って線を描くと、手前が奥を隠す
    eye_z = ground + EYE
    shapes = []
    for ring in faces_near(lat, lon):
        # 足元の面（地面と接する多角形）は必ず隠れるので描かない
        if max(p[2] for p in ring) <= eye_z:
            continue
        if facing_away(ring, lat, lon):
            continue
        pts = [project(p, (lat, lon), ground, forward, right) for p in ring]
        if any(p is None for p in pts) or len(pts) < 3:
            continue
        depth = sum(p[2] for p in pts) / len(pts)
        if depth > RADIUS:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        if max(xs) < 0 or min(xs) > WIDTH or min(ys) > HEIGHT:
            continue
        # 画面上で小さすぎる面は線が潰れるだけなので捨てる
        area = abs(sum(xs[i] * ys[i - 1] - xs[i - 1] * ys[i]
                       for i in range(len(xs)))) / 2
        if area < MIN_AREA:
            continue
        shapes.append((depth, " ".join(f"{x:.0f},{y:.0f}" for x, y in zip(xs, ys))))
    for depth, points in sorted(shapes, key=lambda s: -s[0]):
        width = 1.4 if depth < 60 else (1.0 if depth < 150 else 0.6)
        parts.append(f'<polygon points="{points}" fill="#fff" stroke="#232a30" '
                     f'stroke-width="{width}" stroke-linejoin="round"/>')

    parts.append(f'<line x1="0" y1="{CY:.0f}" x2="{WIDTH}" y2="{CY:.0f}" class="eye"/>')
    parts.append(f'<text x="{CX}" y="24" class="pin">↓ {label}</text>')
    parts.append(f'<line x1="{CX}" y1="30" x2="{CX}" y2="{CY:.0f}" class="aim"/>')
    parts.append("</svg>")
    return "".join(parts)


def main() -> int:
    horizon = json.loads((OSM / "horizon.json").read_text(encoding="utf-8"))["horizon"]
    inter = json.loads((OSM / "intersections.json").read_text(encoding="utf-8"))
    view = json.loads((OSM / "viewshed.json").read_text(encoding="utf-8"))["visible"]
    source = json.loads((ROOT / "tools" / "kyoto_streets.json").read_text(encoding="utf-8"))
    ns_names, ew_names = inter["ns"], inter["ew"]
    points = inter["intersections"]
    landmarks = sorted(source["landmarks"], key=lambda l: l["layer"])

    import numpy as np
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from calc_viewshed import to_cell, OSM_DIR
    terrain = np.load(OSM_DIR / "grid_terrain.npy")

    def azimuth_to(landmark, lat, lon, hits):
        if landmark["kind"] == "range":
            a, b = landmark["ends"]["from"], landmark["ends"]["to"]
            t = (sum(hits) / len(hits)) / 20.0 if hits else 0.5
            target = (a["lat"] + (b["lat"] - a["lat"]) * t,
                      a["lon"] + (b["lon"] - a["lon"]) * t)
        else:
            target = (landmark["lat"], landmark["lon"])
        dy = (target[0] - lat) * M_PER_LAT
        dx = (target[1] - lon) * M_PER_LON
        return int(math.degrees(math.atan2(dx, dy)) % 360)

    wanted = sys.argv[1:] or ["新町通,今出川通", "堺町通,丸太町通", "釜座通,御池通"]
    cards = []
    for spec in wanted:
        a, b = spec.split(",")
        i, j = ns_names.index(a), ew_names.index(b)
        key = f"{i},{j}"
        if key not in horizon:
            print(f"  {spec}: 交差点が無い")
            continue
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
        ground = float(terrain[py, px])
        print(f"  {a} × {b}  基準={landmark['name']} 方位{azimuth}°", flush=True)
        cards.append(f'<section><h2>{a} × {b}</h2>'
                     f'<p class="sub">目印 <b>{landmark["name"]}</b> の方（方位 {azimuth}°）'
                     f'を向いたところ</p>'
                     + draw(lat, lon, ground, azimuth, horizon[key], landmark["name"])
                     + "</section>")

    html = f"""<!doctype html><meta charset="utf-8">
<title>その場に立った景色</title>
<style>
 body {{ font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 960px;
        color: #1f2328; background: #fff; }}
 h1 {{ font-size: 1.15rem; }}
 h2 {{ font-size: 1rem; margin: 0 0 .15rem; }}
 .sub {{ margin: 0 0 .4rem; color: #6b7480; font-size: .8rem; }}
 .scene {{ width: 100%; height: auto; border: 1px solid #d8d2c8; }}
 .ridge {{ fill: none; stroke: #1c4a5a; stroke-width: 2.4; }}
 .eye {{ stroke: #cfd6db; stroke-dasharray: 3 5; }}
 .aim {{ stroke: #c0392b; stroke-dasharray: 4 4; opacity: .55; }}
 .pin {{ font-size: 14px; font-weight: 700; text-anchor: middle; fill: #c0392b; }}
 section {{ margin-bottom: 1.8rem; }}
 .note {{ font-size: .8rem; color: #6b7480; }}
</style>
<h1>その交差点に立って、目印の方を見た景色</h1>
<p class="note">PLATEAU の建物モデル(LOD1)を目線1.5mから透視投影した線画。
 色は付けていない。濃い線が山の稜線。赤い破線が目印の方位。視野 {HFOV:.0f}°。</p>
{"".join(cards)}
"""
    path = OSM / "scene_preview.html"
    path.write_text(html, encoding="utf-8")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
