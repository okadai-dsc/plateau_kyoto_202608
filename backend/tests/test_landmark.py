from __future__ import annotations

from backend.app.grid import Grid
from backend.app.landmark import Landmark, LandmarkService
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
     "kind": "street", "max_distance": 600, "min_width": 15}
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


def test_narrow_street_is_not_a_traffic_cue(tmp_path):
    """幅で選ぶ。寺町通(8m)や三条通(8m)のように major でも車が通らない通りは使わない。"""
    service = make(tmp_path, ns_count=5, ew_count=5, tower=(0, 0),
                   major_ns=[], major_ew=[], landmarks=MAJOR_STREET_LANDMARK)
    # major がひとつも無い = すべて 8m = 車の流れを感じ取れる通りが無い
    assert service.nearest_major_street(2, 2) is None


def test_traffic_cue_is_dropped_when_too_far_to_notice(tmp_path):
    """遠すぎる大通りは、立った場所から気づけないので使わない。"""
    service = make(tmp_path, ns_count=12, ew_count=12, tower=(0, 0),
                   major_ns=[11], major_ew=[11], landmarks=MAJOR_STREET_LANDMARK)
    # (0,0) から N11通 / E11通 までは 1320m。既定の 600m を超える
    assert service.nearest_major_street(0, 0) is None
    # 600m 以内まで寄れば気づける
    assert service.nearest_major_street(7, 7)["distance"] == 480


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


def test_azimuth_is_finer_than_the_eight_directions():
    """図に置くための正確な方位(度)が、8方位に丸める前の値として返る。"""
    grid = Grid()
    service = LandmarkService(grid)
    ns = [s["name"] for s in grid.ns_streets]
    ew = [s["name"] for s in grid.ew_streets]
    cue = service.best(ns.index("川端通"), ew.index("丸太町通"))

    assert cue["name"] == "愛宕山"
    assert cue["bearing"] == "西"           # 8方位に丸めると西
    assert 270 < cue["azimuth"] < 315       # 実際は西より北寄り
    # 丸めた方位と食い違わないこと
    assert abs(((cue["azimuth"] - 270) + 180) % 360 - 180) <= 22.5


def test_mountains_are_low_and_wide():
    """山の仰角は数度しかない。描画で縦を誇張する必要がある根拠（SPEC 2.6）。"""
    grid = Grid()
    service = LandmarkService(grid)
    ns = [s["name"] for s in grid.ns_streets]
    ew = [s["name"] for s in grid.ew_streets]
    cue = service.best(ns.index("烏丸通"), ew.index("四条通"))
    assert cue["elevation"] is not None
    assert 0 < cue["elevation"] < 10


def test_peak_elevation_subtracts_ground_but_structure_does_not(tmp_path):
    """山は標高なので地盤高を引く。京都タワーは構造物の高さなので引かない。"""
    service = make(tmp_path, ns_count=3, ew_count=3, tower=(0, 0))
    tower = service.landmarks[0]
    tower.height = 131
    tower.kind = "point"
    peak = Landmark({"id": "p", "name": "山", "layer": 2, "kind": "peak", "height": 131})

    # 同じ高さ・同じ距離でも、山は地盤高(50m)ぶん低く見える
    assert service.elevation_angle(tower, 1000) > service.elevation_angle(peak, 1000)


def test_range_spans_a_wide_arc_and_a_peak_does_not():
    """東山は連なりなので水平方向に広く占める。単独峰とは扱いが違う。

    洛中の東西の通りはすべて東山に突き当たるので、点では表現できない
    （docs/SPEC.md 2.4）。
    """
    grid = Grid()
    service = LandmarkService(grid)
    ns = [s["name"] for s in grid.ns_streets]
    ew = [s["name"] for s in grid.ew_streets]
    at = (ns.index("千本通"), ew.index("七条通"))

    by_id = {landmark.id: landmark for landmark in service.landmarks}
    higashiyama = service.span(by_id["higashiyama"], *at)
    atago = service.span(by_id["atago"], *at)

    assert higashiyama["width"] > 60          # 連なり
    assert atago["width"] < 30                # 単独峰
    # 東を向いた先が東山の範囲に入っている
    assert (90 - higashiyama["start"]) % 360 <= higashiyama["width"]


def test_the_range_to_the_east_is_the_cue_where_no_peak_is_visible():
    """千本通×七条通 では東山が選ばれる。

    七条通は東へ真っ直ぐ伸びて東山に突き当たる。以前は東山を持っておらず、
    北の山並みを指していた（実際に見えるのは東）。
    """
    grid = Grid()
    service = LandmarkService(grid)
    ns = [s["name"] for s in grid.ns_streets]
    ew = [s["name"] for s in grid.ew_streets]
    cue = service.best(ns.index("千本通"), ew.index("七条通"))

    assert cue["kind"] == "range"
    assert cue["name"] == "東山"
    assert cue["bearing"] == "東"
    assert cue["angular_width"] > 60
