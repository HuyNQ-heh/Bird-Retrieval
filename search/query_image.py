"""Prepare both query orientations in memory using the Part III extractor."""

import math
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

from indexing.features import extract_features
from indexing.image_io import load_rgb
from indexing.masking import create_bird_mask
from search.retrieval import join_features


@dataclass
class Query:
    original: np.ndarray
    mask: np.ndarray
    normalized: np.ndarray
    normalized_mask: np.ndarray
    vectors: np.ndarray


def normalize_crop(rgb, mask):
    if mask.shape != rgb.shape[:2] or mask.dtype != np.uint8 or not np.all((mask == 0) | (mask == 255)):
        raise ValueError("Invalid binary query mask or mismatched dimensions")
    x, y, width, height = cv2.boundingRect(mask)
    if not width or not height:
        raise ValueError("No foreground in query mask")
    side = math.ceil(max(width / 0.84, height / 0.76))
    left = round(x + width / 2 - side / 2)
    top = round(y + height / 2 - side / 2)
    image = Image.fromarray(rgb)
    # Match Part I: upper median per channel on the outer two rows/columns of a 24px sample.
    sample = np.asarray(image.resize((24, 24), Image.Resampling.BILINEAR))
    border = np.ones((24, 24), dtype=bool)
    border[2:-2, 2:-2] = False
    colors = np.sort(sample[border], axis=0)
    fill = tuple(int(c) for c in colors[len(colors) // 2])
    visible = (max(0, left), max(0, top), min(image.width, left + side), min(image.height, top + side))
    square = Image.new("RGB", (side, side), fill)
    square.paste(image.crop(visible), (visible[0] - left, visible[1] - top))
    # Pillow pads an out-of-bounds grayscale crop with zero.
    square_mask = Image.fromarray(mask).crop((left, top, left + side, top + side))
    normalized = np.asarray(square.resize((224, 224), Image.Resampling.LANCZOS))
    normalized_mask = np.asarray(square_mask.resize((224, 224), Image.Resampling.NEAREST))
    if not normalized_mask.any():
        raise ValueError("Empty query mask after resize")
    return normalized, normalized_mask


def prepare_query(path):
    try:
        rgb = np.asarray(load_rgb(path))
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ValueError(f"Cannot read query image {path}: {exc}") from exc
    mask = create_bird_mask(rgb)
    image, bird = normalize_crop(rgb, mask)
    original = join_features(extract_features(image, bird))
    flipped = join_features(extract_features(np.fliplr(image), np.fliplr(bird)))
    return Query(rgb, mask, image, bird, np.stack([original, flipped]))
