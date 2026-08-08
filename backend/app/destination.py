from __future__ import annotations

import math
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from .errors import DestinationOutOfRange, DestinationResolveError
from .grid import Grid

COORDINATE_PAIR_RE = re.compile(
    r"(?<![\d.])(-?\d{1,3}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)(?![\d.])"
)


class DestinationResolver:
    """Google Maps の共有リンクを Kyoter の交差点へ翻訳する。"""

    def __init__(
        self,
        grid: Grid,
        *,
        timeout: float = 5.0,
        max_snap_distance_m: float = 900.0,
    ) -> None:
        self.grid = grid
        self.timeout = timeout
        self.max_snap_distance_m = max_snap_distance_m

    def resolve(self, raw_url: str) -> dict[str, Any]:
        text = raw_url.strip()
        if not text:
            raise DestinationResolveError("Google Mapsリンクを貼ってください")

        lat_lng = self._extract_lat_lng(text)
        expanded_url = None
        if lat_lng is None and self._can_expand(text):
            expanded_url, expanded_text = self._expand(text)
            lat_lng = self._extract_lat_lng(expanded_url) or self._extract_lat_lng(expanded_text)

        if lat_lng is None:
            raise DestinationResolveError()

        lat, lng = lat_lng
        x, y = self._lat_lng_to_xy(lat, lng)
        candidates = self._nearest_candidates(x, y, limit=3)
        if not candidates or candidates[0]["distance_m"] > self.max_snap_distance_m:
            raise DestinationOutOfRange()

        best = candidates[0]
        return {
            "source": "google_maps_url",
            "input": {"lat": round(lat, 7), "lng": round(lng, 7)},
            "destination": best["at"],
            "label": f'{best["label"]} 付近',
            "distance_m": best["distance_m"],
            "candidates": candidates,
            "expanded_url": expanded_url,
        }

    def _expand(self, url: str) -> tuple[str, str]:
        try:
            with httpx.Client(follow_redirects=True, timeout=self.timeout) as client:
                response = client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise DestinationResolveError("Google Mapsリンクを開けませんでした") from exc

        return str(response.url), response.text[:80_000]

    def _extract_lat_lng(self, text: str) -> tuple[float, float] | None:
        normalized = self._normalize(text)

        for pattern in (
            r"@(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)",
            r"!3d(-?\d+(?:\.\d+)?).*?!4d(-?\d+(?:\.\d+)?)",
        ):
            match = re.search(pattern, normalized)
            if match:
                lat_lng = self._valid_lat_lng(match.group(1), match.group(2))
                if lat_lng is not None:
                    return lat_lng

        match = re.search(r"!4d(-?\d+(?:\.\d+)?).*?!3d(-?\d+(?:\.\d+)?)", normalized)
        if match:
            lat_lng = self._valid_lat_lng(match.group(2), match.group(1))
            if lat_lng is not None:
                return lat_lng

        parsed = urlparse(normalized)
        for key in ("q", "query", "ll", "sll", "center"):
            for value in parse_qs(parsed.query).get(key, []):
                lat_lng = self._coordinate_pair(value)
                if lat_lng is not None:
                    return lat_lng

        return self._coordinate_pair(normalized)

    def _coordinate_pair(self, text: str) -> tuple[float, float] | None:
        for match in COORDINATE_PAIR_RE.finditer(text):
            lat_lng = self._valid_lat_lng(match.group(1), match.group(2))
            if lat_lng is not None:
                return lat_lng
        return None

    def _valid_lat_lng(self, lat_text: str, lng_text: str) -> tuple[float, float] | None:
        lat = float(lat_text)
        lng = float(lng_text)
        if -90 <= lat <= 90 and -180 <= lng <= 180:
            return lat, lng
        return None

    def _lat_lng_to_xy(self, lat: float, lng: float) -> tuple[float, float]:
        reference = self.grid.geo_reference
        if reference is None:
            raise DestinationResolveError("緯度経度の基準点が設定されていません")

        ref_ns = int(reference["ns"])
        ref_ew = int(reference["ew"])
        ref_x, ref_y = self.grid.position(ref_ns, ref_ew)
        ref_lat = float(reference["lat"])
        ref_lng = float(reference["lng"])
        meters_per_lat = 111_320.0
        meters_per_lng = meters_per_lat * math.cos(math.radians(ref_lat))

        x = ref_x + (ref_lng - lng) * meters_per_lng
        y = ref_y + (ref_lat - lat) * meters_per_lat
        return x, y

    def _nearest_candidates(self, x: float, y: float, *, limit: int) -> list[dict[str, Any]]:
        candidates = []
        for ew_street in self.grid.ew_streets:
            ew_index = int(ew_street["index"])
            for ns_street in self.grid.ns_streets:
                ns_index = int(ns_street["index"])
                if not self.grid.exists_indices(ns_index, ew_index):
                    continue
                street_x, street_y = self.grid.position(ns_index, ew_index)
                distance = math.hypot(x - street_x, y - street_y)
                label = f'{ns_street["name"]} × {ew_street["name"]}'
                candidates.append(
                    {
                        "at": self.grid.intersection_from_indices(ns_index, ew_index),
                        "label": label,
                        "distance_m": int(round(distance)),
                    }
                )

        return sorted(candidates, key=lambda item: item["distance_m"])[:limit]

    def _normalize(self, text: str) -> str:
        current = text
        for _ in range(3):
            decoded = unquote(current)
            if decoded == current:
                break
            current = decoded
        return current.replace("\\u003d", "=").replace("\\u0026", "&")

    def _can_expand(self, text: str) -> bool:
        parsed = urlparse(text)
        if parsed.scheme not in ("http", "https"):
            return False
        host = (parsed.hostname or "").lower().rstrip(".")
        return (
            host in {"maps.app.goo.gl", "goo.gl", "google.com", "www.google.com", "maps.google.com"}
            or host.endswith(".google.com")
            or host.endswith(".google.co.jp")
        )
