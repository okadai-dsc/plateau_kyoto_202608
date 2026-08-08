from __future__ import annotations

import pytest

from backend.app.destination import DestinationResolver
from backend.app.errors import DestinationOutOfRange, DestinationResolveError
from backend.app.grid import Grid


def make_resolver(repo_root) -> DestinationResolver:
    grid = Grid(repo_root / "backend" / "app" / "data")
    return DestinationResolver(grid)


def test_resolves_google_at_coordinates_to_nearest_intersection(repo_root):
    resolver = make_resolver(repo_root)

    response = resolver.resolve("https://www.google.com/maps/@35.003678,135.759637,17z")

    assert response["destination"] == {"ns": "ns-12", "ew": "ew-12"}
    assert response["label"] == "烏丸通 × 四条通 付近"
    # 実データでは通りの位置が実測の中央値なので、数mのずれは出る。
    # 正しい交差点に寄っていることが要件で、完全一致は求めない
    assert response["distance_m"] < 30
    assert len(response["candidates"]) == 3


def test_resolves_google_data_coordinates(repo_root):
    resolver = make_resolver(repo_root)

    response = resolver.resolve("https://www.google.com/maps/place/foo/data=!3d35.003678!4d135.759637")

    assert response["destination"] == {"ns": "ns-12", "ew": "ew-12"}


def test_resolves_query_coordinates(repo_root):
    resolver = make_resolver(repo_root)

    response = resolver.resolve("https://www.google.com/maps/search/?api=1&query=35.003678,135.759637")

    assert response["destination"] == {"ns": "ns-12", "ew": "ew-12"}


def test_expands_short_google_url_without_real_network(repo_root, monkeypatch):
    resolver = make_resolver(repo_root)

    def fake_expand(_url: str) -> tuple[str, str]:
        return "https://www.google.com/maps/@35.003678,135.759637,17z", ""

    monkeypatch.setattr(resolver, "_expand", fake_expand)

    response = resolver.resolve("https://maps.app.goo.gl/example")

    assert response["destination"] == {"ns": "ns-12", "ew": "ew-12"}
    assert response["expanded_url"] == "https://www.google.com/maps/@35.003678,135.759637,17z"


def test_rejects_destination_outside_supported_grid(repo_root):
    resolver = make_resolver(repo_root)

    with pytest.raises(DestinationOutOfRange):
        resolver.resolve("https://www.google.com/maps/@35.681236,139.767125,17z")


def test_rejects_link_without_coordinates(repo_root):
    resolver = make_resolver(repo_root)

    with pytest.raises(DestinationResolveError):
        resolver.resolve("not a maps link")
