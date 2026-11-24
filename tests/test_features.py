import unittest

import numpy as np

from features import extract_features


class FeatureContract(unittest.TestCase):
    def test_color_order_and_empty_quadrant(self):
        # Foreground bbox starts at (2, 1) and is 3 x 3. Its lower right is empty.
        rgb = np.full((6, 8, 3), 90, dtype=np.uint8)
        mask = np.zeros(rgb.shape[:2], np.uint8)
        for y, x, color in [(1, 2, (255, 0, 0)), (1, 4, (0, 255, 0)), (3, 2, (0, 0, 255))]:
            rgb[y, x] = color
            mask[y, x] = 255
        hsv, texture, shape = extract_features(rgb, mask)
        hist = hsv.reshape(5, 128)
        red, green, blue = 15, 47, 95
        np.testing.assert_allclose(hist[0, [red, green, blue]], 1 / 3)
        np.testing.assert_array_equal(hist.sum(axis=1), [1, 1, 1, 1, 0])
        self.assertEqual((hist[1, red], hist[2, green], hist[3, blue]), (1, 1, 1))
        np.testing.assert_array_equal(texture, np.zeros(26))
        self.assertEqual(shape.shape, (12,))
        self.assertTrue(np.isfinite(shape).all())

    def test_counts_only_adjacent_bird_pixels(self):
        # Quantized bird levels at three corners: top left 0, top right 1, bottom left 3.
        gray = np.array([[0, 16], [48, 255]], dtype=np.uint8)
        rgb = np.repeat(gray[..., None], 3, axis=2)
        mask = np.array([[255, 255], [255, 0]], dtype=np.uint8)
        _, texture, _ = extract_features(rgb, mask)
        np.testing.assert_array_equal(texture[:10], 0)
        expected = [[1, 1/2, 1/np.sqrt(2), -1], [9, 1/10, 1/np.sqrt(2), -1],
                    [0, 0, 0, 0], [4, 1/5, 1/np.sqrt(2), -1]]
        np.testing.assert_allclose(texture[10:].reshape(4, 4), expected)

    def test_lbp_centers_and_constant_glcm(self):
        rgb = np.zeros((5, 5, 3), np.uint8)
        mask = np.zeros((5, 5), np.uint8)
        mask[1:4, 1:4] = 255
        before = extract_features(rgb, mask)
        rgb[mask == 0] = (255, 35, 170)
        for a, b in zip(before, extract_features(rgb, mask)):
            np.testing.assert_array_equal(a, b)
        expected = np.zeros(10)
        expected[8] = 1
        np.testing.assert_array_equal(before[1][:10], expected)
        np.testing.assert_array_equal(before[1][10:], np.tile([0, 1, 1, 1], 4))
        mask[1, 1] = 0  # The only possible center now touches background at its diagonal.
        np.testing.assert_array_equal(extract_features(rgb, mask)[1][:10], 0)

    def test_single_pixel_and_invalid_masks(self):
        image = np.zeros((1, 1, 3), np.uint8)
        shape = extract_features(image, np.ones((1, 1), bool))[2]
        np.testing.assert_array_equal(shape[:4], [1, 1, 1, 0])
        np.testing.assert_array_equal(shape[5:], 0)
        for mask in (np.zeros((1, 1), bool), np.ones((1, 1), np.uint8), np.ones((2, 2), bool)):
            with self.assertRaises(ValueError):
                extract_features(image, mask)
