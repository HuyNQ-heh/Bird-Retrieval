"""Gallery-only Min–Max scaling and unweighted Euclidean ranking (NumPy only)."""

from dataclasses import dataclass

import numpy as np


GROUPS = (("S_mau", 640), ("S_ket_cau", 26), ("S_hinh_dang", 12))
DIMENSIONS = sum(size for _, size in GROUPS)


def join_features(parts):
    if len(parts) != len(GROUPS):
        raise ValueError("Expected three feature groups")
    vectors = []
    for values, (name, size) in zip(parts, GROUPS):
        a = np.asarray(values)
        if a.shape != (size,) or a.dtype.kind not in "iuf" or not np.isfinite(a).all():
            raise ValueError(f"{name}: expected {size} finite numbers")
        vectors.append(a.astype(np.float64))
    return np.concatenate(vectors)


@dataclass
class GalleryIndex:
    ids: np.ndarray
    minimum: np.ndarray
    span: np.ndarray
    active: np.ndarray
    matrix: np.ndarray

    @classmethod
    def fit(cls, ids, vectors):
        ids = np.asarray(ids)
        if not ids.size:
            if len(vectors):
                raise ValueError("Feature rows supplied without gallery IDs")
            return cls(np.empty(0, dtype=int), np.zeros(DIMENSIONS), np.zeros(DIMENSIONS),
                       np.zeros(DIMENSIONS, dtype=bool), np.empty((0, 0)))
        if ids.ndim != 1 or ids.dtype.kind not in "iu" or len(np.unique(ids)) != len(ids):
            raise ValueError("Gallery image_ids must be unique integers")
        raw = np.asarray(vectors, dtype=np.float64)
        if raw.shape != (len(ids), DIMENSIONS) or not np.isfinite(raw).all():
            raise ValueError("Invalid gallery feature matrix")
        minimum = raw.min(axis=0)
        span = raw.max(axis=0) - minimum
        active = span > 0
        scaled = (raw[:, active] - minimum[active]) / span[active]
        return cls(ids, minimum, span, active, scaled)

    def group_counts(self):
        counts = []
        start = 0
        for _, size in GROUPS:
            counts.append(int(self.active[start:start + size].sum()))
            start += size
        return counts

    def rank(self, queries):
        q = np.asarray(queries, dtype=np.float64)
        if q.shape != (2, DIMENSIONS) or not np.isfinite(q).all():
            raise ValueError("Expected two finite 678-dimensional query vectors")
        scaled = (q[:, self.active] - self.minimum[self.active]) / self.span[self.active]
        counts = self.group_counts()
        scores = np.empty((2, len(self.ids), 3))
        for orientation, vector in enumerate(scaled):
            squared = np.square(self.matrix - vector)
            start = 0
            for group, count in enumerate(counts):
                scores[orientation, :, group] = squared[:, start:start + count].sum(axis=1)
                start += count
        distance = np.sqrt(scores.sum(axis=2))
        orientation = distance.argmin(axis=0)
        best = distance[orientation, np.arange(len(self.ids))]
        order = np.lexsort((self.ids, best))[:5]
        results = []
        for rank, i in enumerate(order, start=1):
            side = orientation[i]
            row = dict(rank=rank, image_id=int(self.ids[i]), orientation=("original", "flipped")[side],
                       distance=float(best[i]))
            for (name, _), score in zip(GROUPS, scores[side, i]):
                row[name] = float(score)
            results.append(row)
        return results
