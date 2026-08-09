#!/usr/bin/env python3
"""目印がどう見えるかを1枚もの HTML に書き出す。

  python3 tools/calc_horizon.py      # 先にこれ
  python3 tools/preview_horizon.py   # ここ
  → data/osm/horizon_preview.html をブラウザで開く

全方位は出さない。**基準にする目印のまわりだけ**を切り出して、
「建物の切れ目から、この形の山が見える」を見せる。

奥行きは距離で出す。近い建物ほど濃く大きく、遠い山ほど淡く霞ませる。
"""

from __future__ import annotations

import json
import math
import sys
from statistics import median
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OSM = ROOT / "data" / "osm"

FOV = 70               # 横の視野角（度）
VFOV = 22.0            # 縦の視野角（度）。これより上は画面外に切る
WIDTH = 900
HEIGHT = 300
HORIZON_Y = 250        # 地平線の位置。ここから上が VFOV ぶん

# 誇張はしない。実際に前を見たときと同じで、両側の建物は視界の上に外れ、
# 正面の隙間に数度の山が覗く。その構図をそのまま出す。
SCALE = HORIZON_Y / VFOV


def haze(distance, is_mountain):
    """距離で色を決める。遠いほど空に溶ける（空気遠近法）。"""
    far = min(max((distance - 200) / 12000.0, 0.0), 1.0)
    if is_mountain:
        base = (28, 62, 82)
    else:
        base = (46, 54, 62)
    sky = (214, 227, 235)
    return "#%02x%02x%02x" % tuple(
        round(b + (s - b) * (far * 0.82)) for b, s in zip(base, sky)
    )


def runs(profile, center):
    """視野内を、正体（山／建物）が変わるところで区切る。

    距離では切らない。切ると1度ごとの細切れになって輪郭が消えるため、
    色だけをその区間の距離で決める。
    """
    el, kd, dist = profile["elevation"], profile["kind"], profile["distance"]
    out = []
    for offset in range(-FOV // 2, FOV // 2 + 1):
        a = (center + offset) % 360
        if out and out[-1]["kind"] == kd[a]:
            out[-1]["points"].append((offset, el[a], dist[a]))
        else:
            out.append({"kind": kd[a], "points": [(offset, el[a], dist[a])]})
    return out


def draw(profile, center, label):
    scale = WIDTH / FOV
    top = -HEIGHT      # 画面外まで伸ばして上で切る
    parts = [f'<svg viewBox="0 0 {WIDTH} {HEIGHT}" class="view">',
             '<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">'
             '<stop offset="0" stop-color="#b9cfdd"/>'
             '<stop offset="1" stop-color="#eaf1f5"/></linearGradient>'
             f'<clipPath id="frame"><rect width="{WIDTH}" height="{HEIGHT}"/>'
             '</clipPath></defs>',
             f'<rect width="{WIDTH}" height="{HORIZON_Y}" fill="url(#sky)"/>',
             '<g clip-path="url(#frame)">']

    # 遠いものから描く。近いものが後から重なって手前に来る
    groups = [g for g in runs(profile, center) if g["kind"] != 0]
    for band in sorted(groups, key=lambda b: -median([d for _, _, d in b["points"]])):
        pts = band["points"]
        poly = [f"{(pts[0][0] + FOV / 2) * scale:.1f},{HORIZON_Y}"]
        for o, e, _ in pts:
            y = max(HORIZON_Y - e * SCALE, top)
            poly.append(f"{(o + FOV / 2) * scale:.1f},{y:.1f}")
        poly.append(f"{(pts[-1][0] + FOV / 2) * scale:.1f},{HORIZON_Y}")
        colour = haze(median([d for _, _, d in pts]), band["kind"] == 2)
        parts.append(f'<polygon points="{" ".join(poly)}" fill="{colour}"/>')
    parts.append("</g>")

    parts.append(f'<line x1="0" y1="{HORIZON_Y}" x2="{WIDTH}" y2="{HORIZON_Y}" '
                 f'stroke="#aeb8c0"/>')
    # 中央 = 目印の方位
    mid = WIDTH / 2
    parts.append(f'<line x1="{mid}" y1="0" x2="{mid}" y2="{HORIZON_Y}" '
                 f'stroke="#c0392b" stroke-dasharray="4 4" opacity=".7"/>')
    parts.append(f'<text x="{mid}" y="18" class="pin">{label}</text>')
    parts.append(f'<text x="8" y="{HEIGHT - 10}" class="deg">左 {FOV // 2}°</text>')
    parts.append(f'<text x="{WIDTH - 8}" y="{HEIGHT - 10}" class="deg" '
                 f'text-anchor="end">右 {FOV // 2}°</text>')
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
    M_PER_LAT, M_PER_LON = 111_132.0, 91_200.0

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

    cards = []
    for key, profile in horizon.items():
        lat, lon = points[key]
        for landmark in landmarks:
            seen = view.get(landmark["id"], {}).get(key)
            if not seen:
                continue
            hits = seen if isinstance(seen, list) else []
            center = azimuth_to(landmark, lat, lon, hits)
            i, j = (int(v) for v in key.split(","))
            mountain = sum(1 for o in range(-FOV // 2, FOV // 2 + 1)
                           if profile["kind"][(center + o) % 360] == 2)
            cards.append((mountain, landmark["name"],
                          f"{ns_names[i]} × {ew_names[j]}", center, profile, key))
            break

    cards.sort(key=lambda c: -c[0])
    picks = [cards[0], cards[len(cards) // 5], cards[len(cards) // 2],
             cards[len(cards) * 4 // 5], cards[-1]]

    html_cards = []
    for mountain, name, where, center, profile, key in picks:
        html_cards.append(
            f'<section><h2>{where}</h2>'
            f'<p class="sub">基準にする目印 <b>{name}</b>（方位 {center}°）／'
            f'視野の中で山が占めるのは {mountain}°</p>'
            + draw(profile, center, name) + "</section>")

    html = f"""<!doctype html><meta charset="utf-8">
<title>目印の見え方</title>
<style>
 body {{ font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 960px;
        color: #1f2328; background: #f7f5f2; }}
 h1 {{ font-size: 1.15rem; }}
 h2 {{ font-size: 1rem; margin: 0 0 .15rem; }}
 .sub {{ margin: 0 0 .4rem; color: #6b7480; font-size: .8rem; }}
 .view {{ width: 100%; height: auto; border: 1px solid #dcd6cc; border-radius: 8px; }}
 .pin {{ font-size: 15px; font-weight: 700; text-anchor: middle; fill: #c0392b; }}
 .deg {{ font-size: 12px; fill: #7b848c; }}
 section {{ margin-bottom: 1.5rem; }}
 .note {{ font-size: .8rem; color: #6b7480; }}
</style>
<h1>基準にする目印が、そこからどう見えるか</h1>
<p class="note">PLATEAU の建物（1m格子）と地形から計算。視野 横{FOV}°×縦{VFOV:.0f}°、
 <b>誇張なし</b>。両側の建物は実際の見え方どおり画面の上に外れる。
 <b>遠いものほど淡く</b>描いて奥行きを出している。赤い破線が目印の方位。</p>
{"".join(html_cards)}
"""
    path = OSM / "horizon_preview.html"
    path.write_text(html, encoding="utf-8")
    print(f"wrote {path}")
    for mountain, name, where, center, _, _ in picks:
        print(f"  {where}  基準={name} 方位{center}°  山が{mountain}°")
    return 0


if __name__ == "__main__":
    sys.exit(main())
