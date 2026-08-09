#!/usr/bin/env python3
"""線画と、それを生成AIで写実化したものを並べるページを作る。

  python3 tools/gen_compare.py             # 目印ごとに代表を1枚ずつ
  python3 tools/gen_compare.py 12,5 3,8    # 交差点を指定
  → data/osm/compare.html
  → data/osm/scenes_png/{ns}_{ew}.png    生成AIに渡す入力

使い方:
  1. data/osm/scenes_png/ の PNG を生成AIに渡す
  2. ページに載っているプロンプトで写実化させる
  3. 結果を data/osm/generated/{ns}_{ew}.png に保存
  4. ページをリロードすると左右に並ぶ

**説明資料用。アプリでは使わない。**
生成画像は実在しない建物を描くので、実景と見比べる道具にはならない
（docs/SPEC.md 2.6）。アプリが出すのは線画そのもの。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cairosvg

ROOT = Path(__file__).resolve().parent.parent
OSM = ROOT / "data" / "osm"
SCENES = ROOT / "backend" / "app" / "data" / "scenes"
PNG_IN = OSM / "scenes_png"
GENERATED = OSM / "generated"
PNG_WIDTH = 1400

PROMPT = """この線画は、京都の交差点に立って前を見た視界です。
3D都市モデル（建物の輪郭）から生成したものです。

構図・建物の輪郭・稜線の位置を**厳密に保ったまま**、写実的な写真風にしてください。

- 京都の街並み。2〜4階建ての町家や小さなビル、電線、アスファルトの通り
- 濃い線は遠景の山の稜線。その位置と形は変えない
- 建物の輪郭を勝手に足したり消したりしない
- 人や車は入れない
- 曇りの日中、自然光"""


def main() -> int:
    index = json.loads((SCENES / "index.json").read_text(encoding="utf-8"))
    streets = json.loads((ROOT / "backend" / "app" / "data" / "streets.json")
                         .read_text(encoding="utf-8"))
    ns_names = {s["index"]: s["name"] for s in streets["ns"]}
    ew_names = {s["index"]: s["name"] for s in streets["ew"]}

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        keys = [k for k in args if k in index]
        for k in (a for a in args if a not in index):
            print(f"  {k}: 線画がありません")
    else:
        by_landmark: dict[str, list[str]] = {}
        for key, entry in index.items():
            by_landmark.setdefault(entry["landmark"], []).append(key)
        keys = []
        for group in by_landmark.values():
            group.sort(key=lambda k: -(SCENES / index[k]["file"]).stat().st_size)
            keys.append(group[0])

    PNG_IN.mkdir(parents=True, exist_ok=True)
    GENERATED.mkdir(parents=True, exist_ok=True)

    rows = []
    for key in keys:
        entry = index[key]
        ns_index, ew_index = (int(v) for v in key.split(","))
        name = f"{ns_index}_{ew_index}"
        where = f"{ns_names[ns_index]} × {ew_names[ew_index]}"

        # 生成AIに渡す入力を書き出す
        cairosvg.svg2png(url=str(SCENES / entry["file"]),
                         write_to=str(PNG_IN / f"{name}.png"),
                         output_width=PNG_WIDTH, background_color="white")

        svg = (SCENES / entry["file"]).read_text(encoding="utf-8")
        rows.append(f"""
<section>
  <h2>{where}</h2>
  <p class="sub">目印 <b>{entry['name']}</b>／方位 {entry['azimuth']}°</p>
  <div class="pair">
    <figure>
      <div class="line">{svg}</div>
      <figcaption>PLATEAU から計算した線画（これがアプリに出る）</figcaption>
    </figure>
    <figure>
      <div class="shot">
        <img src="generated/{name}.png" alt=""
             onerror="this.closest('.shot').classList.add('empty')">
        <p class="todo">
          入力 <code>data/osm/scenes_png/{name}.png</code><br>
          出力 <code>data/osm/generated/{name}.png</code> に保存してリロード
        </p>
      </div>
      <figcaption>生成AIで写実化（イメージ）</figcaption>
    </figure>
  </div>
</section>""")

    html = f"""<!doctype html><meta charset="utf-8">
<title>線画と写実化の比較</title>
<style>
 body {{ font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 1200px;
        color: #1f2328; background: #f7f5f2; padding: 0 1rem; }}
 h1 {{ font-size: 1.2rem; }}
 h2 {{ font-size: 1rem; margin: 0 0 .15rem; }}
 .sub {{ margin: 0 0 .5rem; color: #6b7480; font-size: .8rem; }}
 .pair {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
 @media (max-width: 780px) {{ .pair {{ grid-template-columns: 1fr; }} }}
 figure {{ margin: 0; }}
 figcaption {{ margin-top: .3rem; font-size: .75rem; color: #6b7480;
               text-align: center; }}
 .shot, .line {{ border: 1px solid #dcd6cc; border-radius: 6px; background: #fff;
                 aspect-ratio: 900 / 480; overflow: hidden; position: relative; }}
 .shot img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
 .shot .todo {{ display: none; }}
 .shot.empty img {{ display: none; }}
 .shot.empty .todo {{ position: absolute; inset: 0; margin: 0; display: flex;
                      flex-direction: column; justify-content: center;
                      text-align: center; font-size: .78rem; color: #6b7480;
                      line-height: 1.9; padding: 1rem; }}
 .line svg {{ width: 100%; height: 100%; display: block; }}
 code {{ font-size: .78em; background: #eee9e2; padding: .1em .35em;
         border-radius: 3px; }}
 section {{ margin-bottom: 2rem; }}
 .note {{ font-size: .82rem; color: #6b7480; line-height: 1.8; }}
 .prompt {{ background: #fff; border: 1px solid #dcd6cc; border-radius: 6px;
            padding: .9rem 1rem; white-space: pre-wrap; font-size: .8rem;
            line-height: 1.8; margin: .5rem 0 1.5rem; }}
 button {{ font: inherit; padding: .3rem .8rem; border: 1px solid #c9c0b2;
           border-radius: 6px; background: #fff; cursor: pointer; }}
</style>
<h1>線画と、生成AIで写実化したもの</h1>
<p class="note">
 <code>data/osm/scenes_png/</code> の PNG を生成AIに渡し、下のプロンプトで写実化して
 <code>data/osm/generated/</code> に保存するとここに並ぶ。<br>
 <b>説明資料用。</b>生成画像は実在しない建物を描くので、アプリには載せない
 （アプリが出すのは線画そのもの）。
</p>
<button onclick="navigator.clipboard.writeText(document.getElementById('p').textContent)">
 プロンプトをコピー</button>
<div class="prompt" id="p">{PROMPT}</div>
{"".join(rows)}
"""
    path = OSM / "compare.html"
    path.write_text(html, encoding="utf-8")
    print(f"wrote {path}")
    print(f"入力の PNG: {PNG_IN.relative_to(ROOT)}")
    for key in keys:
        entry = index[key]
        ns_index, ew_index = (int(v) for v in key.split(","))
        print(f"  {ns_names[ns_index]} × {ew_names[ew_index]}"
              f"  {entry['name']}  → {ns_index}_{ew_index}.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
