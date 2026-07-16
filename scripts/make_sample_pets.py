from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw


def make_pet(root: Path, pet_id: str, name: str, color: str) -> None:
    folder = root / pet_id
    folder.mkdir(parents=True, exist_ok=True)
    atlas = Image.new("RGBA", (1536, 2288), (0, 0, 0, 0))
    for row, count in enumerate((6, 8, 8, 4, 5, 8, 6, 6, 6, 8, 8)):
        for col in range(count):
            cell = Image.new("RGBA", (192, 208), (0, 0, 0, 0))
            draw = ImageDraw.Draw(cell)
            bob = (col % 3) * 3
            draw.ellipse((53, 42 + bob, 139, 133 + bob), fill=color, outline="#252733", width=5)
            draw.ellipse((69, 73 + bob, 82, 88 + bob), fill="white")
            draw.ellipse((110, 73 + bob, 123, 88 + bob), fill="white")
            draw.arc((75, 82 + bob, 117, 112 + bob), 10, 170, fill="#252733", width=4)
            draw.rounded_rectangle((68, 125 + bob, 124, 185 + bob), 18, fill=color, outline="#252733", width=5)
            atlas.alpha_composite(cell, (col * 192, row * 208))
    atlas.save(folder / "spritesheet.webp", lossless=True)
    manifest = {
        "id": pet_id,
        "displayName": name,
        "description": f"A tiny {name} summoned for Pet Shelf testing.",
        "spriteVersionNumber": 2,
        "spritesheetPath": "spritesheet.webp",
    }
    (folder / "pet.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    output = Path(__file__).resolve().parents[1] / "sample-pets"
    make_pet(output, "aqua-slime", "Aqua Slime", "#53c7ec")
    make_pet(output, "sakura-mochi", "Sakura Mochi", "#f29bb2")
    print(output)
