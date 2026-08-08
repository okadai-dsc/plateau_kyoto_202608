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


def test_block_shape_is_the_last_resort_and_works_anywhere():
    """何も見えなくても、街区の形なら南北か東西かは分かる。

    京都の街区は東西に長いので、次の交差点までの距離が倍ちがう。
    """
    hint = build_start_hint({"kind": "block", "name": "街区の形", "layer": 4,
                             "bearing": None, "ns_spacing": 72, "ew_spacing": 136})
    assert "72m" in hint and "東西" in hint
    assert "136m" in hint and "南北" in hint


def test_nothing_at_all_falls_back_to_street_signs():
    assert "通り名" in build_start_hint(None)
