import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_feature_table as bft  # noqa: E402


def pr(n, pkg, created, done, label, repo="o/r", old="1.0.0", new="1.1.0", rng=False):
    return {"repo": repo, "pr_number": str(n), "package": pkg, "package_norm": pkg.lower(), "created_at": created,
            "ci_completed_at": done, "closed_at": done, "label": label, "fail_confidence": "single_attempt" if label == 1 else "",
            "eff_old_version": old, "eff_new_version": new, "bump_type": "minor", "major_delta": 0, "minor_delta": 1,
            "patch_delta": 0, "is_prerelease": False, "is_zero_major": False, "is_range_update": rng}


LABELED = pd.DataFrame([
    pr(1, "requests", "2026-03-05T00:00:00Z", "2026-03-05T01:00:00Z", 0),
    pr(2, "requests", "2026-03-20T00:00:00Z", "2026-03-20T01:00:00Z", 1, new="1.2.0"),
    pr(3, "pytest", "2026-04-02T00:00:00Z", "2026-04-02T01:00:00Z", 0),
    pr(4, "towncrier", "2026-04-03T00:00:00Z", "2026-04-03T01:00:00Z", 0),
    {**pr(5, "requests", "2026-04-09T00:00:00Z", "2026-04-09T01:00:00Z", 0, new="1.3.0"), "label": float("nan")},  # excluded
])
SNAPS = pd.DataFrame([
    ("o/r", "2026-03", "s1", "requests", "requests", 2, 2, 0, 3, 0, 0.5),
    ("o/r", "2026-04", "s2", "requests", "requests", 3, 2, 1, 5, 0, 0.5),
    ("o/r", "2026-04", "s2", "pytest", "pytest", 4, 0, 4, 4, None, None)],
    columns=["repo", "snapshot_month", "snapshot_sha", "package", "package_norm", "blast_direct", "blast_direct_src",
             "blast_direct_tests", "blast_transitive", "depth_min", "depth_mean"])
INDEX = pd.DataFrame([("o/r", "2026-03", "s1", True), ("o/r", "2026-04", "s2", True)],
                     columns=["repo", "snapshot_month", "snapshot_sha", "snapshot_exists"])
CHANGELOG = pd.DataFrame([("requests", "1.0.0", "1.1.0", True, 2000.0, 40.0, True)],
                         columns=["package", "old_version", "new_version", "changelog_found", "changelog_chars",
                                  "changelog_lines", "has_breaking_keyword"])


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.ft, self.full = bft.build(LABELED, SNAPS, INDEX, CHANGELOG)

    def test_only_labeled_rows_and_all_kept(self):
        self.assertEqual(len(self.ft), 4)
        self.assertEqual(bft.check_rows(self.ft, LABELED)[0], True)

    def test_graph_join_is_point_in_time(self):
        d = self.ft.set_index("pr_number")
        self.assertEqual(d.loc["1", "blast_direct"], 2)   # March snapshot
        self.assertEqual(d.loc["2", "blast_direct"], 2)
        self.assertEqual(d.loc["3", "blast_direct"], 4)   # April snapshot
        self.assertEqual(d.loc["3", "depth_missing"], 1)
        self.assertEqual((d.loc["4", "not_in_graph"], d.loc["4", "blast_direct"]), (1, 0))
        self.assertEqual(d["snapshot_missing"].sum(), 0)

    def test_changelog_join_flags_unscraped(self):
        d = self.ft.set_index("pr_number")
        self.assertEqual((d.loc["1", "changelog_scraped"], d.loc["1", "changelog_found"]), (1, 1))
        self.assertEqual((d.loc["2", "changelog_scraped"], d.loc["2", "changelog_found"]), (0, 0))
        self.assertTrue(pd.isna(d.loc["2", "changelog_chars"]))

    def test_hist_rate_is_point_in_time(self):
        d = self.ft.set_index("pr_number")
        self.assertEqual((d.loc["1", "hist_n"], d.loc["2", "hist_n"]), (0, 1))
        self.assertEqual((d.loc["3", "hist_n"], d.loc["4", "hist_n"]), (0, 0))

    def test_checks_pass_and_catch_a_tampered_rate(self):
        self.assertTrue(bft.check_nulls(self.ft)[0])
        self.assertTrue(bft.check_hist_leakage(self.full, self.ft)[0])
        bad = self.ft.copy()
        bad.loc[0, "hist_n"] = 5   # pretend future/other data leaked in
        self.assertFalse(bft.check_hist_leakage(self.full, bad)[0])
        self.assertTrue(bft.check_snapshot_time(self.ft)[0])

    def test_unexplained_null_is_flagged(self):
        bad = self.ft.copy()
        bad.loc[0, "blast_direct"] = None
        ok, _, unexplained = bft.check_nulls(bad)
        self.assertFalse(ok)
        self.assertEqual(unexplained, ["blast_direct"])

    def test_missing_snapshot_is_flagged_not_dropped(self):
        idx = INDEX[INDEX.snapshot_month != "2026-03"]
        ft, _ = bft.build(LABELED, SNAPS[SNAPS.snapshot_month != "2026-03"], idx, CHANGELOG)
        self.assertEqual(len(ft), 4)
        self.assertEqual(int(ft.snapshot_missing.sum()), 2)

    def test_balance_warns_below_threshold(self):
        ok, msg, per, warn = bft.check_balance(self.ft)
        self.assertTrue(warn)
        self.assertIn("1 breakages", msg)

    def test_duplicate_snapshot_keys_are_rejected(self):
        with self.assertRaises(AssertionError):
            bft.build(LABELED, pd.concat([SNAPS, SNAPS.iloc[[0]]]), INDEX, CHANGELOG)


if __name__ == "__main__":
    unittest.main()
