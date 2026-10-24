"""Guards the numbers quoted in the report against the frozen dataset.

If the data is ever changed (it should not be after the freeze), these fail and the report text must be revisited.
"""
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TABLE = ROOT / "data" / "feature_table_v2.csv"


@unittest.skipUnless(TABLE.exists(), "frozen table not present")
class ReportNumbers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = pd.read_csv(TABLE)

    def test_headline_counts(self):
        self.assertEqual(len(self.f), 1314)
        self.assertEqual(int(self.f["label"].sum()), 129)
        self.assertEqual(self.f["repo"].nunique(), 13)

    def test_blast_direct_bins_in_graph_section(self):
        for lo, want_wide, want_narrow in ((2, (23, 335), (106, 979)), (3, (13, 238), (116, 1076))):
            wide = self.f["blast_direct"] >= lo
            self.assertEqual((int(self.f[wide]["label"].sum()), int(wide.sum())), want_wide)
            self.assertEqual((int(self.f[~wide]["label"].sum()), int((~wide).sum())), want_narrow)

    def test_not_imported_rows(self):
        self.assertEqual(int((self.f["not_in_graph"] == 1).sum()), 824)

    def test_per_repo_rate_range(self):
        r = self.f.groupby("repo")["label"].mean()
        self.assertEqual(round(r.min(), 3), 0.0)
        self.assertEqual(round(r.max(), 3), 0.328)

    def test_report_sections_quote_these_numbers(self):
        txt = (ROOT / "report" / "graph_layer_section.md").read_text()
        for needle in ("23/335", "106/979", "13/238", "0% to 33%", "17.5% to 5.7%"):
            self.assertIn(needle, txt)


if __name__ == "__main__":
    unittest.main()
