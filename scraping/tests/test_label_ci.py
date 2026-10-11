import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from label_ci import label_from_runs, label_row, static_exclusion  # noqa: E402


def run(name, conclusion, attempt=1, event="pull_request"):
    return {"name": name, "conclusion": conclusion, "run_attempt": attempt, "event": event}


class LabelRuleTests(unittest.TestCase):
    def test_all_pass(self):
        r = label_from_runs([run("Tests", "success"), run("Lint", "success")])
        self.assertEqual((r["ci_status"], r["label"]), ("pass", 0))

    def test_single_failure_is_breakage(self):
        r = label_from_runs([run("Tests", "failure"), run("Lint", "success")])
        self.assertEqual((r["ci_status"], r["label"], r["fail_confidence"]), ("fail", 1, "single_attempt"))
        self.assertEqual(r["failed_workflows"], "Tests")

    def test_failure_after_rerun_is_confirmed(self):
        r = label_from_runs([run("Tests", "failure", attempt=2)])
        self.assertEqual((r["label"], r["fail_confidence"]), (1, "confirmed"))

    def test_rerun_that_passes_is_flaky_and_excluded(self):
        r = label_from_runs([run("Tests", "success", attempt=2), run("Lint", "success")])
        self.assertEqual((r["ci_status"], r["label"], r["exclusion_reason"]), ("flaky", "", "flaky_rerun_passed"))

    def test_real_failure_beats_flaky(self):
        r = label_from_runs([run("Tests", "success", attempt=2), run("Docs", "failure")])
        self.assertEqual(r["label"], 1)

    def test_no_information(self):
        for runs in ([], [run("Tests", "cancelled")], [run("Tests", "skipped")], [run("Tests", None)],
                     [run("Tests", "failure", event="push")], [run("Codecov", "failure")],
                     [run("Dependabot auto-merge", "failure")]):
            r = label_from_runs(runs)
            self.assertEqual((r["ci_status"], r["label"]), ("no_ci", ""), runs)

    def test_ignored_workflow_does_not_mask_real_result(self):
        r = label_from_runs([run("Codecov", "failure"), run("Tests", "success")])
        self.assertEqual(r["label"], 0)


def raw(**kw):
    base = {"is_grouped": "False", "title_parsed": "True", "is_range_update": "False", "ecosystem": "pip",
            "touches_ci_config": "False", "bump_type": "minor"}
    base.update(kw)
    return base


class StaticExclusionTests(unittest.TestCase):
    def test_keep(self):
        self.assertEqual(static_exclusion(raw()), "")

    def test_reasons(self):
        self.assertEqual(static_exclusion(raw(is_grouped="True")), "grouped_bump")
        self.assertEqual(static_exclusion(raw(title_parsed="False")), "unparseable_title")
        self.assertEqual(static_exclusion(raw(is_range_update="True")), "range_update")
        self.assertEqual(static_exclusion(raw(ecosystem="github-actions")), "non_pip_or_non_manifest:github-actions")
        self.assertEqual(static_exclusion(raw(ecosystem="other", touches_ci_config="True")), "touches_ci_config")
        self.assertEqual(static_exclusion(raw(bump_type="downgrade")), "bad_version_delta:downgrade")


class FakeClient:
    """Serves canned responses by URL path suffix."""
    def __init__(self, commits, runs):
        self.commits, self.runs = commits, runs

    def paginate(self, path, params=None, item_key=None, cache=False, max_items=None):
        if path.endswith("/commits"):
            return iter(self.commits)
        if path.endswith("/actions/runs"):
            assert params["head_sha"] == self.commits[0]["sha"], "must look up CI on the FIRST commit"
            return iter(self.runs)
        raise AssertionError(path)


BOT = {"sha": "aaa", "author": {"login": "dependabot[bot]"}, "commit": {"author": {"name": "dependabot[bot]"}}}
HUMAN = {"sha": "bbb", "author": {"login": "maintainer"}, "commit": {"author": {"name": "Maintainer"}}}


class LabelRowTests(unittest.TestCase):
    ROW = {"repo": "o/r", "pr_number": "7"}

    def test_failure_fixed_by_human_still_breakage(self):
        out = label_row(FakeClient([BOT, HUMAN], [run("Tests", "failure")]), self.ROW)
        self.assertEqual((out["label"], out["first_commit_sha"], out["has_human_commits"]), (1, "aaa", True))

    def test_human_first_commit_excluded(self):
        out = label_row(FakeClient([HUMAN], []), self.ROW)
        self.assertEqual(out["exclusion_reason"], "first_commit_not_dependabot")
        self.assertEqual(out["label"], "")

    def test_clean(self):
        out = label_row(FakeClient([BOT], [run("Tests", "success")]), self.ROW)
        self.assertEqual((out["label"], out["has_human_commits"]), (0, False))


if __name__ == "__main__":
    unittest.main()
