from pathlib import Path
from PIL import Image, ImageDraw

ATLAS = Path(r"C:\Users\ES-HAOPV15\.codex\pets\charizard-lv3\spritesheet.png")
REF = Path(r"C:\Users\ES-HAOPV15\AppData\Local\Packages\MicrosoftWindows.Client.Core_cw5n1h2txyewy\TempState\ScreenClip\{BB08EBC7-FEE3-4E89-A74E-5EA997695CFA}.png")
OUT = Path(r"C:\Users\ES-HAOPV15\.codex\pets\_runs\charizard-20260714\final\spritesheet-ball-hit-composite.png")
CELL = (192, 208)

def cut(img, box):
    out = img.crop(box).convert("RGBA")
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if r < 18 and g < 18 and b < 18:
                px[x, y] = (0, 0, 0, 0)
    return out

def trim(img):
    a = img.getchannel("A")
    return img.crop(a.getbbox()) if a.getbbox() else img

def fit(img, size):
    img = trim(img)
    img.thumbnail(size, Image.Resampling.NEAREST)
    return img

atlas = Image.open(ATLAS).convert("RGBA")
ref = Image.open(REF).convert("RGBA")

# Existing pixel-art Charizard, row 5 frame 0, is the identity anchor.
base = atlas.crop((0, 5 * CELL[1], CELL[0], 6 * CELL[1]))
base = trim(base)
ball = fit(cut(ref, (105, 32, 170, 105)), (34, 34))
swirl_a = fit(cut(ref, (350, 0, 445, 145)), (150, 150))
swirl_b = fit(cut(ref, (440, 0, 535, 145)), (150, 150))

def cell():
    out = Image.new("RGBA", CELL, (0, 0, 0, 0))
    b = base.copy()
    b.thumbnail((170, 190), Image.Resampling.NEAREST)
    out.alpha_composite(b, ((192 - b.width) // 2, 8))
    return out

frames = [cell() for _ in range(8)]
frames[1].alpha_composite(ball, (18, 75))
frames[2].alpha_composite(ball, (105, 66))
impact = Image.new("RGBA", CELL, (0, 0, 0, 0))
draw = ImageDraw.Draw(impact)
for x, y in [(96, 52), (129, 45), (143, 78), (113, 94)]:
    draw.rectangle((x, y, x + 6, y + 6), fill=(255, 213, 49, 255))
frames[2].alpha_composite(impact)
frames[3].alpha_composite(ball, (105, 66))
frames[4].alpha_composite(swirl_a, (21, 24))
frames[5].alpha_composite(swirl_b, (21, 24))
frames[6].alpha_composite(swirl_a, (21, 24))
frames[7].alpha_composite(ball, (125, 151))

result = atlas.copy()
for i, frame in enumerate(frames):
    result.alpha_composite(frame, (i * CELL[0], 5 * CELL[1]))
OUT.parent.mkdir(parents=True, exist_ok=True)
result.save(OUT)
print(OUT)
