import json
import unittest
from unittest.mock import patch

import numpy as np

from sql.database import read_gallery
from search.service import build_index


class GalleryTests(unittest.TestCase):
    @patch("sql.database.connect")
    def test_missing_invalid_and_valid_rows(self, connect):
        cur = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        color, texture, shape = (json.dumps([0] * n) for n in (640, 26, 12))
        cur.fetchall.return_value = [
            (1, "one.jpg", "one", color, texture, shape),
            (2, "two.jpg", "two", None, None, None),
            (3, "three.jpg", "three", color, texture, "[]"),
            (4, "four.jpg", "four", color, texture, json.dumps([True] + [0] * 11)),
        ]
        records, rejected = read_gallery()
        self.assertEqual(list(records), [1])
        self.assertEqual([r["image_id"] for r in rejected], [2, 3, 4])
        self.assertIn("missing", rejected[0]["reason"])
        self.assertIn("12", rejected[1]["reason"])
        self.assertIn("numbers", rejected[2]["reason"])
        self.assertTrue(cur.execute.call_args.args[0].lstrip().startswith("SELECT "))

    def test_self_excluded_before_fit(self):
        records = {i: (f"{i}.jpg", "bird", np.full(678, value))
                   for i, value in [(1, -1), (2, 2), (3, 99)]}
        index = build_index(records, {3})
        np.testing.assert_array_equal(index.minimum, -1)
        np.testing.assert_array_equal(index.span, 3)
        ids = [r["image_id"] for r in index.rank([records[3][2]] * 2)]
        self.assertEqual(ids, [2, 1])
