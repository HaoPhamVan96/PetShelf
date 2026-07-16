from __future__ import annotations

import json

import pytest
from PIL import Image

from pet_shelf.models import PetLoadError, add_silhouette_outline, load_pet, scan_pet_root


def make_pet(tmp_path, folder_name="pet-one", *, version=2, size=None, pet_id="pet-one", extra=None):
    folder = tmp_path / folder_name
    folder.mkdir()
    height = 2288 if version == 2 else 1872
    Image.new("RGBA", size or (1536, height), (0, 0, 0, 0)).save(folder / "spritesheet.webp")
    manifest = {
        "id": pet_id,
        "displayName": "Pet One",
        "description": "Test pet",
        "spriteVersionNumber": version,
        "spritesheetPath": "spritesheet.webp",
    }
    manifest.update(extra or {})
    (folder / "pet.json").write_text(json.dumps(manifest), encoding="utf-8")
    return folder


def test_load_v2_pet(tmp_path):
    pet = load_pet(make_pet(tmp_path))
    assert pet.pet_id == "pet-one"
    assert pet.sprite_version == 2
    assert pet.thumbnail.size == (192, 208)


def test_load_pet_auto_detects_larger_cell_size(tmp_path):
    folder = make_pet(tmp_path, version=2, size=(2048, 2816))
    atlas = Image.open(folder / "spritesheet.webp").convert("RGBA")
    for y in range(9 * 256, 10 * 256):
        for x in range(4 * 256, 5 * 256):
            atlas.putpixel((x, y), (20, 120, 240, 255))
    atlas.save(folder / "spritesheet.webp", lossless=True)

    pet = load_pet(folder)

    assert pet.cell_width == 256
    assert pet.cell_height == 256
    assert pet.thumbnail.size == (256, 256)
    assert pet.look_frame(4).getpixel((128, 128)) == (20, 120, 240, 255)


def test_scan_immediate_pet_subfolders(tmp_path):
    make_pet(tmp_path, "pet-a", pet_id="a")
    make_pet(tmp_path, "pet-b", pet_id="b")
    (tmp_path / "notes").mkdir()
    pets, issues = scan_pet_root(tmp_path)
    assert [pet.pet_id for pet in pets] == ["a", "b"]
    assert issues == []


def test_invalid_atlas_is_reported(tmp_path):
    folder = make_pet(tmp_path, size=(100, 100))
    with pytest.raises(PetLoadError, match="invalid atlas size"):
        load_pet(folder)


def test_path_escape_is_rejected(tmp_path):
    folder = make_pet(tmp_path)
    data = json.loads((folder / "pet.json").read_text())
    data["spritesheetPath"] = "../spritesheet.webp"
    (folder / "pet.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PetLoadError, match="outside"):
        load_pet(folder)


def test_duplicate_ids_become_issue(tmp_path):
    make_pet(tmp_path, "pet-a", pet_id="same")
    make_pet(tmp_path, "pet-b", pet_id="same")
    pets, issues = scan_pet_root(tmp_path)
    assert len(pets) == 1
    assert len(issues) == 1
    assert "duplicate" in issues[0].message


def test_custom_interactions_are_parsed(tmp_path):
    folder = make_pet(
        tmp_path,
        extra={
            "animations": {
                "special": {
                    "sourceRow": "jumping",
                    "frameCount": 3,
                    "timingMs": [100, 200, 300],
                    "playback": "once",
                }
            },
            "interactions": {
                "hover": {"animation": "special"},
                "click": {"animations": ["special", "waving"], "mode": "cycle"},
            },
        },
    )
    pet = load_pet(folder)
    assert pet.animation_spec("special").row == 4
    assert pet.animation_spec("special").durations_ms == (100, 200, 300)
    assert pet.animation_spec("special").loop is False
    assert pet.interactions["hover"].animations == ("special",)
    assert pet.interactions["click"].animations == ("special", "waving")


def test_custom_animation_can_use_extra_row_index(tmp_path):
    folder = make_pet(tmp_path, version=1, size=(1536, 13 * 192))
    atlas = Image.open(folder / "spritesheet.webp").convert("RGBA")
    for y in range(10 * 192, 11 * 192):
        for x in range(2 * 192, 3 * 192):
            atlas.putpixel((x, y), (20, 120, 240, 255))
    atlas.save(folder / "spritesheet.webp", lossless=True)
    data = json.loads((folder / "pet.json").read_text())
    data["animations"] = {
        "extra-form": {
            "sourceRowIndex": 10,
            "frameCount": 4,
            "timingMs": [100, 100, 100, 100],
            "playback": "once",
        }
    }
    data["interactions"] = {"click": {"animations": ["extra-form"], "mode": "cycle"}}
    (folder / "pet.json").write_text(json.dumps(data), encoding="utf-8")

    pet = load_pet(folder)

    assert pet.atlas_rows == 13
    assert pet.animation_spec("extra-form").row == 10
    assert pet.frame("extra-form", 2).getpixel((96, 96)) == (20, 120, 240, 255)
    assert pet.interactions["click"].animations == ("extra-form",)


def test_hover_and_drag_behavior_can_be_disabled(tmp_path):
    folder = make_pet(
        tmp_path,
        extra={
            "hoverBehavior": {"mode": "disabled"},
            "dragBehavior": {"mode": "disabled"},
        },
    )

    pet = load_pet(folder)

    assert pet.hover_interaction_enabled is False
    assert pet.drag_animation_enabled is False


def test_white_cell_background_becomes_transparent(tmp_path):
    folder = make_pet(tmp_path)
    atlas = Image.open(folder / "spritesheet.webp").convert("RGBA")
    for y in range(208):
        for x in range(192):
            atlas.putpixel((x, y), (255, 255, 255, 255))
    for y in range(70, 140):
        for x in range(70, 120):
            atlas.putpixel((x, y), (230, 40, 80, 255))
    atlas.save(folder / "spritesheet.webp", lossless=True)
    frame = load_pet(folder).thumbnail
    assert frame.getpixel((0, 0))[3] == 0
    assert frame.getpixel((90, 100))[3] == 255


def test_v2_look_direction_uses_clockwise_rows(tmp_path):
    folder = make_pet(tmp_path)
    atlas = Image.open(folder / "spritesheet.webp").convert("RGBA")
    # 090° (screen-right) is direction index 4: row 9, column 4.
    for y in range(9 * 208, 10 * 208):
        for x in range(4 * 192, 5 * 192):
            atlas.putpixel((x, y), (20, 120, 240, 255))
    atlas.save(folder / "spritesheet.webp", lossless=True)
    pet = load_pet(folder)
    assert pet.look_frame(4).getpixel((96, 104)) == (20, 120, 240, 255)


def test_v1_pet_rejects_look_directions(tmp_path):
    pet = load_pet(make_pet(tmp_path, version=1))
    with pytest.raises(PetLoadError, match="require"):
        pet.look_frame(0)


def test_outline_follows_alpha_silhouette():
    image = Image.new("RGBA", (15, 15), (0, 0, 0, 0))
    image.putpixel((7, 7), (255, 255, 255, 255))
    outlined = add_silhouette_outline(image, "#ff0000", width=1)
    assert outlined.getpixel((7, 7)) == (255, 255, 255, 255)
    assert outlined.getpixel((6, 7)) == (255, 0, 0, 255)
    assert outlined.getpixel((5, 7))[3] == 0
    assert outlined.getpixel((0, 0))[3] == 0
