"""Raw PR metadata scraper (PRognosis, Weeks 2-3).

For each shortlisted repo, lists closed Dependabot PRs (newest first) and records
one row per PR: package, old/new version, bump type, changed-file classification,
changelog links, timestamps. No CI labels yet - see label_ci.py.

Run from the repo root:
    export GITHUB_TOKEN=...            # required for any real volume
    python scraping/scrape_prs.py --repos aio-libs/yarl --max-prs 20      # quick smoke test
    python scraping/scrape_prs.py --max-prs 300                           # whole shortlist

Output: data/pr_metadata_raw.csv (append-only; re-running resumes and skips PRs already saved).
"""
import argparse
import csv
from pathlib import Path

from github_client import GitHubClient, GitHubError
from parse_bump import classify_files, extract_links, parse_title, version_delta

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPOS = Path(__file__).resolve().parent / "shortlist_repos.txt"
DEFAULT_OUT = ROOT / "data" / "pr_metadata_raw.csv"
DEFAULT_CACHE = Path(__file__).resolve().parent / ".cache"
BOT = "dependabot[bot]"

RAW_FIELDS = [
    "repo", "pr_number", "pr_url", "title", "state", "merged", "created_at", "closed_at", "merged_at",
    "base_ref", "head_sha", "package", "package_norm", "old_version", "new_version", "title_parsed",
    "is_grouped", "is_range_update", "bump_type", "is_prerelease", "is_zero_major",
    "major_delta", "minor_delta", "patch_delta",
    "ecosystem", "n_files", "n_non_dependency_files", "touches_ci_config", "files",
    "changelog_url", "release_notes_url", "compare_url", "source_repo_url",
]


def read_repos(args):
    if args.repos:
        return args.repos
    return [ln.strip() for ln in Path(args.repos_file).read_text().splitlines()
            if ln.strip() and not ln.startswith("#")]


def load_done(out):
    """Keys (repo, pr_number) already saved, so a re-run resumes."""
    if not out.exists():
        return set()
    with open(out, newline="", encoding="utf-8") as f:
        return {(r["repo"], r["pr_number"]) for r in csv.DictReader(f)}


def bump_prs(client, repo, max_prs):
    """Yield closed PRs authored by Dependabot, newest first, up to max_prs."""
    seen = 0
    for pr in client.paginate(f"/repos/{repo}/pulls",
                              params={"state": "closed", "sort": "created", "direction": "desc"}):
        if (pr.get("user") or {}).get("login") != BOT:
            continue
        yield pr
        seen += 1
        if seen >= max_prs:
            return


def pr_row(client, repo, pr):
    t = parse_title(pr["title"])
    delta = version_delta(t["old_version"], t["new_version"]) if t["title_parsed"] and not t["is_range_update"] \
        else {"bump_type": "range" if t["is_range_update"] else "unknown", "is_prerelease": "",
              "is_zero_major": "", "major_delta": "", "minor_delta": "", "patch_delta": ""}
    files = [f["filename"] for f in client.paginate(
        f"/repos/{repo}/pulls/{pr['number']}/files", cache=True, max_items=300)]
    fc = classify_files(files)
    links = extract_links(pr.get("body"))
    return {
        "repo": repo, "pr_number": pr["number"], "pr_url": pr["html_url"], "title": pr["title"],
        "state": pr["state"], "merged": bool(pr.get("merged_at")), "created_at": pr["created_at"],
        "closed_at": pr.get("closed_at") or "", "merged_at": pr.get("merged_at") or "",
        "base_ref": pr["base"]["ref"], "head_sha": pr["head"]["sha"],
        **t, **delta, **fc, "files": ";".join(files[:20]), **links,
    }


def scrape_repo(client, repo, max_prs, writer, done, fh):
    n_new = n_skip = 0
    for pr in bump_prs(client, repo, max_prs):
        if (repo, str(pr["number"])) in done:
            n_skip += 1
            continue
        try:
            row = pr_row(client, repo, pr)
        except GitHubError as e:
            print(f"  skip #{pr['number']}: {e}")
            continue
        writer.writerow(row)
        fh.flush()
        n_new += 1
    print(f"{repo}: {n_new} new PRs, {n_skip} already saved")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repos", nargs="*", help="owner/name list (default: scraping/shortlist_repos.txt)")
    ap.add_argument("--repos-file", default=str(DEFAULT_REPOS))
    ap.add_argument("--max-prs", type=int, default=300, help="max Dependabot PRs per repo, newest first")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = load_done(out)
    client = GitHubClient(cache_dir=args.cache_dir)
    new_file = not out.exists() or out.stat().st_size == 0
    with open(out, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=RAW_FIELDS)
        if new_file:
            writer.writeheader()
        for repo in read_repos(args):
            try:
                scrape_repo(client, repo, args.max_prs, writer, done, fh)
            except GitHubError as e:
                print(f"{repo}: FAILED ({e})")
    print(f"Done. {client.requests_made} API requests. Saved to {out}")


if __name__ == "__main__":
    main()
