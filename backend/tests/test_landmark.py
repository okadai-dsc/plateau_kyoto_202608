from __future__ import annotations

from backend.app.grid import Grid
from backend.app.landmark import LandmarkService
from .conftest import write_grid_data


def make(tmp_path, **kwargs):
    write_grid_data(tmp_path, **kwargs)
    grid = Grid(tmp_path)
    return LandmarkService(grid, tmp_path)


def test_bearing_covers_eight_directions(tmp_path):
    service = make(tmp_path, ns_count=3, ew_count=3, tower=(1, 1))
    tower = service.landmarks[0]

    cases = {
        (1, 0): "南", (1, 2): "北", (0, 1): "西", (2, 1): "東",
        (0, 0): "南西", (2, 0): "南東", (0, 2): "北西", (2, 2): "北東",
    }
    for (ns_index, ew_index), expected in cases.items():
        bearing, _ = service.bearing_and_distance(tower, ns_index, ew_index)
        assert bearing == expected, (ns_index, ew_index)


def test_bearing_uses_real_distance_not_the_sign_of_the_index(tmp_path):
    """添字の符号だけで判定すると、1本隣に立っただけで斜めになってしまう。

    遠くの目印に対して1本ずれても、実際にはほぼ真っ直ぐに見える。
    """
    service = make(tmp_path, ns_count=3, ew_count=21, tower=(1, 20))
    tower = service.landmarks[0]

    # 目印は 20本ぶん南、1本ぶん東。ほぼ真南に見えるはず
    bearing, distance = service.bearing_and_distance(tower, 2, 0)
    assert bearing == "南"
    assert round(distance) == 2403


def test_bearing_is_none_at_the_landmark_itself(tmp_path):
    service = make(tmp_path, ns_count=3, ew_count=3, tower=(1, 1))
    tower = service.landmarks[0]

    bearing, distance = service.bearing_and_distance(tower, 1, 1)
    assert bearing is None
    assert distance == 0


def test_visible_reads_the_matrix_for_each_landmark(tmp_path):
    visible = [[False, True], [False, False]]
    service = make(tmp_path, ns_count=2, ew_count=2, tower=(1, 1), visible=visible)

    assert service.visible("tower", 1, 0)
    assert not service.visible("tower", 0, 0)
    assert not service.visible("unknown", 1, 0)


def test_best_returns_the_most_precise_visible_cue(tmp_path):
    visible = [[False, False], [False, True]]
    service = make(tmp_path, ns_count=2, ew_count=2, tower=(1, 1), visible=visible)

    cue = service.best(1, 1)
    assert cue["kind"] == "point" and cue["id"] == "tower" and cue["layer"] == 1


def test_best_falls_through_when_the_landmark_is_not_visible(tmp_path):
    """見えない目印は飛ばす。テスト用データには下位の層が無いので何も返らない。"""
    visible = [[False, False], [False, True]]
    service = make(tmp_path, ns_count=2, ew_count=2, tower=(1, 1), visible=visible)

    assert service.best(0, 0)["kind"] == "none"


def test_best_withholds_the_bearing_when_the_landmark_is_too_close(tmp_path):
    """近すぎると見上げる形になり、水平方向の目印にならない。"""
    import json
    write_grid_data(tmp_path, ns_count=3, ew_count=3, tower=(1, 1))
    path = tmp_path / "streets.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["landmarks"][0]["min_distance"] = 500      # 120m 間隔なので隣は近すぎ扱い
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    service = LandmarkService(Grid(tmp_path), tmp_path)
    cue = service.best(1, 0)

    assert cue["kind"] == "point"
    assert cue["bearing"] is None          # 見えてはいるが方位には使わせない
    assert cue["distance"] == 120


MAJOR_STREET_LANDMARK = [
    {"id": "major_street", "name": "大きい通り", "layer": 4,
     "kind": "street", "max_distance": 1200}
]


def test_nearest_major_street_gives_a_real_bearing(tmp_path):
    """「大きい通り」は、置き換え前の「街区の形」と違って実際の方角を返す。"""
    service = make(tmp_path, ns_count=5, ew_count=5, tower=(0, 0),
                   major_ns=[4], major_ew=[0], landmarks=MAJOR_STREET_LANDMARK)
    # (2,2) から見て N4通 は西に240m、E0通 は北に240m。同距離なら先に見た方
    found = service.nearest_major_street(2, 2)
    assert found["bearing"] in ("北", "西")
    assert found["distance"] == 240


def test_nearest_major_street_picks_the_closest(tmp_path):
    service = make(tmp_path, ns_count=5, ew_count=5, tower=(0, 0),
                   major_ns=[0], major_ew=[3], landmarks=MAJOR_STREET_LANDMARK)
    # (2,2) から N0通 は東に240m、E3通 は南に120m → 近い南を選ぶ
    found = service.nearest_major_street(2, 2)
    assert found == {"name": "E3通", "bearing": "南", "distance": 120}


def test_severed_street_is_not_visible_through(tmp_path):
    """大通りとの交点が欠けている＝そこで通りが切れている（御所・二条城など）。"""
    exists = [[True] * 5 for _ in range(5)]
    exists[3][2] = False          # E3通 × N2通 が無い = N2通 は E3通 に届かない
    service = make(tmp_path, ns_count=5, ew_count=5, tower=(0, 0), exists=exists,
                   major_ns=[], major_ew=[3], landmarks=MAJOR_STREET_LANDMARK)
    assert service.nearest_major_street(2, 2) is None
    # 隣の通りからは見通せる
    assert service.nearest_major_street(1, 2)["name"] == "E3通"


def test_major_street_covers_almost_every_real_intersection():
    """実データで、ほぼ全ての交差点から方角が出ることを確かめる。

    置き換え前の「街区の形」は bearing を返さず、実在交差点の 47% が
    方角なしだった（docs/SPEC.md 2.4）。
    """
    grid = Grid()
    service = LandmarkService(grid)
    total = 0
    without_bearing = 0
    for ew in range(len(grid.ew_streets)):
        for ns in range(len(grid.ns_streets)):
            if not grid.exists_indices(ns, ew):
                continue
            total += 1
            if service.best(ns, ew).get("bearing") is None:
                without_bearing += 1
    assert total > 0
    assert without_bearing / total < 0.05
