import csv
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from label_ci import static_exclusion  # noqa: E402
from scrape_prs import RAW_FIELDS, bump_prs, pr_row  # noqa: E402


def pr(number, title, login="dependabot[bot]", body=""):
    return {"number": number, "title": title, "user": {"login": login}, "state": "closed",
            "html_url": f"https://github.com/o/r/pull/{number}", "created_at": "2026-01-01T00:00:00Z",
            "closed_at": "2026-01-02T00:00:00Z", "merged_at": "2026-01-02T00:00:00Z", "body": body,
            "base": {"ref": "main"}, "head": {"sha": "abc"}}


class FakeClient:
    def __init__(self, prs, files):
        self.prs, self.files = prs, files

    def paginate(self, path, params=None, item_key=None, cache=False, max_items=None):
        if path.endswith("/pulls"):
            self.last_state = params["state"]
            return iter(self.prs)
        if path.endswith("/files"):
            n = int(path.split("/")[-2])
            return iter([{"filename": f} for f in self.files[n]])
        raise AssertionError(path)


class ScrapeTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient(
            [pr(1, "Bump requests from 2.31.0 to 2.32.0"), pr(2, "Fix bug", login="human"),
             pr(3, "Bump actions/checkout from 4 to 5"), pr(4, "Bump the pip group with 2 updates")],
            {1: ["requirements.txt"], 3: [".github/workflows/ci.yml"], 4: ["requirements.txt"]})

    def test_only_dependabot_prs_and_max(self):
        self.assertEqual([p["number"] for p in bump_prs(self.client, "o/r", 10, True)], [1, 3, 4])
        self.assertEqual([p["number"] for p in bump_prs(self.client, "o/r", 2, True)], [1, 3])

    def test_actions_skipped_unless_kept(self):
        self.assertEqual([p["number"] for p in bump_prs(self.client, "o/r", 10, keep_non_pip=False)], [1, 4])
        self.assertEqual([p["number"] for p in bump_prs(self.client, "o/r", 10, keep_non_pip=True)], [1, 3, 4])

    def test_range_update_resolves_versions_from_compare_link(self):
        body = '<a href="https://github.com/o/pytest/compare/7.4.0...8.0.0">Compare view</a>'
        client = FakeClient([pr(9, "Update pytest requirement from <8,>=7 to >=7,<9", body=body)],
                            {9: ["requirements.txt"]})
        row = pr_row(client, "o/r", pr(9, "Update pytest requirement from <8,>=7 to >=7,<9", body=body))
        self.assertEqual((row["resolved_old_version"], row["resolved_new_version"], row["version_source"],
                          row["bump_type"]), ("7.4.0", "8.0.0", "compare_url", "major"))
        row2 = pr_row(client, "o/r", pr(9, "Update pytest requirement from <8,>=7 to >=7,<9"))
        self.assertEqual((row2["bump_type"], row2["resolved_old_version"]), ("range", ""))

    def test_state_option_is_passed_through_and_defaults_to_closed(self):
        list(bump_prs(self.client, "o/r", 10))
        self.assertEqual(self.client.last_state, "closed")
        list(bump_prs(self.client, "o/r", 10, state="open"))
        self.assertEqual(self.client.last_state, "open")

    def test_row_matches_schema_and_roundtrips_through_csv(self):
        rows = [pr_row(self.client, "o/r", p) for p in bump_prs(self.client, "o/r", 10, True)]
        for r in rows:
            self.assertEqual(set(r), set(RAW_FIELDS))
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=RAW_FIELDS)
        w.writeheader()
        w.writerows(rows)
        back = list(csv.DictReader(io.StringIO(buf.getvalue())))
        self.assertEqual([static_exclusion(r) for r in back],
                         ["", "non_pip_or_non_manifest:github-actions", "grouped_bump"])
        self.assertEqual((back[0]["package"], back[0]["bump_type"], back[0]["merged"]), ("requests", "minor", "True"))


if __name__ == "__main__":
    unittest.main()
