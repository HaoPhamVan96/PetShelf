from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance
import math

RUN = Path(r"C:\Users\ES-HAOPV15\.codex\pets\_runs\charizard-reference-20260714")
CELL_W, CELL_H, COLS, ROWS = 192, 208, 8, 11

base = Image.open(RUN / "decoded" / "base.png").convert("RGBA")
box = base.getbbox()
base = base.crop(box)

def fitted(scale=1.0, flip=False, angle=0):
    im = base.transpose(Image.Transpose.FLIP_LEFT_RIGHT) if flip else base.copy()
    target_h = int(194 * scale)
    target_w = max(1, int(im.width * target_h / im.height))
    im = im.resize((target_w, target_h), Image.Resampling.LANCZOS)
    if angle:
        im = im.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    return im

def frame(scale=1.0, dx=0, dy=0, flip=False, angle=0, fire=False, dim=1.0):
    out = Image.new("RGBA", (CELL_W, CELL_H), (0, 0, 0, 0))
    im = fitted(scale, flip, angle)
    x = (CELL_W - im.width) // 2 + dx
    y = CELL_H - im.height - 4 + dy
    out.alpha_composite(im, (x, y))
    if fire:
        # Deliberately basic fallback effect: attached to the right-facing mouth area.
        d = ImageDraw.Draw(out)
        if flip:
            pts = [(48, 69), (18, 63), (42, 78)]
        else:
            pts = [(144, 69), (174, 63), (150, 78)]
        d.polygon(pts, fill=(255, 112, 12, 255))
        d.polygon([(pts[0][0], pts[0][1]), ((pts[0][0]+pts[1][0])//2, pts[1][1]+2), (pts[2][0], pts[2][1])], fill=(255, 229, 68, 255))
    if dim != 1.0:
        rgb = ImageEnhance.Brightness(out.convert("RGB")).enhance(dim)
        out = Image.merge("RGBA", (*rgb.split(), out.getchannel("A")))
    return out

atlas = Image.new("RGBA", (CELL_W * COLS, CELL_H * ROWS), (0, 0, 0, 0))

def put(row, col, **kw):
    atlas.alpha_composite(frame(**kw), (col * CELL_W, row * CELL_H))

# Basic fallback state rows. Directional rows are hover-flight, never walking.
for c in range(7): put(0, c, dy=[0,-1,-2,-1,0,0,-1][c], scale=[1,1.005,1.01,1.005,1,1,1.005][c], fire=c in (2,3))
for c in range(8): put(1, c, dx=[-3,-2,-1,0,1,2,3,2][c], dy=[0,-3,-5,-3,0,-3,-5,-3][c], angle=[-2,-1,0,1,2,1,0,-1][c])
for c in range(8): put(2, c, dx=[3,2,1,0,-1,-2,-3,-2][c], dy=[0,-3,-5,-3,0,-3,-5,-3][c], flip=True, angle=[2,1,0,-1,-2,-1,0,1][c])
for c in range(4): put(3, c, angle=[-2,2,-2,2][c], dy=[0,-1,0,-1][c])
for c in range(5): put(4, c, dy=[0,-7,-16,-7,0][c], scale=[1,.99,.97,.99,1][c])
for c in range(8): put(5, c, dy=[3,4,5,4,3,4,5,4][c], angle=[4,3,2,3,4,3,2,3][c], dim=.74)
for c in range(6): put(6, c, dy=[0,-1,-2,-1,0,0][c], angle=[0,-1,-2,-1,0,1][c])
for c in range(6): put(7, c, dy=[0,-1,-2,-1,0,-1][c], angle=[-1,1,-1,1,-1,1][c], fire=c in (1,4))
for c in range(6): put(8, c, angle=[0,-2,-3,-2,0,1][c], dy=[0,0,-1,0,0,0][c])

# Basic look loop: small facing/attention shifts, with a stable footprint.
for c in range(8):
    put(9, c, flip=False, angle=[0,-2,-4,-6,-8,-5,-3,-1][c], dx=[0,1,2,3,4,3,2,1][c], dy=[-2,-2,-1,0,0,1,2,2][c])
for c in range(8):
    put(10, c, flip=True, angle=[0,1,3,5,8,6,4,2][c], dx=[0,-1,-2,-3,-4,-3,-2,-1][c], dy=[2,2,1,0,0,-1,-2,-2][c])

out = RUN / "final" / "spritesheet-basic.png"
out.parent.mkdir(exist_ok=True)
# Validation requires fully transparent pixels to have zero RGB values.
rgba = atlas.load()
for y in range(atlas.height):
    for x in range(atlas.width):
        r, g, b, a = rgba[x, y]
        if a == 0:
            rgba[x, y] = (0, 0, 0, 0)
atlas.save(out)
atlas.save(RUN / "final" / "spritesheet-basic.webp", lossless=True, quality=95)
print(out)
