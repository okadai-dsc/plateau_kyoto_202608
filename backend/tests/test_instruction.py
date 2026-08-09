from __future__ import annotations

from backend.app.instruction import build_move_instruction, build_start_hint


def test_move_instruction_leads_with_the_street_and_keeps_the_kyoto_wording():
    assert build_move_instruction("上ル", 4, "三条通") == "三条通まで上ル（およそ4本）"
    assert build_move_instruction("西入ル", 11, "烏丸通") == "烏丸通まで西入ル（およそ11本）"


def test_move_instruction_always_uses_the_kyoto_direction_words():
    """上ル / 下ル / 東入ル / 西入ル は必ず残す（企画の核）。"""
    for direction in ("上ル", "下ル", "東入ル", "西入ル"):
        assert direction in build_move_instruction(direction, 1, "四条通")


def point(bearing, distance=2000):
    return {"kind": "point", "name": "京都タワー", "layer": 1,
            "bearing": bearing, "distance": distance}


def test_point_landmark_tells_which_way_is_agaru():
    """目印は経路選択ではなく、どちらが上ルかを知るためにある。"""
    assert build_start_hint(point("南")) == (
        "京都タワーが南に見えます。京都タワーを正面に見て、真後ろが上ルです。")
    assert build_start_hint(point("西")) == (
        "京都タワーが西に見えます。京都タワーを正面に見て、右手が上ルです。")
    assert build_start_hint(point("北")) == (
        "京都タワーが北に見えます。京都タワーの方が上ルです。")


def test_point_landmark_that_is_too_close_gives_no_bearing():
    """近すぎると見上げる形になり、水平方向が読みにくい。"""
    hint = build_start_hint(point(None, distance=80))
    assert "すぐそこ" in hint and "見上げる" in hint


def test_skyline_says_where_the_mountains_are():
    at_hand = {"kind": "skyline", "name": "山の稜線", "layer": 3,
               "bearing": "東", "walk": 0}
    # 東を向けば北は左手
    assert build_start_hint(at_hand) == "東に山が見えます。山を正面に見て、左手が上ルです。"

    after_walking = {"kind": "skyline", "name": "山の稜線", "layer": 3,
                     "bearing": "北東", "walk": 40}
    hint = build_start_hint(after_walking)
    assert "北東へ40mほど歩くと山が見えます" in hint
    assert "左前が上ル" in hint


def test_major_street_is_the_last_resort_and_gives_a_real_bearing():
    """タワーも山も見えないときは、車がよく通っている方角で上ルを知る。

    「街区の形」と違って **実際の方角が出る** のがこのレイヤの要点。
    そこまで歩かせず、立った場所で気づけることを文にする。
    """
    hint = build_start_hint({"kind": "street", "name": "御池通", "layer": 4,
                             "bearing": "北", "distance": 118})
    assert "北の方を車がよく通っています" in hint
    assert "あちらが御池通です" in hint
    # 北に大通り → その大通りの方が上ル
    assert "御池通の方が上ルです" in hint
    # 歩かせる言い方はしない
    assert "歩く" not in hint and "出ます" not in hint


def test_major_street_to_the_west_puts_north_on_the_right():
    hint = build_start_hint({"kind": "street", "name": "堀川通", "layer": 4,
                             "bearing": "西", "distance": 209})
    assert "堀川通を正面に見て、右手が上ルです" in hint


def test_nothing_at_all_falls_back_to_street_signs():
    assert "通り名" in build_start_hint(None)
    assert "通り名" in build_start_hint({"kind": "none", "layer": 99, "bearing": None})


def test_a_range_is_described_as_a_skyline_not_a_named_peak():
    """連なりは「正面に見て」が成り立たず、個別の山も名指しできない。"""
    hint = build_start_hint({"kind": "range", "name": "東山", "layer": 4,
                             "bearing": "東", "angular_width": 85.9})
    assert "東に東山の山並みが広がっています" in hint
    assert "そちらを向くと、左手が上ルです" in hint
    assert "正面に見て" not in hint


def test_a_range_straight_ahead_needs_no_rotation():
    hint = build_start_hint({"kind": "range", "name": "北山", "layer": 5,
                             "bearing": "北", "angular_width": 40})
    assert "そちらが上ルです" in hint
