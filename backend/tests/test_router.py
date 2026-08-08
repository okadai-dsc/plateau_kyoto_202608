from __future__ import annotations

import pytest

from backend.app.errors import RouteNotFound, SameLocation
from .conftest import make_route_service, write_grid_data


def directions(response):
    return [move["direction"] for move in response["moves"]]


def test_result_is_two_directions_with_counts_not_a_route(tmp_path):
    """経路ではなく「方角 × 本数」を返すこと。

    碁盤の目では上ル/下ル と 東入ル/西入ル をどの順に消化しても着くので、
    順番は指定しない（docs/SPEC.md 3.5）。ここが本企画の核。
    """
    write_grid_data(tmp_path, ns_count=4, ew_count=4, tower=(1, 3))
    service = make_route_service(tmp_path)

    response = service.build_route_response(
        {"ns": "ns-01", "ew": "ew-03"},
        {"ns": "ns-03", "ew": "ew-00"},
    )

    assert "routes" not in response          # 経路候補は返さない
    assert len(response["moves"]) == 2
    assert directions(response) == ["上ル", "西入ル"]
    assert [move["count"] for move in response["moves"]] == [3, 2]
    assert response["moves"][0]["to_street"] == "ew-00"
    assert response["moves"][1]["to_street"] == "ns-03"


def test_single_direction_when_only_one_axis_differs(tmp_path):
    write_grid_data(tmp_path, ns_count=4, ew_count=4, tower=(1, 3))
    service = make_route_service(tmp_path)

    response = service.build_route_response(
        {"ns": "ns-01", "ew": "ew-03"},
        {"ns": "ns-01", "ew": "ew-00"},
    )

    assert len(response["moves"]) == 1
    assert directions(response) == ["上ル"]


def test_all_four_kyoto_directions_are_produced(tmp_path):
    """上ル / 下ル / 東入ル / 西入ル がすべて出ること。"""
    write_grid_data(tmp_path, ns_count=4, ew_count=4, tower=(1, 3))
    service = make_route_service(tmp_path)

    north_east = service.build_route_response(
        {"ns": "ns-02", "ew": "ew-02"}, {"ns": "ns-00", "ew": "ew-00"})
    south_west = service.build_route_response(
        {"ns": "ns-00", "ew": "ew-00"}, {"ns": "ns-02", "ew": "ew-02"})

    assert directions(north_east) == ["上ル", "東入ル"]
    assert directions(south_west) == ["下ル", "西入ル"]


def test_counts_come_from_the_street_order_so_they_do_not_depend_on_the_path(tmp_path):
    """本数は通り順の差。途中の交差点が欠けていても変わらない。

    順番を決めない以上、実際に横切る本数は道によって変わってしまうため、
    数え歌の並びでの本数を目安として返す。
    """
    exists = [[True] * 3 for _ in range(4)]
    exists[1][2] = False   # 途中の交差点を落とす
    write_grid_data(tmp_path, ns_count=3, ew_count=4, tower=(1, 3), exists=exists)
    service = make_route_service(tmp_path)

    response = service.build_route_response(
        {"ns": "ns-02", "ew": "ew-03"},
        {"ns": "ns-02", "ew": "ew-00"},
    )

    assert response["moves"][0]["count"] == 3


def test_errors_when_neither_order_can_turn(tmp_path):
    """どちらの順序でも曲がる地点が無ければエラーになること。"""
    exists = [[True] * 3 for _ in range(3)]
    exists[2][0] = False   # 横から先に折れる場合の曲がり角
    exists[0][2] = False   # 縦から先に折れる場合の曲がり角
    write_grid_data(tmp_path, ns_count=3, ew_count=3, tower=(1, 2), exists=exists)
    service = make_route_service(tmp_path)

    with pytest.raises(RouteNotFound):
        service.build_route_response(
            {"ns": "ns-02", "ew": "ew-02"},
            {"ns": "ns-00", "ew": "ew-00"},
        )


def test_one_usable_turn_point_is_enough(tmp_path):
    """片方の順序で曲がれるなら成立すること。順番はユーザーが選ぶ。"""
    exists = [[True] * 3 for _ in range(3)]
    exists[2][0] = False
    write_grid_data(tmp_path, ns_count=3, ew_count=3, tower=(1, 2), exists=exists)
    service = make_route_service(tmp_path)

    response = service.build_route_response(
        {"ns": "ns-02", "ew": "ew-02"},
        {"ns": "ns-00", "ew": "ew-00"},
    )

    assert len(response["moves"]) == 2


def test_does_not_depend_on_default_grid_size(tmp_path):
    write_grid_data(tmp_path, ns_count=3, ew_count=3, tower=(1, 1))
    service = make_route_service(tmp_path)

    response = service.build_route_response(
        {"ns": "ns-02", "ew": "ew-02"},
        {"ns": "ns-00", "ew": "ew-00"},
    )

    assert {move["to_street"] for move in response["moves"]} == {"ns-00", "ew-00"}


def test_same_location_is_rejected(tmp_path):
    write_grid_data(tmp_path, ns_count=3, ew_count=3, tower=(1, 1))
    service = make_route_service(tmp_path)

    with pytest.raises(SameLocation):
        service.build_route_response(
            {"ns": "ns-01", "ew": "ew-01"},
            {"ns": "ns-01", "ew": "ew-01"},
        )
