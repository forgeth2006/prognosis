"""Point-in-time dependency-graph snapshots (PRognosis, Weeks 5-7).

The Week-4 prototype graphed each repo as it is TODAY, which leaks the future into old PRs.
Here each repo is graphed as it was at the START of every month in which it has a labeled PR,
so a PR created in month M only sees code committed before M began.

For each (repo, month): find the last commit on the default branch before the first of that
month, read its .py files straight from git (no checkout), build the import graph, and record
the package features. Results are cached by commit SHA, so a re-run only analyses new months.

    python graph_features/snapshots.py --labels data/labeled_prs_v1.csv
    python graph_features/snapshots.py --repos aio-libs/yarl --months 2026-03 2026-04

Output: data/graph_snapshots_v1.csv       one row per repo x month x package
        data/graph_snapshots_index_v1.csv one row per repo x month (snapshot exists? which SHA?)
Clones go to graph_features/.checkouts/<owner>__<name>.git (bare, blobs <1 MB only).
"""
import argparse
import subprocess
from pathlib import Path

import pandas as pd

from import_graph import SKIP_DIRS, analyze_graph, build_graph_from_sources

ROOT = Path(__file__).resolve().parents[1]
CHECKOUTS = Path(__file__).resolve().parent / ".checkouts"
OUT = ROOT / "data" / "graph_snapshots_v1.csv"
INDEX = ROOT / "data" / "graph_snapshots_index_v1.csv"
PKG_COLS = ["package", "package_norm", "blast_direct", "blast_direct_src", "blast_direct_tests",
            "blast_transitive", "depth_min", "depth_mean"]


def git(gitdir, *args, text=True, input=None):
    r = subprocess.run(["git", "--git-dir", str(gitdir), *args], capture_output=True, input=input,
                       text=text, check=True)
    return r.stdout


def clone_bare(repo, base=CHECKOUTS):
    """Bare clone with full history but without very large blobs; fetch if it already exists."""
    dest = Path(base) / (repo.replace("/", "__") + ".git")
    if dest.exists():
        subprocess.run(["git", "--git-dir", str(dest), "fetch", "-q", "origin", "+HEAD:refs/heads/snapshot-head"],
                       check=True)
    else:
        Path(base).mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "-q", "--bare", "--filter=blob:limit=1m",
                        f"https://github.com/{repo}", str(dest)], check=True)
        subprocess.run(["git", "--git-dir", str(dest), "branch", "-f", "snapshot-head", "HEAD"], check=True)
    return dest


def month_start(month):
    """'2026-03' -> '2026-03-01T00:00:00+00:00' (git --before takes this)."""
    return f"{month}-01T00:00:00+00:00"


def sha_before(gitdir, month, ref="snapshot-head"):
    """Last commit on ref strictly before the start of `month`, or '' if the repo did not exist yet."""
    out = git(gitdir, "rev-list", "-1", f"--before={month_start(month)}", ref).strip()
    return out


def read_py_sources(gitdir, sha):
    """{path: text} for every analysable .py file in the tree at sha, read via one cat-file batch."""
    names = git(gitdir, "ls-tree", "-r", "--name-only", sha).splitlines()
    names = [n for n in names if n.endswith(".py") and not (set(Path(n).parts) & SKIP_DIRS)]
    if not names:
        return {}
    req = "".join(f"{sha}:{n}\n" for n in names).encode()
    raw = subprocess.run(["git", "--git-dir", str(gitdir), "cat-file", "--batch"], input=req,
                         capture_output=True, check=True).stdout
    out, pos = {}, 0
    for n in names:
        end = raw.index(b"\n", pos)
        header = raw[pos:end].split()
        if len(header) == 3 and header[1] == b"blob":
            size = int(header[2])
            out[n] = raw[end + 1:end + 1 + size].decode("utf-8", errors="replace")
            pos = end + 1 + size + 1
        else:  # missing / oversized blob
            pos = end + 1
    return out


def snapshot_rows(gitdir, repo, month, cache):
    """(index_row, package_rows) for one repo-month; cache maps sha -> package rows."""
    sha = sha_before(gitdir, month)
    idx = {"repo": repo, "snapshot_month": month, "snapshot_sha": sha, "snapshot_exists": bool(sha),
           "n_files": 0, "n_packages": 0, "parse_failures": 0}
    if not sha:
        return idx, []
    if sha not in cache:
        G, stats = build_graph_from_sources(read_py_sources(gitdir, sha))
        cache[sha] = (analyze_graph(G, stats, repo), stats)
    rows, stats = cache[sha]
    idx.update(n_files=stats["n_files"], n_packages=len(rows), parse_failures=stats["parse_failures"])
    out = [{**{c: r[c] for c in PKG_COLS}, "repo": repo, "snapshot_month": month, "snapshot_sha": sha}
           for r in rows]
    return idx, out


def months_needed(labels_path):
    df = pd.read_csv(labels_path, usecols=["repo", "created_at", "label"])
    df = df[df["label"].notna()]
    df["month"] = pd.to_datetime(df["created_at"], utc=True).dt.strftime("%Y-%m")
    return {repo: sorted(g["month"].unique()) for repo, g in df.groupby("repo")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", default=str(ROOT / "data" / "labeled_prs_v1.csv"))
    ap.add_argument("--repos", nargs="*", help="only these repos (with --months)")
    ap.add_argument("--months", nargs="*", help="YYYY-MM list; default: months present in --labels")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--index-out", default=str(INDEX))
    args = ap.parse_args()

    need = months_needed(args.labels) if not (args.repos and args.months) else \
        {r: args.months for r in args.repos}
    if args.repos:
        need = {r: need.get(r, args.months or []) for r in args.repos}
    all_rows, all_idx = [], []
    for repo, months in need.items():
        gitdir, cache = clone_bare(repo), {}
        for m in months:
            idx, rows = snapshot_rows(gitdir, repo, m, cache)
            all_idx.append(idx)
            all_rows += rows
        print(f"{repo}: {len(months)} months, {len(cache)} distinct commits analysed", flush=True)
    pd.DataFrame(all_rows, columns=["repo", "snapshot_month", "snapshot_sha"] + PKG_COLS).to_csv(args.out, index=False)
    pd.DataFrame(all_idx).to_csv(args.index_out, index=False)
    missing = sum(not i["snapshot_exists"] for i in all_idx)
    print(f"Saved {len(all_rows)} package rows and {len(all_idx)} snapshots ({missing} with no commit yet) "
          f"to {args.out}")


if __name__ == "__main__":
    main()
