import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_ci_lag import known_capped, purge_sizes


class CapTests(unittest.TestCase):
    def test_cap_never_later_than_close(self):
        ci = pd.Series(pd.to_datetime(["2026-10-10", "2025-09-01"], utc=True))
        closed = pd.Series(pd.to_datetime(["2025-09-05", "2025-09-02"], utc=True))
        out = known_capped(ci, closed)
        self.assertEqual(out[0], closed[0])
        self.assertEqual(out[1], ci[1])

    def test_missing_ci_falls_back_to_close(self):
        ci = pd.Series(pd.to_datetime([None], utc=True))
        closed = pd.Series(pd.to_datetime(["2025-09-05"], utc=True))
        self.assertEqual(known_capped(ci, closed)[0], closed[0])

    def test_purge_drops_rows_known_after_test_start(self):
        created = pd.Series(pd.to_datetime([f"2025-01-{d:02d}" for d in range(1, 11)], utc=True))
        known = created + pd.Timedelta(hours=1)
        known[0] = pd.Timestamp("2026-01-01", tz="UTC")       # first row's verdict arrives very late
        sizes = purge_sizes(created, known, chunks=5)
        self.assertEqual(sizes[0], (2, 1))                     # 2 train rows, 1 kept


if __name__ == "__main__":
    unittest.main()
