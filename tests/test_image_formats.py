from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, UnidentifiedImageError

from indexing import pipeline
from indexing.image_io import FORMATS, load_rgb


class ImageFormatTests(unittest.TestCase):
    def test_upload_and_gallery_paths_decode_each_advertised_format(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for fmt, extensions in FORMATS.items():
                with self.subTest(fmt=fmt):
                    path = folder / ("Bird_0001_123." + extensions[0].upper())
                    Image.new("RGB", (20, 12), "red").save(path, format=fmt)
                    with BytesIO(path.read_bytes()) as upload:
                        expected = np.asarray(load_rgb(upload, supported_only=True))
                    self.assertEqual(expected.shape, (12, 20, 3))
                    np.testing.assert_array_equal(pipeline.read_rgb(path), expected)
            (folder / "notes.txt").touch()
            with patch.object(pipeline, "IMAGES", folder):
                self.assertEqual(set(pipeline.dataset()), set(folder.iterdir()) - {folder / "notes.txt"})

    def test_animated_and_multipage_images_use_first_frame(self):
        for fmt in ("GIF", "TIFF"):
            with self.subTest(fmt=fmt), BytesIO() as buf:
                a = Image.new("RGB", (8, 6), "red")
                a.save(buf, format=fmt, save_all=True, append_images=[Image.new("RGB", a.size, "blue")])
                self.assertEqual(load_rgb(buf).getpixel((0, 0)), (255, 0, 0))

    def test_transparency_orientation_and_high_bit_depth(self):
        with BytesIO() as buf:
            Image.new("RGBA", (8, 6), (0, 0, 255, 0)).save(buf, format="PNG")
            self.assertEqual(load_rgb(buf).getpixel((0, 0)), (255, 255, 255))
        with BytesIO() as buf:
            exif = Image.Exif()
            exif[274] = 6
            Image.new("RGB", (8, 6)).save(buf, format="JPEG", exif=exif)
            self.assertEqual(load_rgb(buf).size, (6, 8))
        with BytesIO() as buf:
            Image.fromarray(np.array([[0, 32768, 65535]], dtype=np.uint16)).save(buf, format="TIFF")
            self.assertEqual(np.asarray(load_rgb(buf))[0, :, 0].tolist(), [0, 127, 255])

    def test_invalid_content(self):
        with self.assertRaises(UnidentifiedImageError):
            load_rgb(BytesIO(b"broken image"), supported_only=True)
