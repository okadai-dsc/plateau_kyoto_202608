#!/usr/bin/env python3
"""OpenStreetMap から洛中の通りの形状を取ってくる。

PLATEAU の道路データ（tran）には通り名が入っていないため、通り名と形状は OSM から取る。
交差点の座標を出す土台になる。出力は data/osm/streets.json（Git管理外）。

  python3 tools/fetch_osm_streets.py
"""

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tools" / "kyoto_streets.json"
OUT_DIR = ROOT / "data" / "osm"

# 公開サーバは重いクエリを 504 で切るので、分割して投げ、失敗したら別サーバを試す
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
BATCH = 6          # 一度に問い合わせる通りの本数
RETRIES = 3

# 洛中（北大路〜十条、東大路〜西大路）を余裕をもって囲む
BBOX = (34.965, 135.700, 35.055, 135.800)


def street_names() -> list[str]:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    return [s["name"] for s in source["ns"]] + [s["name"] for s in source["ew"]]


def request_once(endpoint: str, names: list[str]) -> dict:
    pattern = "^(" + "|".join(names) + ")$"
    query = (
        "[out:json][timeout:120];"
        f'way["highway"]["name"~"{pattern}"]'
        f"({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});"
        "out geom;"
    )
    data = urllib.parse.urlencode({"data": query}).encode()
    # User-Agent が無いと Overpass は 406 を返す
    request = urllib.request.Request(
        endpoint,
        data=data,
        headers={"User-Agent": "kyoter/0.1 (Kyoto street grid research)"},
    )
    with urllib.request.urlopen(request, timeout=180) as res:
        return json.load(res)


def fetch(names: list[str]) -> list[dict]:
    ways: list[dict] = []
    batches = [names[i:i + BATCH] for i in range(0, len(names), BATCH)]

    for index, batch in enumerate(batches, start=1):
        for attempt in range(1, RETRIES + 1):
            endpoint = OVERPASS_ENDPOINTS[(attempt - 1) % len(OVERPASS_ENDPOINTS)]
            try:
                got = request_once(endpoint, batch).get("elements", [])
                ways.extend(got)
                print(f"  [{index}/{len(batches)}] {len(got):>4} way  {' '.join(batch)}", flush=True)
                break
            except Exception as error:              # noqa: BLE001
                print(f"  [{index}/{len(batches)}] 失敗({attempt}/{RETRIES}) {error}", flush=True)
                if attempt == RETRIES:
                    print(f"      → あきらめ: {' '.join(batch)}", flush=True)
                time.sleep(5 * attempt)
        time.sleep(2)                                # 公開サーバへの配慮
    return ways


def main() -> None:
    names = street_names()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    started = time.time()
    print(f"Overpass に問い合わせ中… 通り {len(names)}本", flush=True)
    ways = fetch(names)
    print(f"\n合計 {len(ways)} way / {time.time() - started:.0f}秒")

    # 通り名ごとに折れ線をまとめる
    lines: dict[str, list[list[list[float]]]] = {}
    for way in ways:
        name = way.get("tags", {}).get("name")
        geometry = way.get("geometry")
        if not name or not geometry:
            continue
        lines.setdefault(name, []).append([[p["lat"], p["lon"]] for p in geometry])

    found = [n for n in names if n in lines]
    missing = [n for n in names if n not in lines]

    out = OUT_DIR / "streets.json"
    out.write_text(json.dumps(lines, ensure_ascii=False), encoding="utf-8")
    print(f"\n見つかった通り: {len(found)}/{len(names)}")
    print(f"wrote {out.relative_to(ROOT)}  ({out.stat().st_size / 1e6:.1f}MB)")
    if missing:
        print(f"\n見つからなかった通り（{len(missing)}）:")
        print("  " + " ".join(missing))


if __name__ == "__main__":
    main()
