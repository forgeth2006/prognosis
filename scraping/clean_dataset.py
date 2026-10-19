"""Cleaning pass 1 (PRognosis, Week 5): labeled_prs_v0.csv -> labeled_prs_v1.csv.

Steps (each is reported, nothing is dropped silently):
  1. effective versions: eff_old_version / eff_new_version = the real version pair
     (resolved_* for range updates, the title versions otherwise) - the join key for changelogs.
  2. dedupe: exact repeats of (repo, pr_number) are removed; if the same bump
     (repo, package_norm, eff_old, eff_new) appears in several PRs (Dependabot closed and recreated
     it), only the earliest labeled PR keeps its label, the rest become `duplicate_bump`.
  3. unusable repos: repos with fewer than --min-labeled labeled rows are marked
     `unusable_repo` (rows stay in the file, label blanked, so counts are traceable).

    python scraping/clean_dataset.py
Output: data/labeled_prs_v1.csv, data/labeled_prs_v1_report.csv (per-repo before/after)
"""
import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BUMP_KEY = ["repo", "package_norm", "eff_old_version", "eff_new_version"]


def effective_versions(df):
    src_res = df["resolved_old_version"].fillna("") if "resolved_old_version" in df else pd.Series("", index=df.index)
    df["eff_old_version"] = src_res.where(src_res != "", df["old_version"].fillna(""))
    new_res = df["resolved_new_version"].fillna("") if "resolved_new_version" in df else pd.Series("", index=df.index)
    df["eff_new_version"] = new_res.where(new_res != "", df["new_version"].fillna(""))
    # a range PR without resolved versions has specifiers, not versions: blank them
    unresolved = (df["is_range_update"].astype(str) == "True") & (src_res == "")
    df.loc[unresolved, ["eff_old_version", "eff_new_version"]] = ""
    return df


def clean(df, min_labeled=20):
    n0 = len(df)
    df = df.drop_duplicates(subset=["repo", "pr_number"], keep="first").copy()
    stats = {"rows_in": n0, "exact_duplicates_removed": n0 - len(df)}
    df = effective_versions(df)
    df["exclusion_reason"] = df["exclusion_reason"].astype(object)  # all-empty CSV column reads as float
    df["created_ts"] = pd.to_datetime(df["created_at"], utc=True)

    labeled = df["label"].notna()
    ordered = df[labeled & (df["eff_new_version"] != "")].sort_values("created_ts")
    dup = ordered.duplicated(subset=BUMP_KEY, keep="first")
    dup_idx = ordered.index[dup]
    df.loc[dup_idx, "label"] = float("nan")
    df.loc[dup_idx, "exclusion_reason"] = "duplicate_bump"
    stats["duplicate_bumps_unlabeled"] = len(dup_idx)

    counts = df[df["label"].notna()].groupby("repo").size()
    small = [r for r in df["repo"].unique() if counts.get(r, 0) < min_labeled]
    mask = df["repo"].isin(small) & df["label"].notna()
    df.loc[mask, "label"] = float("nan")
    df.loc[mask, "exclusion_reason"] = "unusable_repo"
    stats["unusable_repos"] = small
    stats["unusable_repo_rows_unlabeled"] = int(mask.sum())
    return df.drop(columns="created_ts"), stats


def repo_report(before, after):
    def agg(d, tag):
        g = d.groupby("repo").agg(**{f"prs{tag}": ("pr_number", "count"),
                                     f"labeled{tag}": ("label", "count"),
                                     f"breakages{tag}": ("label", "sum")})
        return g
    r = agg(before, "_v0").join(agg(after, "_v1"), how="outer").fillna(0).astype(int).reset_index()
    r["breakage_rate_v1"] = (r["breakages_v1"] / r["labeled_v1"].where(r["labeled_v1"] > 0)).round(3)
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", default=str(ROOT / "data" / "labeled_prs_v0.csv"))
    ap.add_argument("--out", default=str(ROOT / "data" / "labeled_prs_v1.csv"))
    ap.add_argument("--min-labeled", type=int, default=20)
    args = ap.parse_args()
    v0 = pd.read_csv(args.inp, dtype={"pr_number": str}, keep_default_na=True)
    v1, stats = clean(v0.copy(), args.min_labeled)
    v1.to_csv(args.out, index=False)
    rep = repo_report(v0, v1)
    rep.to_csv(Path(args.out).with_name(Path(args.out).stem + "_report.csv"), index=False)
    print(rep.to_string(index=False))
    for k, v in stats.items():
        print(f"{k}: {v}")
    n, pos = int(v1["label"].notna().sum()), int(v1["label"].sum())
    print(f"\nlabeled v0: {int(v0['label'].notna().sum())} -> v1: {n}; breakages: {pos} ({pos / n:.1%})" if n else "no labeled rows")


if __name__ == "__main__":
    main()
