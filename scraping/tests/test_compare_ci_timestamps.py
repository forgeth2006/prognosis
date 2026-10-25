import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "graph_features"))
from compare_ci_timestamps import hist_change, label_differences, lag_summary


def frame(rows):
    d = pd.DataFrame(rows, columns=["repo", "pr_number", "package_norm", "label", "created_at", "ci_completed_at", "closed_at"])
    for c in ("created_at", "ci_completed_at", "closed_at"):
        d[c] = pd.to_datetime(d[c], utc=True)
    return d


OLD = [("r", 1, "p", 1, "2025-01-01 00:00", "2025-01-01 01:00", "2025-01-01 02:00"),
       ("r", 2, "p", 0, "2025-01-02 00:00", "2026-10-01 00:00", "2025-01-02 02:00"),
       ("r", 3, "p", 0, "2025-01-03 00:00", "2025-01-03 01:00", "2025-01-03 02:00")]


class CompareTests(unittest.TestCase):
    def test_label_differences(self):
        old = frame(OLD)
        new = old.copy()
        self.assertEqual(len(label_differences(old, new)), 0)
        new.loc[0, "label"] = 0
        self.assertEqual(len(label_differences(old, new)), 1)
        self.assertEqual(len(label_differences(old, new.iloc[:2])), 2)   # one differs, one missing

    def test_lag_summary_counts_after_close(self):
        s = lag_summary(frame(OLD))
        self.assertEqual(s["after_close_1h"], 1)
        self.assertEqual(s["missing"], 0)

    def test_hist_change_detects_late_verdict(self):
        old = frame(OLD)
        new = old.copy()
        new.loc[1, "ci_completed_at"] = pd.Timestamp("2025-01-02 01:00", tz="UTC")   # verdict now known early
        changed, _, n = hist_change(old, new)
        self.assertEqual(n, 3)
        self.assertGreaterEqual(changed, 1)                                          # row 3 now sees row 2's verdict

    def test_identical_timestamps_change_nothing(self):
        old = frame(OLD)
        self.assertEqual(hist_change(old, old.copy())[0], 0)


if __name__ == "__main__":
    unittest.main()
