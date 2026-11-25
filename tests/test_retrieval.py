import unittest

import numpy as np

from search.retrieval import DIMENSIONS, GalleryIndex, join_features


def vector(color, texture, shape):
    data = np.zeros(DIMENSIONS)
    data[[0, 640, 666]] = color, texture, shape
    return data


class RetrievalTests(unittest.TestCase):
    def test_identical_and_hand_distance(self):
        rows = [vector(0, 2, 3), vector(10, 4, 8)]
        index = GalleryIndex.fit([11, 12], rows)
        exact = index.rank([rows[0], rows[0]])
        self.assertEqual((exact[0]["image_id"], exact[0]["distance"]), (11, 0))
        query = vector(30, 10, 3)  # Scales to (3, 4, 0); no clipping.
        hit = next(r for r in index.rank([query, query]) if r["image_id"] == 11)
        self.assertEqual([hit[k] for k in ("S_mau", "S_ket_cau", "S_hinh_dang", "distance")],
                         [9, 16, 0, 5])

    def test_constant_dimensions_and_repeated_queries(self):
        rows = [vector(5, 0, 1), vector(5, 2, 1)]
        index = GalleryIndex.fit([1, 2], rows)
        minimum, span = index.minimum.copy(), index.span.copy()
        first = index.rank(rows)
        other = vector(-100, 300, 1000)
        changed = index.rank([other, other])
        self.assertEqual(index.group_counts(), [0, 1, 0])
        self.assertEqual(changed[0]["S_mau"] + changed[0]["S_hinh_dang"], 0)
        np.testing.assert_array_equal(index.minimum, minimum)
        np.testing.assert_array_equal(index.span, span)
        self.assertEqual(first, index.rank(rows))

    def test_orientation_contributions_stable_top_five(self):
        rows = [vector(0, 0, 0), vector(0, 0, 0), vector(2, 4, 8),
                vector(1, 2, 4), vector(1, 3, 4), vector(1, 2, 5)]
        index = GalleryIndex.fit([8, 2, 7, 4, 9, 6], rows)
        query = [vector(0, 0, 0), vector(2, 3, 6)]
        hits = index.rank(query)
        self.assertEqual([r["image_id"] for r in hits[:2]], [2, 8])
        self.assertEqual(len({r["image_id"] for r in hits}), 5)
        distances = [r["distance"] for r in hits]
        self.assertEqual(distances, sorted(distances))
        for r in hits:
            self.assertAlmostEqual(sum(r[k] for k in ("S_mau", "S_ket_cau", "S_hinh_dang")),
                                   r["distance"]**2)
        hit = next(r for r in hits if r["image_id"] == 7)
        self.assertEqual(hit["orientation"], "flipped")
        self.assertEqual((hit["S_mau"], hit["S_ket_cau"], hit["S_hinh_dang"]), (0, 1/16, 1/16))

    def test_small_empty_and_all_constant_gallery(self):
        a = vector(0, 0, 0)
        self.assertEqual(GalleryIndex.fit([], []).rank([a, a]), [])
        one = GalleryIndex.fit([4], [a]).rank([a+1, a+2])
        self.assertEqual([(r["image_id"], r["distance"]) for r in one], [(4, 0)])
        with self.assertRaises(ValueError):
            GalleryIndex.fit([4, 4], [a, a])

    def test_rejects_invalid_groups(self):
        groups = [np.zeros(640), np.zeros(26), np.zeros(12)]
        for bad in (np.zeros(11), np.full(12, np.nan), np.full(12, "0")):
            with self.assertRaises(ValueError):
                join_features([*groups[:2], bad])
        self.assertEqual(join_features(groups).shape, (678,))
