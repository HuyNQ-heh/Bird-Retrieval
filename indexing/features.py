"""Feature order follows section II of the report. All input images are uint8 RGB."""

import cv2
import numpy as np
from skimage.feature import local_binary_pattern
from skimage.measure import perimeter_crofton

from indexing.masking import validate_rgb


def _hist(values, bins):
    counts = np.bincount(values, minlength=bins)
    return counts / max(1, values.size)


def color_features(image, bird):
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV).astype(np.int32)
    h, s, v = hsv.transpose(2, 0, 1)
    bins = ((h * 8 // 180) * 4 + s // 64) * 4 + v // 64
    height, width = bird.shape
    ys = (slice(0, height // 2), slice(height // 2, height))
    xs = (slice(0, width // 2), slice(width // 2, width))
    blocks = [_hist(bins[bird], 128)]
    for y in ys:
        for x in xs:
            blocks.append(_hist(bins[y, x][bird[y, x]], 128))
    return np.concatenate(blocks)


def _glcm(gray, bird, dy, dx):
    h, w = gray.shape
    a = (slice(0, h - dy), slice(max(0, -dx), w - max(0, dx)))
    b = (slice(dy, h), slice(max(0, dx), w - max(0, -dx)))
    keep = bird[a] & bird[b]
    if not keep.any():
        return (0., 0., 0., 0.)
    index = gray[a][keep] * 16 + gray[b][keep]
    counts = np.bincount(index, minlength=256).reshape(16, 16)
    p = (counts + counts.T) / (2. * keep.sum())
    i, j = np.indices(p.shape)
    delta2 = (i - j) ** 2
    mean = (p * i).sum()
    variance = (p * (i - mean) ** 2).sum()
    corr = (p * (i - mean) * (j - mean)).sum() / variance if variance else 1.
    return ((p * delta2).sum(), (p / (1 + delta2)).sum(), np.linalg.norm(p), corr)


def texture_features(image, bird):
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    centers = cv2.erode(bird.astype(np.uint8), np.ones((3, 3), np.uint8),
                        borderType=cv2.BORDER_CONSTANT, borderValue=0).astype(bool)
    codes = local_binary_pattern(gray, 8, 1, method="uniform")
    lbp = _hist(codes[centers].astype(np.intp), 10)
    quantized = gray.astype(np.int32) // 16
    directions = ((0, 1), (1, 0), (1, 1), (1, -1))
    glcm = [_glcm(quantized, bird, dy, dx) for dy, dx in directions]
    return np.concatenate([lbp, np.ravel(glcm)])


def shape_features(bird):
    binary = bird.astype(np.uint8)
    h, w = binary.shape
    area = int(binary.sum())
    hull = cv2.convexHull(cv2.findNonZero(binary))
    hull_pixels = cv2.fillConvexPoly(np.zeros_like(binary), hull, 1)
    moments = cv2.moments(binary, binaryImage=True)
    covariance = np.array([[moments["mu20"], moments["mu11"]],
                           [moments["mu11"], moments["mu02"]]]) / area
    minor, major = np.linalg.eigvalsh(covariance)
    eccentricity = np.sqrt(np.clip(1 - minor / major, 0, 1)) if major > 0 else 0.
    perimeter = perimeter_crofton(binary, directions=4)
    geometry = [w / h, area / (w * h), area / hull_pixels.sum(), eccentricity,
                4 * np.pi * area / perimeter**2 if perimeter else 0.]
    hu = cv2.HuMoments(moments).ravel()
    nonzero = hu != 0
    hu[nonzero] = -np.sign(hu[nonzero]) * np.log10(np.abs(hu[nonzero]))
    return np.concatenate([geometry, hu])


def extract_features(image, mask):
    """Return (color, texture, shape) float64 arrays of size 640, 26 and 12."""
    validate_rgb(image)
    if not isinstance(mask, np.ndarray) or mask.shape != image.shape[:2]:
        raise ValueError("Image and mask dimensions do not match")
    if mask.dtype != bool and (mask.dtype != np.uint8 or not np.all((mask == 0) | (mask == 255))):
        raise ValueError("Mask must be bool or uint8 with values 0 and 255")
    x, y, w, h = cv2.boundingRect(mask.astype(np.uint8))
    if not w or not h:
        raise ValueError("Empty bird mask")
    bird = mask[y:y+h, x:x+w].astype(bool)
    rgb = image[y:y+h, x:x+w]
    vectors = color_features(rgb, bird), texture_features(rgb, bird), shape_features(bird)
    for vector, size in zip(vectors, (640, 26, 12)):
        if vector.shape != (size,) or not np.isfinite(vector).all():
            raise ValueError(f"Invalid feature vector, expected {size} finite values")
    return vectors
