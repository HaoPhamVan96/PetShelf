from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)


def draw_icon(size: int) -> Image.Image:
    scale = size / 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    s = lambda value: round(value * scale)

    draw.rounded_rectangle((s(8), s(8), s(248), s(248)), radius=s(56), fill="#172554")
    draw.rounded_rectangle((s(28), s(38), s(228), s(218)), radius=s(28), fill="#2563eb")

    # Shelf boards.
    for y in (92, 166):
        draw.rounded_rectangle((s(48), s(y), s(208), s(y + 12)), radius=s(6), fill="#bfdbfe")
    draw.rounded_rectangle((s(48), s(202), s(208), s(216)), radius=s(7), fill="#dbeafe")

    # Friendly pet head peeking over the top shelf.
    draw.polygon([(s(78), s(82)), (s(84), s(48)), (s(110), s(68)), (s(146), s(68)), (s(172), s(48)), (s(178), s(82))], fill="#fbbf24")
    draw.ellipse((s(78), s(58), s(178), s(142)), fill="#f59e0b")
    draw.ellipse((s(101), s(88), s(115), s(105)), fill="#172554")
    draw.ellipse((s(141), s(88), s(155), s(105)), fill="#172554")
    draw.ellipse((s(124), s(104), s(132), s(112)), fill="#172554")
    draw.arc((s(113), s(105), s(143), s(130)), 10, 170, fill="#172554", width=s(4))
    return image


icon = draw_icon(256)
icon.save(ASSETS / "petshelf.png")
icon.save(ASSETS / "petshelf.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
