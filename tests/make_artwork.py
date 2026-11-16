#!/usr/bin/env python3
"""Generate opaque, native-size test images without touching the device."""
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parent / "artwork"
root.mkdir(exist_ok=True)
palette = [0, 0, 0, 255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 255]
palette += [0] * (768 - len(palette))


def frame(color):
    image = Image.new("P", (240, 135), color)
    image.putpalette(palette)
    return image


def save(name, frames, duration):
    frames[0].save(
        root / name, save_all=True, append_images=frames[1:],
        duration=duration, loop=0, disposal=2, optimize=False,
    )


save("01-red.gif", [frame(1)], 1000)
save("02-blue.gif", [frame(3)], 1000)
save("03-red-blue-1000ms.gif", [frame(1), frame(3)], 1000)
save("04-red-blue-500ms.gif", [frame(1), frame(3)], 500)
marker = frame(0)
draw = ImageDraw.Draw(marker)
draw.rectangle((0, 0, 15, 15), fill=1)
draw.rectangle((224, 0, 239, 15), fill=2)
draw.rectangle((0, 119, 15, 134), fill=3)
draw.rectangle((224, 119, 239, 134), fill=4)
save("05-corners.gif", [marker], 1000)

for path in sorted(root.glob("*.gif")):
    with Image.open(path) as image:
        print(path.name, image.size, image.n_frames, image.info.get("duration"))
