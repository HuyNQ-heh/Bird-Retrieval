import unittest

import numpy as np

from search.query_image import normalize_crop


class QueryCropTests(unittest.TestCase):
    def test_edge_padding_and_mask_alignment(self):
        # A left-edge object forces a partially out-of-frame square crop.
        mask = np.zeros((60, 100), np.uint8)
        mask[10:40, :10] = 255
        rgb = np.full((60, 100, 3), 25, np.uint8)
        rgb[mask > 0] = (250, 0, 0)
        im, bird = normalize_crop(rgb, mask)
        self.assertEqual(im.shape, (224, 224, 3))
        self.assertEqual(bird.shape, (224, 224))
        np.testing.assert_array_equal(np.unique(bird), [0, 255])
        np.testing.assert_array_equal(im[0, 0], [25, 25, 25])
        y, x = np.where(bird)
        self.assertAlmostEqual(x.mean(), 111.5, delta=3)
        self.assertAlmostEqual(y.mean(), 111.5, delta=3)
        self.assertAlmostEqual(len(np.unique(y)) / 224, 0.75, delta=0.01)
        red = im[..., 0] > 140
        self.assertGreater((red & (bird != 0)).sum() / (red | (bird != 0)).sum(), 0.95)

    def test_empty_mask(self):
        with self.assertRaisesRegex(ValueError, "No foreground"):
            normalize_crop(np.zeros((9, 5, 3), np.uint8), np.zeros((9, 5), np.uint8))
