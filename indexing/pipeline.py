"""Batch indexing, dataset inspection and verification of stored features."""

from collections import Counter
from contextlib import nullcontext
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
from tempfile import NamedTemporaryFile
from uuid import uuid4

import cv2
import numpy as np
from PIL import Image

from sql.database import ROOT, SELECT_FEATURES, connect, publish, register
from indexing.features import extract_features
from indexing.image_io import EXTENSIONS, load_rgb
from indexing.masking import create_bird_mask


IMAGES = ROOT / "data/images"


def species_of(path):
    match = re.fullmatch(r"(.+)_[0-9]{4}_[0-9]+", path.stem)
    if not match:
        raise ValueError("Expected species_####_numeric-id followed by an image extension")
    return match[1].replace("_", " ")


def dataset():
    files = sorted(p for p in IMAGES.rglob("*") if p.is_file() and p.suffix[1:].lower() in EXTENSIONS)
    if not files:
        raise ValueError("No supported image files under data/images")
    return files


def read_rgb(path):
    return np.asarray(load_rgb(path, supported_only=True))


def read_mask(path):
    with Image.open(path) as im:
        if im.format != "PNG" or im.mode != "L":
            raise ValueError("Expected single-channel 8-bit PNG mask")
        return np.asarray(im)


def save_mask(source, mask):
    buffer = io.BytesIO()
    Image.fromarray(mask).save(buffer, format="PNG")
    data = buffer.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    folder = ROOT / "data/masks" / source.relative_to(IMAGES).parent
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{source.stem}.{digest}.png"
    if path.exists() and path.read_bytes() == data:
        return path.relative_to(ROOT).as_posix()
    with NamedTemporaryFile(dir=folder, delete=False) as tmp:
        temp_path = Path(tmp.name)
        try:
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        except BaseException:
            tmp.close()
            temp_path.unlink(missing_ok=True)
            raise
    try:
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
    return path.relative_to(ROOT).as_posix()


def preview(rgb, mask, path):
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    overlay = rgb.copy()
    cv2.drawContours(overlay, contours, -1, (255, 32, 110), 1, cv2.LINE_AA)
    panels = np.concatenate([rgb, cv2.cvtColor(mask, cv2.COLOR_GRAY2RGB), overlay], axis=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(panels).save(path)


def check_histograms(mask, vectors):
    x, y, w, h = cv2.boundingRect(mask)
    bird = mask[y:y+h, x:x+w]
    occupied = [1, *(int(p.any()) for row in (bird[:h//2], bird[h//2:])
                     for p in (row[:, :w//2], row[:, w//2:]))]
    color_sums = vectors[0].reshape(5, 128).sum(axis=1)
    centers = cv2.erode(mask, np.ones((3, 3), np.uint8),
                        borderType=cv2.BORDER_CONSTANT, borderValue=0)
    lbp_sum = vectors[1][:10].sum()
    np.testing.assert_allclose(color_sums, occupied, atol=1e-12, rtol=0)
    np.testing.assert_allclose(lbp_sum, int(centers.any()), atol=1e-12, rtol=0)
    return [*color_sums.tolist(), float(lbp_sum)]


def run(args):
    files = [p.resolve() for p in args.image] if args.image else dataset()
    if args.limit is not None:
        files = files[:args.limit]
    if args.mask and len(files) != 1:
        raise ValueError("--mask requires exactly one input image")
    folder = ROOT / "runs" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:6])
    folder.mkdir(parents=True)
    counts = dict(selected=len(files), masks=0, extracted=0, mysql_verified=0, errors=0)
    print("Run:", folder, flush=True)
    with (nullcontext(None) if args.offline else connect()) as conn, (folder / "results.jsonl").open(
            "w", encoding="utf-8") as log:
        for i, source in enumerate(files, 1):
            row = {"image": str(source)}
            stage = "register"
            try:
                relative = source.relative_to(IMAGES)
                row["image"] = source.relative_to(ROOT).as_posix()
                species = species_of(source)
                if conn:
                    row["image_id"] = register(conn, row["image"], species)
                stage = "read_image"
                rgb = read_rgb(source)
                stage = "mask"
                mask = read_mask(args.mask) if args.mask else create_bird_mask(rgb)
                stage = "features"
                vectors = extract_features(rgb, mask)
                row["hist_sums"] = check_histograms(mask, vectors)
                counts["extracted"] += 1
                if args.check_background:
                    changed = rgb.copy()
                    changed[mask == 0] = 255 - changed[mask == 0]
                    after = extract_features(changed, mask)
                    diffs = [float(np.abs(a - b).max()) for a, b in zip(after, vectors)]
                    row["background_max_abs"] = diffs
                    if max(diffs) > 1e-12:
                        raise ValueError(f"Background changed features: {diffs}")
                stage = "save_mask"
                row["mask"] = save_mask(source, mask)
                counts["masks"] += 1
                if args.preview:
                    stage = "preview"
                    # Preserve historical JPEG preview paths and distinguish other source formats.
                    name = relative.with_suffix(".png") if relative.suffix.lower() == ".jpg" else relative.with_name(relative.name + ".png")
                    preview(rgb, mask, folder / "previews" / name)
                if conn:
                    stage = "mysql"
                    publish(conn, row["image_id"], row["mask"], vectors)
                    counts["mysql_verified"] += 1
                else:
                    row["vectors"] = [v.tolist() for v in vectors]
            except Exception as exc:
                row.update(stage=stage, error=f"{type(exc).__name__}: {exc}")
                counts["errors"] += 1
                print(f"{source.name} [{stage}] {exc}", file=sys.stderr, flush=True)
            log.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            log.flush()
            if i % 100 == 0:
                print(i, "/", len(files), flush=True)
    (folder / "summary.json").write_text(json.dumps(counts, indent=2), encoding="utf-8")
    print(json.dumps(counts))
    return int(counts["errors"] > 0)


def verify():
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM images")
        total = cur.fetchone()[0]
        cur.execute(SELECT_FEATURES + " ORDER BY i.image_id")
        rows = cur.fetchall()
    errors = 0
    for image_id, source, path, *stored in rows:
        try:
            mask = read_mask(ROOT / path)
            vectors = extract_features(read_rgb(ROOT / source), mask)
            check_histograms(mask, vectors)
            for actual, value in zip(vectors, stored):
                np.testing.assert_allclose(actual, json.loads(value), atol=1e-12, rtol=1e-12)
        except Exception as exc:
            print(f"{image_id} {source} [verify] {exc}", file=sys.stderr)
            errors += 1
    print(json.dumps(dict(registered=total, complete=len(rows), missing=total-len(rows),
                          verified=len(rows)-errors, mismatches=errors)))
    return int(errors > 0)


def inspect_dataset():
    specs, species = Counter(), Counter()
    for path in dataset():
        with Image.open(path) as im:
            im.load()
            specs[(im.format, im.mode, im.size)] += 1
        species[species_of(path)] += 1
    print(f"{sum(species.values())} images / {len(species)} species")
    print(dict(specs))
    print(json.dumps(dict(species), ensure_ascii=False))
