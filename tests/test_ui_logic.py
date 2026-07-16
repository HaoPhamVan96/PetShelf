from pet_shelf.ui import drag_animation_for_delta


def test_drag_left_selects_running_left():
    assert drag_animation_for_delta(-1) == "running-left"


def test_drag_right_selects_running_right():
    assert drag_animation_for_delta(1) == "running-right"


def test_drag_without_horizontal_motion_keeps_current_animation():
    assert drag_animation_for_delta(0) is None
