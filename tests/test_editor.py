from __future__ import annotations

from PIL import Image

from pet_shelf.editor import (
    fit_frame,
    frame_from_image_or_atlas,
    parse_timing,
    replace_atlas_cell,
    update_action_manifest,
)


def test_fit_frame_centers_without_distortion():
    source = Image.new("RGBA", (100, 50), (255, 0, 0, 255))
    result = fit_frame(source)
    assert result.size == (192, 208)
    assert result.getpixel((96, 104))[3] == 255
    assert result.getpixel((0, 0))[3] == 0


def test_replace_cell_does_not_touch_neighbor():
    atlas = Image.new("RGBA", (1536, 1872), (0, 0, 0, 0))
    frame = Image.new("RGBA", (192, 208), (20, 40, 200, 255))
    result = replace_atlas_cell(atlas, 3, 4, frame)
    assert result.getpixel((4 * 192 + 96, 3 * 208 + 104)) == (20, 40, 200, 255)
    assert result.getpixel((3 * 192 + 96, 3 * 208 + 104))[3] == 0


def test_timing_is_extended_to_frame_count():
    assert parse_timing("100, 200", 4) == [100, 200, 200, 200]


def test_action_manifest_and_trigger_are_generated():
    manifest: dict = {}
    update_action_manifest(manifest, "magic-beam", "running", 3, [100, 200, 300], "once", "hover")
    action = manifest["animations"]["magic-beam"]
    assert action["sourceRow"] == "running"
    assert action["durationMs"] == 600
    assert action["loop"] is False
    assert manifest["interactions"]["hover"]["animation"] == "magic-beam"
    assert manifest["actions"]["magic-beam"] == "magic-beam"


def test_reassigning_trigger_removes_old_trigger():
    manifest: dict = {}
    update_action_manifest(manifest, "wave-hi", "waving", 4, [100] * 4, "loop", "hover")
    update_action_manifest(manifest, "wave-hi", "waving", 4, [100] * 4, "loop", "click")
    assert "hover" not in manifest["interactions"]
    assert manifest["interactions"]["click"]["animation"] == "wave-hi"


def test_matching_cell_is_extracted_from_imported_atlas():
    atlas = Image.new("RGBA", (1536, 2288), (0, 0, 0, 0))
    atlas.paste((80, 160, 240, 255), (3 * 192, 4 * 208, 4 * 192, 5 * 208))
    frame = frame_from_image_or_atlas(atlas, 4, 3)
    assert frame.size == (192, 208)
    assert frame.getpixel((96, 104)) == (80, 160, 240, 255)
