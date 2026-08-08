from __future__ import annotations

from backend.app.instruction import build_move_instruction, build_start_hint


def test_move_instruction_leads_with_the_street_and_keeps_the_kyoto_wording():
    assert build_move_instruction("上ル", 4, "三条通") == "三条通まで上ル（およそ4本）"
    assert build_move_instruction("西入ル", 11, "烏丸通") == "烏丸通まで西入ル（およそ11本）"


def test_move_instruction_always_uses_the_kyoto_direction_words():
    """上ル / 下ル / 東入ル / 西入ル は必ず残す（企画の核）。"""
    for direction in ("上ル", "下ル", "東入ル", "西入ル"):
        assert direction in build_move_instruction(direction, 1, "四条通")


def test_start_hint_tells_which_way_is_agaru_from_the_landmark():
    """目印は経路選択ではなく、どちらが上ルかを知るためにある。"""
    assert build_start_hint("京都タワー", "南", 2000, 200) == (
        "京都タワーが南に見えます。京都タワーを正面に見て、真後ろが上ルです。")
    assert build_start_hint("京都タワー", "西", 2000, 200) == (
        "京都タワーが西に見えます。京都タワーを正面に見て、右手が上ルです。")
    assert build_start_hint("大文字", "北東", 3000, 0) == (
        "大文字が北東に見えます。大文字を正面に見て、左前が上ルです。")
    assert build_start_hint("大文字", "北", 3000, 0) == (
        "大文字が北に見えます。大文字の方が上ルです。")


def test_start_hint_refuses_to_use_a_landmark_that_is_too_close():
    """近すぎると見上げる形になり、水平方向が読みにくい。"""
    hint = build_start_hint("京都タワー", "南", 80, 200)
    assert "すぐそこ" in hint and "見上げる" in hint


def test_start_hint_falls_back_to_street_signs_when_nothing_is_visible():
    assert "通り名" in build_start_hint(None, None)
