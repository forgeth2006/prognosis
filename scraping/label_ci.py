"""CI outcome labels (PRognosis, Week 4). Implements scraping/LABEL_RULES.md.

Reads data/pr_metadata_raw.csv, applies the static exclusions (no API calls), then for
the remaining PRs looks up CI on the PR's FIRST commit (Dependabot's own commit, before any
human fix is pushed) and assigns:
    label = 1  CI failed on the bump          (breakage)
    label = 0  CI passed on the bump          (clean)
    label = '' excluded - see exclusion_reason

    python scraping/label_ci.py                 # label everything in the raw table
    python scraping/label_ci.py --limit 50      # quick test

Output: data/labeled_prs_v0.csv (+ data/labeled_prs_v0_summary.csv). Re-running resumes.
"""
import argparse
import csv
import re
from pathlib import Path

from github_client import GitHubClient, GitHubError
from scrape_prs import DEFAULT_CACHE, RAW_FIELDS

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IN = ROOT / "data" / "pr_metadata_raw.csv"
DEFAULT_OUT = ROOT / "data" / "labeled_prs_v0.csv"

LABEL_FIELDS = ["first_commit_sha", "n_commits", "has_human_commits", "n_workflow_runs",
                "failed_workflows", "flaky_workflows", "fail_confidence",
                "ci_status", "ci_completed_at", "label", "exclusion_reason"]
OUT_FIELDS = RAW_FIELDS + LABEL_FIELDS

PR_EVENTS = {"pull_request", "pull_request_target"}
FAIL_CONCLUSIONS = {"failure", "timed_out", "startup_failure"}
# Workflows that say nothing about whether the bump broke the build.
IGNORE_WORKFLOW = re.compile(
    r"label|codecov|coverage report|\bcla\b|stale|welcome|dependabot|auto-?merge|"
    r"pre-commit\.ci|release|publish|deploy|preview|triage|"
    r"autofix\.ci|semgrep|title\s+(?:lint|check)|"
    r"add external component comment|dependency review|changelog check", re.I)


def static_exclusion(row, include_range=False):
    """Reason a PR is excluded before any CI lookup, or ''. Order matters: first match wins.

    include_range: keep "Update X requirement from A to B" PRs when their real version pair could be
    recovered from the compare link (resolved_*_version); otherwise they are excluded.
    """
    if row["is_grouped"] == "True":
        return "grouped_bump"
    if row["title_parsed"] != "True":
        return "unparseable_title"
    if row["is_range_update"] == "True":
        if not include_range:
            return "range_update"
        if not row.get("resolved_old_version"):
            return "range_update_no_versions"
    if row["ecosystem"] != "pip":
        # Includes github-actions / docker / npm PRs and any PR touching non-manifest files.
        if row["touches_ci_config"] == "True" and row["ecosystem"] == "other":
            return "touches_ci_config"
        return f"non_pip_or_non_manifest:{row['ecosystem']}"
    if row["bump_type"] in ("downgrade", "unknown"):
        return f"bad_version_delta:{row['bump_type']}"
    return ""


def label_from_runs(runs):
    """Apply CI label rules and use job completion times for verdict timing.

    _ci_completed_at must be populated from the relevant workflow-run attempt's
    job completed_at timestamps before this function is called.
    """
    failed, flaky, passed = [], [], []
    finished = []
    missing_completion_time = False

    for r in runs:
        if r.get("event") not in PR_EVENTS:
            continue

        name = r.get("name") or ""
        if IGNORE_WORKFLOW.search(name):
            continue

        attempt = r.get("run_attempt") or 1
        conclusion = r.get("conclusion")

        if conclusion in FAIL_CONCLUSIONS or conclusion == "success":
            completed_at = r.get("_ci_completed_at") or ""
            if completed_at:
                finished.append(completed_at)
            else:
                missing_completion_time = True

        if conclusion in FAIL_CONCLUSIONS:
            failed.append((name, attempt))
        elif conclusion == "success":
            (flaky if attempt > 1 else passed).append(name)

    verdict_time = (
        max(finished)
        if finished and not missing_completion_time
        else ""
    )

    res = {
        "n_workflow_runs": len(failed) + len(flaky) + len(passed),
        "failed_workflows": ";".join(n for n, _ in failed),
        "flaky_workflows": ";".join(flaky),
        "fail_confidence": "",
        "ci_completed_at": verdict_time,
    }

    if failed:
        res.update(
            ci_status="fail",
            label=1,
            exclusion_reason="",
            fail_confidence=(
                "confirmed"
                if any(a > 1 for _, a in failed)
                else "single_attempt"
            ),
        )
    elif flaky:
        res.update(
            ci_status="flaky",
            label="",
            exclusion_reason="flaky_rerun_passed",
        )
    elif passed:
        res.update(ci_status="pass", label=0, exclusion_reason="")
    else:
        res.update(ci_status="no_ci", label="", exclusion_reason="no_ci_result")

    return res

def is_bot(commit):
    login = (commit.get("author") or {}).get("login") or ""
    name = ((commit.get("commit") or {}).get("author") or {}).get("name") or ""
    return "dependabot" in login.lower() or "dependabot" in name.lower()

def latest_job_completed_at(client, repo, run):
    """Return the latest completed job timestamp for this workflow-run attempt.

    Return an empty string if the timestamp cannot be established.
    Never fall back to the workflow run's updated_at.
    """
    run_id = run.get("id")
    if not run_id:
        return ""

    attempt = int(run.get("run_attempt") or 1)

    try:
        jobs = client.paginate(
            f"/repos/{repo}/actions/runs/{run_id}/attempts/{attempt}/jobs",
            params={"per_page": 100},
            item_key="jobs",
            cache=True,
        )

        timestamps = [
            job["completed_at"]
            for job in jobs
            if (
                job.get("status") == "completed"
                and job.get("completed_at")
            )
        ]

        return max(timestamps, default="")

    except GitHubError as exc:
        print(
            f"warning: CI job timestamps unavailable for "
            f"{repo}, run {run_id}, attempt {attempt}: {exc}"
        )
        return ""

def label_row(client, row):  # noqa: C901
    repo, num = row["repo"], row["pr_number"]

    commits = list(
        client.paginate(
            f"/repos/{repo}/pulls/{num}/commits",
            cache=True,
            max_items=250,
        )
    )

    out = {k: "" for k in LABEL_FIELDS}

    if not commits:
        out.update(ci_status="no_ci", exclusion_reason="no_commits")
        return out

    first = commits[0]
    out.update(
        first_commit_sha=first["sha"],
        n_commits=len(commits),
        has_human_commits=any(not is_bot(c) for c in commits),
    )

    if not is_bot(first):
        out.update(
            ci_status="",
            exclusion_reason="first_commit_not_dependabot",
        )
        return out

    runs = list(
        client.paginate(
            f"/repos/{repo}/actions/runs",
            params={"head_sha": first["sha"]},
            item_key="workflow_runs",
            cache=True,
        )
    )

    for run in runs:
        name = run.get("name") or ""
        conclusion = run.get("conclusion")

        relevant = (
            run.get("event") in PR_EVENTS
            and not IGNORE_WORKFLOW.search(name)
            and (
                conclusion in FAIL_CONCLUSIONS
                or conclusion == "success"
            )
        )

        if relevant:
            run["_ci_completed_at"] = latest_job_completed_at(
                client, repo, run
            )

    out.update(label_from_runs(runs))
    return out

def load_done(path):
    if not path.exists():
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        return {(r["repo"], r["pr_number"]) for r in csv.DictReader(f)}


def summarize(path):
    import pandas as pd
    df = pd.read_csv(path)
    df["included"] = df["label"].notna()
    by_repo = df.groupby("repo").agg(prs=("pr_number", "count"), included=("included", "sum"),
                                     breakages=("label", "sum")).reset_index()
    by_repo["breakage_rate"] = (by_repo["breakages"] / by_repo["included"]).round(3)
    by_repo.to_csv(path.with_name(path.stem + "_summary.csv"), index=False)
    print("\nPer repo:\n" + by_repo.to_string(index=False))
    print("\nExclusion reasons:\n" + df.loc[~df["included"], "exclusion_reason"].value_counts().to_string())
    n, pos = int(df["included"].sum()), int(df["label"].sum())
    print(f"\nTOTAL: {len(df)} PRs, {n} labeled, {pos} breakages ({pos / n:.1%})" if n else "\nNo labeled PRs.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", default=str(DEFAULT_IN))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    ap.add_argument("--include-range-updates", action="store_true",
                    help="label range-update PRs too (needs resolved versions from the compare link)")
    ap.add_argument("--limit", type=int, help="only process the first N unlabeled PRs (testing)")
    args = ap.parse_args()

    out = Path(args.out)
    done = load_done(out)
    with open(args.inp, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if (r["repo"], r["pr_number"]) not in done]
    if args.limit:
        rows = rows[:args.limit]
    client = GitHubClient(cache_dir=args.cache_dir)
    new_file = not out.exists() or out.stat().st_size == 0
    with open(out, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=OUT_FIELDS)
        if new_file:
            w.writeheader()
        for i, row in enumerate(rows, 1):
            reason = static_exclusion(row, args.include_range_updates)
            if reason:
                lab = {k: "" for k in LABEL_FIELDS}
                lab.update(exclusion_reason=reason)
            else:
                try:
                    lab = label_row(client, row)
                except GitHubError as e:
                    print(f"  skip {row['repo']}#{row['pr_number']}: {e}")
                    continue
            w.writerow({**row, **lab})
            fh.flush()
            if i % 50 == 0:
                print(f"{i}/{len(rows)} processed ({client.requests_made} API requests)")
    summarize(out)


if __name__ == "__main__":
    main()
