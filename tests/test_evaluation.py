import random
import unittest

from search.search_cli import _select_queries


class EvaluationSplitTests(unittest.TestCase):
    def test_balanced_holdout_preserves_baseline_and_gallery_examples(self):
        groups = {"a": [2, 4, 6, 8, 10], "b": [1, 3, 5], "c": [7]}
        records = {i: ("", species, None) for species, ids in groups.items() for i in ids}
        rng = random.Random(42)
        baseline = [rng.choice(groups[s]) for s in ("a", "b")]
        held = _select_queries(records, 3, 42)
        self.assertEqual(held[:2], baseline)
        self.assertEqual(len(set(held)), len(held))
        self.assertEqual([len(set(held).intersection(ids)) for ids in groups.values()], [3, 2, 0])
        self.assertEqual(held, _select_queries(dict(reversed(records.items())), 3, 42))
