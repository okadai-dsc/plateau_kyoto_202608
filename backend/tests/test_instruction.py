from __future__ import annotations

from backend.app.instruction import build_instruction, build_start_hint


def test_instruction_includes_street_name_with_visible_tower_clue():
    assert (
        build_instruction("上ル", 4, "8通", True, "南")
        == "京都タワーを背にして、4本上ル（8通まで）"
    )
    assert (
        build_instruction("東入ル", 3, "C通", True, "南")
        == "京都タワーを右手に見て、3本東入ル（C通まで）"
    )


def test_instruction_omits_tower_phrase_when_not_visible():
    assert build_instruction("東入ル", 3, "C通", False, "南西") == "3本東入ル（C通まで）"


def test_start_hint_is_backend_generated():
    assert build_start_hint(True, "南") == "京都タワーが南に見えます。"
    assert "京都タワーは見えません" in build_start_hint(False, "北")
