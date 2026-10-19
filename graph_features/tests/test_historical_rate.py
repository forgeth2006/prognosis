import random
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from historical_rate import M, PRIOR_RATE, PRIOR_STRENGTH, add_historical_rate  # noqa: E402


def df(rows):
    return pd.DataFrame(rows, columns=["repo", "package_norm", "created_at", "ci_completed_at", "closed_at", "label"])


class HistRateTests(unittest.TestCase):
    def test_first_row_has_no_evidence_and_gets_prior(self):
        out = add_historical_rate(df([("a", "x", "2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z", None, 1)]))
        self.assertEqual((out.hist_k[0], out.hist_n[0]), (0, 0))
        self.assertAlmostEqual(out.hist_rate[0], PRIOR_RATE)

    def test_only_strictly_earlier_verdicts_count(self):
        rows = [("a", "x", "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", None, 1),
                # created exactly when the first verdict landed: must NOT see it
                ("a", "x", "2026-01-02T00:00:00Z", "2026-01-03T00:00:00Z", None, 0),
                # created after the first verdict but BEFORE the second one finished
                ("a", "x", "2026-01-02T12:00:00Z", "2026-01-05T00:00:00Z", None, 0),
                ("a", "x", "2026-01-06T00:00:00Z", "2026-01-07T00:00:00Z", None, 0)]
        out = add_historical_rate(df(rows))
        self.assertEqual(list(out.hist_n), [0, 0, 1, 3])
        self.assertEqual(list(out.hist_k), [0, 0, 1, 1])

    def test_pooled_across_repos_and_packages(self):
        rows = [("a", "x", "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", None, 1),
                ("b", "x", "2026-01-03T00:00:00Z", "2026-01-04T00:00:00Z", None, 0),
                ("b", "y", "2026-01-05T00:00:00Z", "2026-01-06T00:00:00Z", None, 0)]
        out = add_historical_rate(df(rows))
        self.assertEqual((out.hist_n[1], out.hist_k[1]), (1, 1))   # package x seen in another repo
        self.assertEqual((out.hist_n[2], out.hist_k[2]), (0, 0))   # package y unseen -> global rate
        self.assertAlmostEqual(out.hist_rate[2], out.hist_global_rate[2])

    def test_smoothing_formula(self):
        rows = [("a", "x", "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", None, 1),
                ("a", "x", "2026-02-01T00:00:00Z", "2026-02-02T00:00:00Z", None, 0)]
        out = add_historical_rate(df(rows))
        p0 = (1 + PRIOR_STRENGTH * PRIOR_RATE) / (1 + PRIOR_STRENGTH)
        self.assertAlmostEqual(out.hist_global_rate[1], p0)
        self.assertAlmostEqual(out.hist_rate[1], (1 + M * p0) / (1 + M))

    def test_closed_at_fallback_and_missing_time_never_counted(self):
        rows = [("a", "x", "2026-01-01T00:00:00Z", None, "2026-01-02T00:00:00Z", 1),
                ("a", "x", "2026-01-01T12:00:00Z", None, None, 1),
                ("a", "x", "2026-02-01T00:00:00Z", None, None, 0)]
        out = add_historical_rate(df(rows))
        self.assertEqual(out.hist_n[2], 1)  # only the row with a closed_at

    def test_matches_brute_force_on_random_data(self):
        random.seed(3)
        rows = []
        for i in range(120):
            day = random.randint(1, 120)
            rows.append(("r", random.choice("abcd"), f"2026-01-01T00:00:00Z" if False else
                         (pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(days=day, hours=random.randint(0, 23))).isoformat(),
                         (pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(days=day + random.randint(0, 5), hours=random.randint(0, 23))).isoformat(),
                         None, random.randint(0, 1)))
        d = df(rows)
        out = add_historical_rate(d)
        c = pd.to_datetime(d.created_at, utc=True)
        k = pd.to_datetime(d.ci_completed_at, utc=True)
        for i in range(len(d)):
            prior = k < c[i]
            same = prior & (d.package_norm == d.package_norm[i])
            self.assertEqual((out.hist_n[i], out.hist_k[i]), (int(same.sum()), int(d.label[same].sum())))


if __name__ == "__main__":
    unittest.main()
