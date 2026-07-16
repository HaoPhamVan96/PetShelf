from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFilter


CELL_WIDTH = 192
CELL_HEIGHT = 208
ATLAS_COLUMNS = 8
STANDARD_ROWS = 9
EXTENDED_ROWS = 11


class PetLoadError(ValueError):
    """A pet folder does not satisfy the supported atlas contract."""


def add_silhouette_outline(image: Image.Image, color: str, width: int = 1) -> Image.Image:
    """Draw a colored outline around the non-transparent sprite silhouette."""
    rgba = image.convert("RGBA")
    if width <= 0:
        return rgba
    try:
        red, green, blue = ImageColor.getrgb(color)
    except ValueError:
        red, green, blue = ImageColor.getrgb("#202124")
    alpha = rgba.getchannel("A")
    dilated = alpha.filter(ImageFilter.MaxFilter(width * 2 + 1))
    outline_alpha = ImageChops.subtract(dilated, alpha)
    outlined = Image.new("RGBA", rgba.size, (red, green, blue, 0))
    outlined.putalpha(outline_alpha)
    outlined.alpha_composite(rgba)
    return outlined


@dataclass(frozen=True, slots=True)
class AnimationSpec:
    row: int
    durations_ms: tuple[int, ...]
    loop: bool = True
    display_name: str = ""


@dataclass(frozen=True, slots=True)
class InteractionSpec:
    animations: tuple[str, ...]
    mode: str = "single"


ANIMATIONS: dict[str, AnimationSpec] = {
    "idle": AnimationSpec(0, (280, 110, 110, 140, 140, 320)),
    "running-right": AnimationSpec(1, (120, 120, 120, 120, 120, 120, 120, 220)),
    "running-left": AnimationSpec(2, (120, 120, 120, 120, 120, 120, 120, 220)),
    "waving": AnimationSpec(3, (140, 140, 140, 280)),
    "jumping": AnimationSpec(4, (140, 140, 140, 140, 280)),
    "failed": AnimationSpec(5, (140, 140, 140, 140, 140, 140, 140, 240)),
    "waiting": AnimationSpec(6, (150, 150, 150, 150, 150, 260)),
    "running": AnimationSpec(7, (120, 120, 120, 120, 120, 220)),
    "review": AnimationSpec(8, (150, 150, 150, 150, 150, 280)),
}


@dataclass(slots=True)
class Pet:
    folder: Path
    pet_id: str
    display_name: str
    description: str
    sprite_version: int
    spritesheet_path: Path
    atlas: Image.Image
    cell_width: int = CELL_WIDTH
    cell_height: int = CELL_HEIGHT
    atlas_rows: int = STANDARD_ROWS
    display_width: int = CELL_WIDTH
    display_height: int = CELL_HEIGHT
    custom_animations: dict[str, AnimationSpec] = field(default_factory=dict)
    interactions: dict[str, InteractionSpec] = field(default_factory=dict)
    drag_animation_enabled: bool = True
    hover_interaction_enabled: bool = True
    _frame_cache: dict[tuple[str, int], Image.Image] = field(default_factory=dict, repr=False)

    def animation_spec(self, name: str) -> AnimationSpec | None:
        return self.custom_animations.get(name) or ANIMATIONS.get(name)

    def frame(self, state: str, index: int) -> Image.Image:
        spec = self.animation_spec(state)
        if spec is None:
            raise PetLoadError(f"Unknown animation '{state}'")
        if spec.row >= self.atlas_rows:
            raise PetLoadError(f"Animation '{state}' is outside this spritesheet")
        index %= len(spec.durations_ms)
        cache_key = (state, index)
        if cache_key in self._frame_cache:
            return self._frame_cache[cache_key]
        left = index * self.cell_width
        top = spec.row * self.cell_height
        frame = self.atlas.crop((left, top, left + self.cell_width, top + self.cell_height))
        frame = _remove_connected_white_background(frame)
        self._frame_cache[cache_key] = frame
        return frame

    def look_frame(self, direction_index: int) -> Image.Image:
        """Return one of the 16 clockwise v2 look-direction cells."""
        if self.sprite_version != 2:
            raise PetLoadError("look directions require spriteVersionNumber 2")
        direction_index %= 16
        cache_key = ("__look__", direction_index)
        if cache_key in self._frame_cache:
            return self._frame_cache[cache_key]
        row = 9 + direction_index // ATLAS_COLUMNS
        column = direction_index % ATLAS_COLUMNS
        left = column * self.cell_width
        top = row * self.cell_height
        frame = self.atlas.crop((left, top, left + self.cell_width, top + self.cell_height))
        frame = _remove_connected_white_background(frame)
        self._frame_cache[cache_key] = frame
        return frame

    @property
    def thumbnail(self) -> Image.Image:
        return self.frame("idle", 0)

    def animation_display_name(self, name: str) -> str:
        spec = self.animation_spec(name)
        if spec and spec.display_name:
            return spec.display_name
        return name.replace("-", " ").title()


def _required_text(data: dict, key: str, manifest: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PetLoadError(f"{manifest.name}: '{key}' must be a non-empty string")
    return value.strip()


def _remove_connected_white_background(image: Image.Image) -> Image.Image:
    """Remove only near-white pixels connected to a cell edge.

    This preserves enclosed white clothes/eyes and is a safe fallback for legacy
    sprites. Properly transparent Codex atlases take the fast path unchanged.
    """
    rgba = image.convert("RGBA")
    edge_points = (
        [(x, 0) for x in range(rgba.width)]
        + [(x, rgba.height - 1) for x in range(rgba.width)]
        + [(0, y) for y in range(rgba.height)]
        + [(rgba.width - 1, y) for y in range(rgba.height)]
    )
    edge_pixels = [rgba.getpixel(point) for point in edge_points]
    opaque_white_edges = sum(
        alpha > 245 and min(red, green, blue) > 235 and max(red, green, blue) - min(red, green, blue) < 20
        for red, green, blue, alpha in edge_pixels
    )
    if opaque_white_edges < len(edge_pixels) * 0.55:
        return rgba

    pixels = rgba.load()
    candidate = Image.new("L", (rgba.width + 2, rgba.height + 2), 0)
    mask_pixels = candidate.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            red, green, blue, alpha = pixels[x, y]
            near_white = (
                alpha > 0
                and min(red, green, blue) >= 205
                and max(red, green, blue) - min(red, green, blue) <= 24
            )
            mask_pixels[x + 1, y + 1] = 0 if near_white else 255
    ImageDraw.floodfill(candidate, (0, 0), 128)
    for y in range(rgba.height):
        for x in range(rgba.width):
            if mask_pixels[x + 1, y + 1] == 128:
                red, green, blue, _ = pixels[x, y]
                pixels[x, y] = (red, green, blue, 0)
    return rgba


def _parse_custom_animations(data: dict, atlas_rows: int | None = None) -> dict[str, AnimationSpec]:
    parsed: dict[str, AnimationSpec] = {}
    raw_animations = data.get("animations", {})
    if not isinstance(raw_animations, dict):
        return parsed
    for name, raw in raw_animations.items():
        if not isinstance(name, str) or not isinstance(raw, dict):
            continue
        source_row = raw.get("sourceRow")
        base = ANIMATIONS.get(source_row) if isinstance(source_row, str) else None
        row_index = raw.get("sourceRowIndex")
        if base is None and isinstance(source_row, int):
            row_index = source_row
        if base is None and isinstance(row_index, int) and row_index >= 0:
            if atlas_rows is None or row_index < atlas_rows:
                base = AnimationSpec(row_index, ANIMATIONS["idle"].durations_ms)
        if base is None:
            continue
        frame_count = raw.get("frameCount", len(base.durations_ms))
        if not isinstance(frame_count, int) or not 1 <= frame_count <= ATLAS_COLUMNS:
            continue
        timing = raw.get("timingMs")
        if not isinstance(timing, list):
            nested = raw.get("spriteSheetPlayback", {})
            if isinstance(nested, dict):
                timing_data = nested.get("timing", {})
                if isinstance(timing_data, dict):
                    timing = timing_data.get("frameDurationsMs")
        valid_timing = isinstance(timing, list) and all(
            isinstance(value, (int, float)) and 16 <= value <= 60_000 for value in timing
        )
        if valid_timing and timing:
            durations = [int(value) for value in timing[:frame_count]]
            durations.extend([durations[-1]] * (frame_count - len(durations)))
        else:
            durations = list(base.durations_ms[:frame_count])
            durations.extend([durations[-1]] * (frame_count - len(durations)))
        playback = raw.get("playback", "loop" if raw.get("loop") else "once")
        loop = bool(raw.get("loop", playback == "loop"))
        display_name = raw.get("displayName", "")
        parsed[name] = AnimationSpec(base.row, tuple(durations), loop, display_name if isinstance(display_name, str) else "")
    return parsed


def _parse_interactions(data: dict, available: set[str]) -> dict[str, InteractionSpec]:
    parsed: dict[str, InteractionSpec] = {}
    raw_interactions = data.get("interactions", {})
    if not isinstance(raw_interactions, dict):
        return parsed
    for event_name in ("hover", "click"):
        raw = raw_interactions.get(event_name)
        if not isinstance(raw, dict):
            continue
        names = raw.get("animations")
        if not isinstance(names, list):
            names = [raw.get("animation")]
        clean_names = tuple(name for name in names if isinstance(name, str) and name in available)
        if clean_names:
            mode = raw.get("mode", "cycle" if len(clean_names) > 1 else "single")
            parsed[event_name] = InteractionSpec(clean_names, str(mode))
    return parsed


def load_pet(folder: Path) -> Pet:
    folder = folder.resolve()
    manifest = folder / "pet.json"
    if not manifest.is_file():
        raise PetLoadError("missing pet.json")

    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PetLoadError(f"cannot read pet.json: {exc}") from exc
    if not isinstance(data, dict):
        raise PetLoadError("pet.json must contain a JSON object")

    pet_id = _required_text(data, "id", manifest)
    display_name = _required_text(data, "displayName", manifest)
    description = data.get("description", "")
    if not isinstance(description, str):
        raise PetLoadError("pet.json: 'description' must be a string")

    version = data.get("spriteVersionNumber", 1)
    if version not in (1, 2):
        raise PetLoadError("spriteVersionNumber must be 1 or 2")
    relative_sprite = data.get("spritesheetPath", "spritesheet.webp")
    if not isinstance(relative_sprite, str) or not relative_sprite.strip():
        raise PetLoadError("spritesheetPath must be a non-empty string")

    sprite_path = (folder / relative_sprite).resolve()
    try:
        sprite_path.relative_to(folder)
    except ValueError as exc:
        raise PetLoadError("spritesheetPath cannot point outside the pet folder") from exc
    if not sprite_path.is_file():
        raise PetLoadError(f"missing {relative_sprite}")

    try:
        with Image.open(sprite_path) as source:
            source.load()
            atlas = source.convert("RGBA")
    except (OSError, ValueError) as exc:
        raise PetLoadError(f"cannot decode spritesheet: {exc}") from exc

    expected_rows = EXTENDED_ROWS if version == 2 else STANDARD_ROWS
    if atlas.width % ATLAS_COLUMNS != 0:
        raise PetLoadError(
            f"invalid atlas size {atlas.width}x{atlas.height}; "
            f"version {version} requires {ATLAS_COLUMNS} columns and {expected_rows} rows"
        )
    cell_width = atlas.width // ATLAS_COLUMNS
    atlas_rows = expected_rows
    if atlas.height % expected_rows == 0:
        cell_height = atlas.height // expected_rows
    elif atlas.height % cell_width == 0 and atlas.height // cell_width >= expected_rows:
        cell_height = cell_width
        atlas_rows = atlas.height // cell_height
    else:
        raise PetLoadError(
            f"invalid atlas size {atlas.width}x{atlas.height}; "
            f"version {version} requires {ATLAS_COLUMNS} columns and at least {expected_rows} rows"
        )
    if cell_width <= 0 or cell_height <= 0:
        raise PetLoadError("spritesheet cell size must be positive")
    display_width = data.get("displayWidth", cell_width)
    display_height = data.get("displayHeight", cell_height)
    if not isinstance(display_width, int) or display_width <= 0:
        display_width = cell_width
    if not isinstance(display_height, int) or display_height <= 0:
        display_height = cell_height

    custom_animations = _parse_custom_animations(data, atlas_rows)
    available = set(ANIMATIONS) | set(custom_animations)
    interactions = _parse_interactions(data, available)
    raw_drag_behavior = data.get("dragBehavior")
    drag_animation_enabled = True
    if isinstance(raw_drag_behavior, dict):
        mode = str(raw_drag_behavior.get("mode", "")).strip().lower()
        if mode in {"none", "disabled", "off", "idle"}:
            drag_animation_enabled = False
    elif raw_drag_behavior is False:
        drag_animation_enabled = False
    raw_hover_behavior = data.get("hoverBehavior")
    hover_interaction_enabled = True
    if isinstance(raw_hover_behavior, dict):
        mode = str(raw_hover_behavior.get("mode", "")).strip().lower()
        if mode in {"none", "disabled", "off", "idle"}:
            hover_interaction_enabled = False
    elif raw_hover_behavior is False:
        hover_interaction_enabled = False
    return Pet(
        folder,
        pet_id,
        display_name,
        description.strip(),
        version,
        sprite_path,
        atlas,
        cell_width,
        cell_height,
        atlas_rows,
        display_width,
        display_height,
        custom_animations,
        interactions,
        drag_animation_enabled,
        hover_interaction_enabled,
    )


@dataclass(frozen=True, slots=True)
class ScanIssue:
    folder_name: str
    message: str


def scan_pet_root(root: Path) -> tuple[list[Pet], list[ScanIssue]]:
    root = root.resolve()
    if not root.is_dir():
        raise PetLoadError("selected pet folder does not exist")

    pets: list[Pet] = []
    issues: list[ScanIssue] = []
    seen_ids: set[str] = set()
    for child in sorted((item for item in root.iterdir() if item.is_dir()), key=lambda p: p.name.lower()):
        if not (child / "pet.json").is_file():
            continue
        try:
            pet = load_pet(child)
            if pet.pet_id in seen_ids:
                raise PetLoadError(f"duplicate pet id '{pet.pet_id}'")
            seen_ids.add(pet.pet_id)
            pets.append(pet)
        except PetLoadError as exc:
            issues.append(ScanIssue(child.name, str(exc)))
    return pets, issues
