"""Localize a VOC bird and segment its silhouette on an in-memory RGB image."""

from functools import lru_cache
import hashlib
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from urllib.request import urlopen
import shutil

import cv2
import numpy as np
import onnxruntime as ort


MODEL_DIR = Path(__file__).resolve().parent / "models"
_SSD_URL = "https://raw.githubusercontent.com/chuanqi305/MobileNet-SSD/master/"
_FILES = {
    "deploy.prototxt": (_SSD_URL + "deploy.prototxt",
                        "2d180f723b3109e21f8287f6b3c691390d07b60eed998327cd3259ffa0e50608"),
    "mobilenet_iter_73000.caffemodel": (_SSD_URL + "mobilenet_iter_73000.caffemodel",
                                        "52eed8be80522c152a17fb56740de705b79881bde1a167e0e747310523685fc7"),
    "silueta.onnx": ("https://github.com/danielgatis/rembg/releases/download/v0.0.0/silueta.onnx",
                     "75da6c8d2f8096ec743d071951be73b4a8bc7b3e51d9a6625d63644f90ffeedb"),
}
_detector_lock = Lock()


def setup_models():
    MODEL_DIR.mkdir(exist_ok=True)
    for name, (url, digest) in _FILES.items():
        path = MODEL_DIR / name
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
            print(f"OK {name}")
            continue
        with NamedTemporaryFile(dir=MODEL_DIR, delete=False) as tmp:
            temp_path = Path(tmp.name)
        try:
            with urlopen(url, timeout=90) as response, temp_path.open("wb") as output:
                shutil.copyfileobj(response, output)
            if hashlib.sha256(temp_path.read_bytes()).hexdigest() != digest:
                raise ValueError(f"Unexpected SHA-256 for {name}")
            temp_path.replace(path)
            print(f"OK {name}")
        finally:
            temp_path.unlink(missing_ok=True)


def validate_rgb(image):
    if (not isinstance(image, np.ndarray) or image.dtype != np.uint8
            or image.ndim != 3 or image.shape[2] != 3 or not image.size):
        raise ValueError("Expected a non-empty H x W x 3 uint8 RGB image")


@lru_cache(maxsize=1)
def _models():
    if any(not (MODEL_DIR / name).is_file() for name in _FILES):
        raise FileNotFoundError("Missing model files. Run: python cli.py setup-models")
    cv2.setNumThreads(2)
    net = cv2.dnn.readNetFromCaffe(str(MODEL_DIR / "deploy.prototxt"),
                                  str(MODEL_DIR / "mobilenet_iter_73000.caffemodel"))
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 3
    opts.inter_op_num_threads = 1
    session = ort.InferenceSession(str(MODEL_DIR / "silueta.onnx"), opts,
                                   providers=["CPUExecutionProvider"])
    return net, session


def _detect(detector, image):
    blob = cv2.dnn.blobFromImage(image, 1 / 127.5, (300, 300),
                                 (127.5, 127.5, 127.5), swapRB=True)
    with _detector_lock:
        detector.setInput(blob)
        detections = detector.forward().reshape(-1, 7)
    birds = detections[(detections[:, 1] == 3) & (detections[:, 2] >= 0.35)]
    if len(birds):
        return birds[np.argmax(birds[:, 2]), 3:].copy()
    return None


def _segment(image, segmenter, coords, padding):
    h, w = image.shape[:2]
    x0, y0, x1, y1 = coords
    dx, dy = (x1 - x0) * padding, (y1 - y0) * padding
    left, top = max(0, int(np.floor(x0 - dx))), max(0, int(np.floor(y0 - dy)))
    right, bottom = min(w, int(np.ceil(x1 + dx))), min(h, int(np.ceil(y1 + dy)))
    if right <= left or bottom <= top:
        raise ValueError("Bird detection has no visible area")
    crop = image[top:bottom, left:right]
    rgb = cv2.resize(crop, (320, 320), interpolation=cv2.INTER_LINEAR).astype(np.float32)
    rgb /= max(1., float(rgb.max()))
    rgb -= np.array([0.485, 0.456, 0.406], np.float32)
    rgb /= np.array([0.229, 0.224, 0.225], np.float32)
    tensor = np.ascontiguousarray(rgb.transpose(2, 0, 1)[None])
    output = segmenter.run([segmenter.get_outputs()[0].name],
                           {segmenter.get_inputs()[0].name: tensor})[0][0, 0]
    if not np.isfinite(output).all():
        raise ValueError("Non-finite segmentation output")
    soft = cv2.resize(output, (right - left, bottom - top))
    binary = np.uint8(soft >= 0.5)
    if not binary.any() or binary.all():
        return None
    # Select the connected component with most pixels inside the predicted box.
    count, labels = cv2.connectedComponents(binary, connectivity=8)
    bx0, by0 = max(0, int(x0) - left), max(0, int(y0) - top)
    bx1, by1 = min(right, int(np.ceil(x1))) - left, min(bottom, int(np.ceil(y1))) - top
    overlap = np.bincount(labels[by0:by1, bx0:bx1].ravel(), minlength=count)[1:]
    if not overlap.any():
        return None
    selected = 1 + overlap.argmax()
    foreground = labels == selected
    inside = int(overlap[selected - 1])
    box_area = (bx1 - bx0) * (by1 - by0)
    if not 0.03 <= inside / box_area <= 0.96 or inside < 0.5 * foreground.sum():
        return None
    mask = np.zeros((h, w), np.uint8)
    mask[top:bottom, left:right] = foreground.astype(np.uint8) * 255
    return mask


def create_bird_mask(image):
    """Return uint8 0/255 at original resolution. Raise ValueError on a miss."""
    validate_rgb(image)
    detector, segmenter = _models()
    box = _detect(detector, image)
    if box is None:
        box = _detect(detector, cv2.flip(image, 1))
        if box is None:
            raise ValueError("No VOC bird at confidence >= 0.35 in either orientation")
        box[[0, 2]] = 1 - box[[2, 0]]
    h, w = image.shape[:2]
    coords = box * [w, h, w, h]
    for padding in (0.15, 0.25):
        mask = _segment(image, segmenter, coords, padding)
        if mask is not None:
            return mask
    raise ValueError("No usable bird silhouette at either crop size")
