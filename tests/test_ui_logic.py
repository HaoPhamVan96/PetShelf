from pet_shelf.models import AnimationSpec
from pet_shelf.ui import animation_cycle_should_end, drag_animation_for_delta


def test_drag_left_selects_running_left():
    assert drag_animation_for_delta(-1) == "running-left"


def test_drag_right_selects_running_right():
    assert drag_animation_for_delta(1) == "running-right"


def test_drag_without_horizontal_motion_keeps_current_animation():
    assert drag_animation_for_delta(0) is None


def test_click_interaction_finishes_looping_animation_after_one_cycle():
    spec = AnimationSpec(3, (100, 100, 100), loop=True)

    assert animation_cycle_should_end(spec, "click") is True


def test_non_interaction_looping_animation_keeps_looping():
    spec = AnimationSpec(3, (100, 100, 100), loop=True)

    assert animation_cycle_should_end(spec, None) is False
