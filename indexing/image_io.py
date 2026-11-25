"""Image formats shared by the indexer and search interfaces."""

import numpy as np
from PIL import Image, ImageOps, features


FORMATS = {
    "JPEG": ("jpg", "jpeg", "jfif", "jpe"),
    "PNG": ("png", "apng"),
    "GIF": ("gif",),
    "BMP": ("bmp",),
    "TIFF": ("tif", "tiff"),
}
for codec, name, extensions in (
    ("webp", "WEBP", ("webp",)),
    ("avif", "AVIF", ("avif", "avifs")),
    ("jpg_2000", "JPEG2000", ("jp2", "j2k", "jpx", "jpf")),
):
    if codec in features.get_supported():
        FORMATS[name] = extensions

EXTENSIONS = tuple(ext for extensions in FORMATS.values() for ext in extensions)


def load_rgb(source, *, supported_only=False):
    """Decode the first frame/page as an oriented, opaque RGB image."""
    with Image.open(source, formats=tuple(FORMATS) if supported_only else None) as image:
        frame = ImageOps.exif_transpose(image)
        if frame.mode.startswith("I;16"):
            gray = (np.asarray(frame).astype(np.uint32) // 257).astype(np.uint8)
            return Image.fromarray(gray).convert("RGB")
        if "A" in frame.getbands() or "transparency" in frame.info:
            rgba = frame.convert("RGBA")
            background = Image.new("RGB", frame.size, "white")
            background.paste(rgba, mask=rgba.getchannel("A"))
            return background
        return frame.convert("RGB")
