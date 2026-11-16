"""UI-independent editing and local upload history."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sys
import uuid

from PIL import GifImagePlugin, Image, ImageEnhance, ImageOps, ImageSequence


def external_editor_environment():
    """Do not inject bundled Qt/shared libraries into a system image editor."""
    environment = os.environ.copy()
    if getattr(sys, "frozen", False):
        original = environment.get("LD_LIBRARY_PATH_ORIG")
        if original:
            environment["LD_LIBRARY_PATH"] = original
        else:
            environment.pop("LD_LIBRARY_PATH", None)
        bundle = str(getattr(sys, "_MEIPASS", ""))
        for key in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH"):
            value = environment.get(key, "")
            if bundle and bundle in value:
                environment.pop(key, None)
    return environment


@dataclass(frozen=True)
class Adjustments:
    rotation: int = 0
    flip_horizontal: bool = False
    flip_vertical: bool = False
    brightness: float = 1.0


def load_animation(path):
    frames, durations = [], []
    with Image.open(path) as image:
        count = getattr(image, "n_frames", 1)
        if count > 2:
            raise ValueError(f"This prototype supports at most 2 frames; this file has {count}.")
        if image.width * image.height > 20_000_000:
            raise ValueError("Image is too large (maximum 20 megapixels).")
        for frame in ImageSequence.Iterator(image):
            frames.append(frame.convert("RGBA").copy())
            durations.append(frame.info.get("duration", 1000))
    return frames, durations


def render_frames(frames, adjustments):
    result = []
    for source in frames:
        image = source.convert("RGBA")
        if adjustments.rotation:
            image = image.rotate(-adjustments.rotation, expand=True)
        if adjustments.flip_horizontal:
            image = ImageOps.mirror(image)
        if adjustments.flip_vertical:
            image = ImageOps.flip(image)
        # Composite before brightness adjustment so transparency cannot become white.
        opaque = Image.new("RGBA", image.size, (0, 0, 0, 255))
        opaque.alpha_composite(image)
        image = ImageEnhance.Brightness(opaque.convert("RGB")).enhance(adjustments.brightness)
        image = ImageOps.contain(image, (240, 135), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (240, 135), "black")
        canvas.paste(image, ((240 - image.width) // 2, (135 - image.height) // 2))
        result.append(canvas)
    return result


def save_animation(path, frames, interval):
    if not frames or len(frames) > 2 or not 500 <= interval <= 1000:
        raise ValueError("Expected 1–2 frames and a 500–1000 ms interval.")
    # GIF timing is in centiseconds; do not silently round a user's choice.
    if interval % 10:
        raise ValueError("GIF interval must be a multiple of 10 ms.")
    # Pillow's high-level save merges identical adjacent frames even with
    # optimize=False. Write explicit frame blocks to preserve count and timing.
    indexed = [frame.convert("RGB").quantize(colors=256) for frame in frames]
    header, _ = GifImagePlugin.getheader(indexed[0], info={"loop": 0, "optimize": False})
    with Path(path).open("wb") as stream:
        for block in header:
            stream.write(block)
        for frame in indexed:
            for block in GifImagePlugin.getdata(
                frame, duration=interval, disposal=2, include_color_table=True,
            ):
                stream.write(block)
        stream.write(b";")


class History:
    """Only successfully uploaded, prepared artwork is added by the UI."""
    def __init__(self, root, limit=10):
        self.root = Path(root)
        self.limit = limit
        self.root.mkdir(parents=True, exist_ok=True)

    def items(self):
        try:
            values = json.loads((self.root / "index.json").read_text())
            if not isinstance(values, list):
                return []
            return [item for item in values if isinstance(item, dict)
                    and isinstance(item.get("file"), str)
                    and re.fullmatch(r"[0-9a-f]{32}\.gif", item["file"])
                    and isinstance(item.get("name"), str)
                    and (self.root / item["file"]).is_file()][:self.limit]
        except (OSError, ValueError, TypeError):
            return []

    def record(self, source, name, interval):
        previous = self.items()
        filename = uuid.uuid4().hex + ".gif"
        destination = self.root / filename
        shutil.copyfile(source, destination)
        entry = dict(file=filename, name=name, interval=interval,
                     uploaded=datetime.now(timezone.utc).isoformat())
        entries = [entry] + previous
        temporary = self.root / "index.json.tmp"
        try:
            temporary.write_text(json.dumps(entries[:self.limit], indent=2) + "\n")
            temporary.replace(self.root / "index.json")
        except OSError:
            destination.unlink(missing_ok=True)
            raise
        for old in entries[self.limit:]:
            (self.root / old["file"]).unlink(missing_ok=True)
        return entry
