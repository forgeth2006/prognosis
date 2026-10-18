import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clean_dataset import clean  # noqa: E402


def row(n, repo="o/r", pkg="requests", old="1.0", new="1.1", label=0.0, created="2026-01-01T00:00:00Z", **kw):
    r = {"repo": repo, "pr_number": str(n), "package": pkg, "package_norm": pkg.lower(), "old_version": old,
         "new_version": new, "resolved_old_version": "", "resolved_new_version": "", "is_range_update": False,
         "label": label, "exclusion_reason": "", "created_at": created}
    r.update(kw)
    return r


class CleanTests(unittest.TestCase):
    def test_exact_duplicates_removed(self):
        df, st = clean(pd.DataFrame([row(1), row(1)]), min_labeled=0)
        self.assertEqual(len(df), 1)
        self.assertEqual(st["exact_duplicates_removed"], 1)

    def test_duplicate_bump_keeps_earliest(self):
        df, st = clean(pd.DataFrame([row(1, created="2026-01-01T00:00:00Z"),
                                     row(2, created="2026-02-01T00:00:00Z", label=1.0)]), min_labeled=0)
        d = df.set_index("pr_number")
        self.assertEqual(d.loc["1", "label"], 0.0)
        self.assertTrue(pd.isna(d.loc["2", "label"]))
        self.assertEqual(d.loc["2", "exclusion_reason"], "duplicate_bump")
        self.assertEqual(st["duplicate_bumps_unlabeled"], 1)

    def test_unusable_repo(self):
        rows = [row(i, repo="big/r", new=f"1.{i}") for i in range(3)] + [row(9, repo="tiny/r")]
        df, st = clean(pd.DataFrame(rows), min_labeled=3)
        self.assertEqual(st["unusable_repos"], ["tiny/r"])
        self.assertEqual(df[df.repo == "tiny/r"]["exclusion_reason"].iloc[0], "unusable_repo")
        self.assertEqual(int(df[df.repo == "big/r"]["label"].notna().sum()), 3)

    def test_effective_versions_for_range_update(self):
        r = row(1, old="<8,>=7", new=">=7,<9", is_range_update=True,
                resolved_old_version="7.4.0", resolved_new_version="8.0.0")
        df, _ = clean(pd.DataFrame([r, row(2, old="<8", new=">=9", is_range_update=True, new_version=">=9")]),
                      min_labeled=0)
        d = df.set_index("pr_number")
        self.assertEqual((d.loc["1", "eff_old_version"], d.loc["1", "eff_new_version"]), ("7.4.0", "8.0.0"))
        self.assertEqual(d.loc["2", "eff_old_version"], "")  # unresolved range: specifiers are not versions

    def test_all_empty_exclusion_column_from_csv(self):
        # a CSV with no exclusions reads exclusion_reason as float NaN; writing a reason must still work
        df, _ = clean(pd.DataFrame([row(1, exclusion_reason=float("nan")), row(2, exclusion_reason=float("nan"), new="1.2")]),
                      min_labeled=5)
        self.assertEqual(set(df["exclusion_reason"]), {"unusable_repo"})

    def test_normal_pr_uses_title_versions(self):
        df, _ = clean(pd.DataFrame([row(1)]), min_labeled=0)
        self.assertEqual((df["eff_old_version"].iloc[0], df["eff_new_version"].iloc[0]), ("1.0", "1.1"))


if __name__ == "__main__":
    unittest.main()
