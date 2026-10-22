import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eda_graph_layer import cluster_bootstrap, crude_or, mh_odds_ratio, wilson  # noqa: E402


class StatsTests(unittest.TestCase):
    def test_wilson_known_values(self):
        lo, hi = wilson(5, 10)
        self.assertAlmostEqual(lo, 0.237, places=2)
        self.assertAlmostEqual(hi, 0.763, places=2)
        self.assertEqual(wilson(0, 0), (0.0, 0.0))
        lo, hi = wilson(0, 20)
        self.assertEqual(lo, 0.0)
        self.assertGreater(hi, 0.1)  # zero breakages in 20 PRs still allows ~16%

    def test_mh_matches_hand_calculation(self):
        # two strata with a=2,b=8,c=1,d=9 (n=20) and a=3,b=7,c=3,d=7 (n=20)
        rows = []
        for s, (a, b, c, d) in {"x": (2, 8, 1, 9), "y": (3, 7, 3, 7)}.items():
            rows += [(s, 1, 1)] * a + [(s, 1, 0)] * b + [(s, 0, 1)] * c + [(s, 0, 0)] * d
        df = pd.DataFrame(rows, columns=["repo", "e", "label"])
        expected = (2 * 9 / 20 + 3 * 7 / 20) / (8 * 1 / 20 + 7 * 3 / 20)
        self.assertAlmostEqual(mh_odds_ratio(df, "e", "repo"), expected)

    def test_stratification_removes_composition_effect(self):
        # exposure is common in the high-risk repo, rare in the low-risk one, and has NO effect inside either
        rows = ([("hi", 1, 1)] * 30 + [("hi", 1, 0)] * 70 + [("hi", 0, 1)] * 6 + [("hi", 0, 0)] * 14
                + [("lo", 1, 1)] * 1 + [("lo", 1, 0)] * 19 + [("lo", 0, 1)] * 5 + [("lo", 0, 0)] * 95)
        df = pd.DataFrame(rows, columns=["repo", "e", "label"])
        self.assertGreater(crude_or(df, "e"), 1.5)                       # pooled looks harmful
        self.assertAlmostEqual(mh_odds_ratio(df, "e", "repo"), 1.0, delta=0.2)  # within repos it is not

    def test_cluster_bootstrap_is_reproducible_and_brackets_estimate(self):
        rng = np.random.default_rng(0)
        df = pd.DataFrame({"package_norm": rng.choice(list("abcdefghij"), 400), "repo": rng.choice(["r1", "r2"], 400),
                           "e": rng.integers(0, 2, 400), "label": rng.integers(0, 2, 400)})
        f = lambda d: mh_odds_ratio(d, "e", "repo")
        a = cluster_bootstrap(df, f, reps=200)
        self.assertEqual(a, cluster_bootstrap(df, f, reps=200))
        self.assertLess(a[0], f(df))
        self.assertGreater(a[1], f(df))


if __name__ == "__main__":
    unittest.main()
