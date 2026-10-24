import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


from label_ci import (
    label_from_runs,
    label_row,
    static_exclusion,
    latest_job_completed_at,
)

def run(
    name,
    conclusion,
    attempt=1,
    event="pull_request",
    updated_at="2026-01-01T00:10:00Z",
    _ci_completed_at=None,
):
    result = {
        "name": name,
        "conclusion": conclusion,
        "run_attempt": attempt,
        "event": event,
        "updated_at": updated_at,
    }

    if _ci_completed_at is not None:
        result["_ci_completed_at"] = _ci_completed_at

    return result

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

    def test_ci_completed_at_uses_job_completion_times(self):
        r = label_from_runs([
            run(
                "Tests",
                "success",
                updated_at="2026-10-10T11:00:00Z",
                _ci_completed_at="2025-09-05T11:26:08Z",
            ),
            run(
                "Lint",
                "success",
                updated_at="2026-10-10T11:30:00Z",
                _ci_completed_at="2025-09-05T11:30:00Z",
            ),
            run(
                "Docs",
                "cancelled",
                updated_at="2026-10-11T00:00:00Z",
            ),
        ])

        self.assertEqual(
            r["ci_completed_at"],
            "2025-09-05T11:30:00Z",
        )
    def test_ci_completed_at_is_blank_if_a_counted_run_lacks_timestamp(self):
        r = label_from_runs([
            run(
                "Tests",
                "success",
                _ci_completed_at="2025-09-05T11:26:08Z",
            ),
            run(
                "Lint",
                "success",
                updated_at="2026-10-10T11:30:00Z",
                _ci_completed_at="",
            ),
        ])

        # Keep the label because both workflows passed,
        # but don't claim we know the overall verdict time.
        self.assertEqual(r["label"], 0)
        self.assertEqual(r["ci_status"], "pass")
        self.assertEqual(r["ci_completed_at"], "")

    def test_ignored_workflow_does_not_mask_real_result(self):
        r = label_from_runs([run("Codecov", "failure"), run("Tests", "success")])
        self.assertEqual(r["label"], 0)



    def test_non_test_workflows_are_ignored(self):
        ignored = [
            "autofix.ci",
            "Run Semgrep Checks",
            "PR Title Lint",
            "PR Title Check",
            "Add External Component Comment",
            "Dependency Review",
            "Changelog check",
        ]
        for name in ignored:
            with self.subTest(workflow=name):
                result = label_from_runs([run(name, "failure")])
                self.assertEqual(result["label"], "")
                self.assertEqual(result["ci_status"], "no_ci")

        # Ignoring an unrelated workflow must not hide a real test failure.
        result = label_from_runs([
            run("autofix.ci", "failure"),
            run("Tests", "failure"),
        ])
        self.assertEqual(result["label"], 1)
        self.assertEqual(result["failed_workflows"], "Tests")

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
        self.assertEqual(static_exclusion(raw(is_range_update="True"), include_range=True),
                         "range_update_no_versions")
        self.assertEqual(static_exclusion(raw(is_range_update="True", resolved_old_version="7.4.0"),
                                          include_range=True), "")
        self.assertEqual(static_exclusion(raw(ecosystem="github-actions")), "non_pip_or_non_manifest:github-actions")
        self.assertEqual(static_exclusion(raw(ecosystem="other", touches_ci_config="True")), "touches_ci_config")
        self.assertEqual(static_exclusion(raw(bump_type="downgrade")), "bad_version_delta:downgrade")


class FakeClient:
    """Serves canned responses by URL path."""
    def __init__(self, commits, runs, jobs_by_path=None):
        self.commits = commits
        self.runs = runs
        self.jobs_by_path = jobs_by_path or {}

    def paginate(
        self,
        path,
        params=None,
        item_key=None,
        cache=False,
        max_items=None,
    ):
        if "/actions/runs/" in path and "/attempts/" in path and path.endswith("/jobs"):
            return iter(self.jobs_by_path.get(path, []))

        if path.endswith("/commits"):
            return iter(self.commits)

        if path.endswith("/actions/runs"):
            assert params["head_sha"] == self.commits[0]["sha"], (
                "must look up CI on the FIRST commit"
            )
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

    def test_clean_uses_job_completion_timestamp(self):
        workflow = run(
            "Tests",
            "success",
            attempt=1,
            updated_at="2026-10-10T11:30:00Z",
        )
        workflow["id"] = 12345

        jobs_path = "/repos/o/r/actions/runs/12345/attempts/1/jobs"
        client = FakeClient(
            [BOT],
            [workflow],
            jobs_by_path={
                jobs_path: [
                    {
                        "status": "completed",
                        "completed_at": "2025-09-05T11:26:08Z",
                    },
                    {
                        "status": "in_progress",
                        "completed_at": "2026-10-10T11:30:00Z",
                    },
                ]
            },
        )

        out = label_row(client, self.ROW)

        self.assertEqual(out["label"], 0)
        self.assertEqual(
            out["ci_completed_at"],
            "2025-09-05T11:26:08Z",
        )
class FakeJobsClient:
    def __init__(self, jobs):
        self.jobs = jobs
        self.last_call = None

    def paginate(
        self,
        path,
        params=None,
        item_key=None,
        cache=False,
        max_items=None,
    ):
        self.last_call = {
            "path": path,
            "params": params,
            "item_key": item_key,
            "cache": cache,
        }
        return iter(self.jobs)


class LatestJobCompletedAtTests(unittest.TestCase):
    def test_uses_latest_completed_job_for_exact_attempt(self):
        client = FakeJobsClient([
            {
                "status": "completed",
                "completed_at": "2025-09-05T11:26:08Z",
            },
            {
                "status": "completed",
                "completed_at": "2025-09-05T11:30:00Z",
            },
            {
                "status": "in_progress",
                "completed_at": "2026-10-10T11:00:00Z",
            },
        ])

        result = latest_job_completed_at(
            client,
            "aio-libs/yarl",
            {"id": 12345, "run_attempt": 2},
        )

        self.assertEqual(result, "2025-09-05T11:30:00Z")
        self.assertEqual(
            client.last_call["path"],
            "/repos/aio-libs/yarl/actions/runs/12345/attempts/2/jobs",
        )
        self.assertEqual(client.last_call["item_key"], "jobs")
        self.assertTrue(client.last_call["cache"])

    def test_missing_run_id_returns_empty_without_api_call(self):
        client = FakeJobsClient([])

        result = latest_job_completed_at(
            client,
            "aio-libs/yarl",
            {"run_attempt": 1},
        )

        self.assertEqual(result, "")
        self.assertIsNone(client.last_call)

    def test_no_completed_job_timestamps_returns_empty(self):
        client = FakeJobsClient([
            {"status": "completed", "completed_at": None},
            {"status": "in_progress", "completed_at": None},
        ])

        result = latest_job_completed_at(
            client,
            "aio-libs/yarl",
            {"id": 12345, "run_attempt": 1},
        )

        self.assertEqual(result, "")
if __name__ == "__main__":
    unittest.main()
