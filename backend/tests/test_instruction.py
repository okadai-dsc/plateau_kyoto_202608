from __future__ import annotations

from backend.app.instruction import build_move_instruction, build_start_hint


def test_move_instruction_leads_with_the_street_and_keeps_the_kyoto_wording():
    assert build_move_instruction("上ル", 4, "三条通") == "三条通まで上ル（およそ4本）"
    assert build_move_instruction("西入ル", 11, "烏丸通") == "烏丸通まで西入ル（およそ11本）"


def test_move_instruction_always_uses_the_kyoto_direction_words():
    """上ル / 下ル / 東入ル / 西入ル は必ず残す（企画の核）。"""
    for direction in ("上ル", "下ル", "東入ル", "西入ル"):
        assert direction in build_move_instruction(direction, 1, "四条通")


def test_start_hint_tells_which_way_is_agaru_from_the_tower():
    """タワーは経路選択ではなく、どちらが上ルかを知るためにある。"""
    assert build_start_hint(True, "南") == "京都タワーが南に見えます。タワーを正面に見て、真後ろが上ルです。"
    assert build_start_hint(True, "西") == "京都タワーが西に見えます。タワーを正面に見て、右手が上ルです。"
    assert build_start_hint(True, "南西") == "京都タワーが南西に見えます。タワーを正面に見て、右後ろが上ルです。"
    assert build_start_hint(True, "北") == "京都タワーが北に見えます。タワーの方が上ルです。"


def test_start_hint_falls_back_to_street_signs_when_the_tower_is_hidden():
    assert "通り名" in build_start_hint(False, "北")
