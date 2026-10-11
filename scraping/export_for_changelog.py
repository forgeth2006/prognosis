"""Export the PR table in the shape Person A's changelog scraper expects.

Writes data/pr_bumps_for_changelog.csv with repo, pr_number, package, old_version, new_version,
changelog_url, release_notes_url, source_repo_url for every single-package pip bump PR
(grouped bumps, range updates and non-pip PRs have no usable version pair). Join key back to
the PR table: (package, old_version, new_version), or (repo, pr_number).

    python scraping/export_for_changelog.py
"""
import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
COLS = ["repo", "pr_number", "package", "old_version", "new_version",
        "changelog_url", "release_notes_url", "source_repo_url"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", default=str(ROOT / "data" / "pr_metadata_raw.csv"))
    ap.add_argument("--out", default=str(ROOT / "data" / "pr_bumps_for_changelog.csv"))
    args = ap.parse_args()
    df = pd.read_csv(args.inp, dtype=str, keep_default_na=False)
    keep = df[(df["title_parsed"] == "True") & (df["is_grouped"] == "False")
              & (df["is_range_update"] == "False") & (df["ecosystem"] == "pip")]
    keep[COLS].to_csv(args.out, index=False)
    uniq = keep[["package", "old_version", "new_version"]].drop_duplicates().shape[0]
    print(f"{len(keep)} bump PRs ({uniq} unique package/version pairs) -> {args.out}")


if __name__ == "__main__":
    main()
