from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .grid import DATA_DIR


class SceneLibrary:
    """交差点ごとの線画（docs/SPEC.md 2.6 段階C）。

    その場に立って目印の方を見た景色を、PLATEAU の建物(LOD1)から
    透視投影した SVG。`tools/gen_scenes.py` が事前に作る。

    目印が一点として定まる交差点にしか無い。稜線や大きい通りが手がかりの
    交差点では線画を持たず、文章の指示だけになる。
    """

    def __init__(self, data_dir: Path | str = DATA_DIR) -> None:
        self.directory = Path(data_dir) / "scenes"
        index = self.directory / "index.json"
        self._index: dict[str, dict[str, Any]] = {}
        if index.is_file():
            self._index = json.loads(index.read_text(encoding="utf-8"))

    def info(self, ns_index: int, ew_index: int) -> dict[str, Any] | None:
        """その交差点の線画の情報。無ければ None。"""
        entry = self._index.get(f"{ns_index},{ew_index}")
        if entry is None:
            return None
        return {
            "url": f"/api/scene/{ns_index}/{ew_index}",
            "landmark": entry["landmark"],
            "name": entry["name"],
            "azimuth": entry["azimuth"],
        }

    def svg(self, ns_index: int, ew_index: int) -> str | None:
        entry = self._index.get(f"{ns_index},{ew_index}")
        if entry is None:
            return None
        path = self.directory / entry["file"]
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    @property
    def count(self) -> int:
        return len(self._index)
