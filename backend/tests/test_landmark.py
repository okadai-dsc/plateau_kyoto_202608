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
