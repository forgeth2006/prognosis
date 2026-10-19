"""Feature table + Checkpoint 2 checks (PRognosis, Weeks 7-8).

Joins, for every LABELED PR:
  bump features        (from the PR table: version deltas, bump type, flags)
  graph features       (point-in-time monthly snapshot: blast radius, depth)
  historical rate      (expanding window, strictly earlier CI verdicts only)
  changelog features   (Person A's scraper output, joined on package + versions)
and then runs the four Checkpoint 2 checks from CONTRIBUTING.md, writing a report:
  1. row counts match between labeled data and feature table (no silent loss/duplication)
  2. class balance reported (and the scarcity trigger flagged)
  3. no unexplained null features (expected nulls are listed and explained)
  4. the historical-rate feature uses only earlier data (brute-force recomputation on a sample)

    python graph_features/build_feature_table.py
Output: data/feature_table_v1.csv, data/dataset_checks_v1.md   (exit code 1 if any check FAILS)
"""
import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from historical_rate import M, PRIOR_RATE, PRIOR_STRENGTH, add_historical_rate, known_at

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data"

ID_COLS = ["repo", "pr_number", "package_norm", "created_at"]
LABEL = "label"
META_COLS = ["fail_confidence"]  # describes the outcome: for sensitivity analysis only, NOT a feature
BUMP_FEATURES = ["bump_type", "major_delta", "minor_delta", "patch_delta", "is_prerelease",
                 "is_zero_major", "is_range_update"]
GRAPH_FEATURES = ["blast_direct", "blast_direct_src", "blast_direct_tests", "blast_transitive",
                  "depth_min", "depth_mean", "not_in_graph", "depth_missing", "snapshot_missing"]
HIST_FEATURES = ["hist_rate", "hist_n", "hist_k", "hist_global_rate"]
CHANGELOG_FEATURES = ["changelog_scraped", "changelog_found", "changelog_chars", "changelog_lines",
                      "has_breaking_keyword"]
FEATURES = BUMP_FEATURES + GRAPH_FEATURES + HIST_FEATURES + CHANGELOG_FEATURES
# Columns that exist in the labeled table but describe what happened AFTER/BECAUSE of the bump.
OUTCOME_COLS = ["ci_status", "ci_completed_at", "n_workflow_runs", "failed_workflows", "flaky_workflows",
                "fail_confidence", "first_commit_sha", "n_commits", "has_human_commits", "state",
                "merged", "closed_at", "merged_at", "exclusion_reason", "label"]
MIN_POSITIVES = 100  # plan: below ~100-150 positives -> trigger the data-scarcity contingency


def norm(name):
    return re.sub(r"[-_.]+", "-", str(name)).lower()


def month_of(created):
    return pd.to_datetime(created, utc=True).dt.strftime("%Y-%m")


def add_graph_features(df, snaps, index):
    df = df.copy()
    df["snapshot_month"] = month_of(df["created_at"])
    n = len(df)
    df = df.merge(index[["repo", "snapshot_month", "snapshot_exists"]], on=["repo", "snapshot_month"], how="left")
    assert len(df) == n, "snapshot index has duplicate (repo, month) keys"
    snaps = snaps.drop(columns=["package", "snapshot_sha"], errors="ignore")
    df = df.merge(snaps, on=["repo", "snapshot_month", "package_norm"], how="left", indicator="_g")
    assert len(df) == n, "graph snapshots have duplicate (repo, month, package) keys"
    exists = df["snapshot_exists"].fillna(False).astype(bool)
    df["snapshot_missing"] = (~exists).astype(int)
    df["not_in_graph"] = ((df["_g"] == "left_only") & exists).astype(int)
    for c in ["blast_direct", "blast_direct_src", "blast_direct_tests", "blast_transitive"]:
        df[c] = df[c].fillna(0).astype(int)
    df["depth_missing"] = df["depth_min"].isna().astype(int)
    return df.drop(columns=["_g", "snapshot_exists"])


def add_changelog_features(df, changelog):
    df = df.copy()
    n = len(df)
    c = changelog.copy()
    c["package_norm"] = c["package"].map(norm)
    c = c.rename(columns={"old_version": "eff_old_version", "new_version": "eff_new_version"})
    for col in ("eff_old_version", "eff_new_version"):
        c[col] = c[col].astype(str)
    c = c.drop_duplicates(subset=["package_norm", "eff_old_version", "eff_new_version"])
    keep = ["package_norm", "eff_old_version", "eff_new_version", "changelog_found", "changelog_chars",
            "changelog_lines", "has_breaking_keyword"]
    df = df.merge(c[keep], on=["package_norm", "eff_old_version", "eff_new_version"], how="left",
                  indicator="_c")
    assert len(df) == n, "changelog join changed the row count"
    df["changelog_scraped"] = (df["_c"] == "both").astype(int)
    df["changelog_found"] = df["changelog_found"].map({True: 1, False: 0, "True": 1, "False": 0}).fillna(0).astype(int)
    return df.drop(columns="_c")


def build(labeled_all, snaps, index, changelog):
    df = labeled_all[labeled_all[LABEL].notna()].copy().reset_index(drop=True)
    df["package_norm"] = df["package_norm"].fillna(df["package"].map(norm))
    df = add_historical_rate(df)
    df = add_graph_features(df, snaps, index)
    df = add_changelog_features(df, changelog)
    for b in ("is_prerelease", "is_zero_major", "is_range_update"):
        df[b] = df[b].map({True: 1, False: 0, "True": 1, "False": 0}).astype("Int64")
    df[LABEL] = df[LABEL].astype(int)
    cols = ID_COLS + [LABEL] + META_COLS + FEATURES
    return df[cols + ["snapshot_month"]], df


# ---------------------------------------------------------------- checks
def expected_null_mask(ft, col):
    if col in ("depth_min", "depth_mean"):
        return ft["depth_missing"] == 1
    if col in ("changelog_chars", "changelog_lines", "has_breaking_keyword"):
        return ft["changelog_found"] == 0
    if col in ("major_delta", "minor_delta", "patch_delta", "is_prerelease", "is_zero_major"):
        return ft["bump_type"].isin(["range", "unknown"])
    return pd.Series(False, index=ft.index)


def check_rows(ft, labeled_all):
    n_lab = int(labeled_all[LABEL].notna().sum())
    ok = len(ft) == n_lab and not ft.duplicated(["repo", "pr_number"]).any()
    return ok, f"labeled rows in labeled_prs_v1 = {n_lab}; feature-table rows = {len(ft)}; " \
               f"duplicate (repo, pr_number) keys = {int(ft.duplicated(['repo', 'pr_number']).sum())}"


def check_balance(ft):
    pos, n = int(ft[LABEL].sum()), len(ft)
    per = ft.groupby("repo")[LABEL].agg(["count", "sum"]).rename(columns={"count": "labeled", "sum": "breakages"})
    per["rate"] = (per["breakages"] / per["labeled"]).round(3)
    msg = f"{n} labeled rows, {pos} breakages ({pos / n:.1%})" if n else "no labeled rows"
    warn = pos < MIN_POSITIVES
    return not warn, msg, per, warn


def check_nulls(ft):
    rows, unexplained = [], []
    for c in FEATURES + ID_COLS + [LABEL]:
        nulls = ft[c].isna()
        n = int(nulls.sum())
        if not n:
            continue
        exp = int((nulls & expected_null_mask(ft, c)).sum())
        rows.append((c, n, exp))
        if n != exp:
            unexplained.append(c)
    return not unexplained, rows, unexplained


def check_hist_leakage(df_full, ft, sample=300, seed=0):
    """Recompute hist_k / hist_n / hist_rate by brute force for a random sample of rows."""
    created = pd.to_datetime(df_full["created_at"], utc=True)
    known = known_at(df_full)
    rng = np.random.default_rng(seed)
    pick = rng.choice(len(df_full), size=min(sample, len(df_full)), replace=False)
    bad = []
    for i in pick:
        prior = (known < created.iloc[i]).fillna(False)
        k_all, n_all = int(df_full.loc[prior, LABEL].sum()), int(prior.sum())
        same = prior & (df_full["package_norm"] == df_full["package_norm"].iloc[i])
        k, n = int(df_full.loc[same, LABEL].sum()), int(same.sum())
        p0 = (k_all + PRIOR_STRENGTH * PRIOR_RATE) / (n_all + PRIOR_STRENGTH)
        rate = (k + M * p0) / (n + M)
        if (ft["hist_k"].iloc[i], ft["hist_n"].iloc[i]) != (k, n) or abs(ft["hist_rate"].iloc[i] - rate) > 1e-9:
            bad.append(int(i))
    return not bad, len(pick), sorted(bad)[:10]


def md_table(df):
    head = "| " + " | ".join(map(str, df.columns)) + " |"
    sep = "|" + "---|" * len(df.columns)
    body = ["| " + " | ".join(map(str, r)) + " |" for r in df.itertuples(index=False)]
    return "\n".join([head, sep] + body)


def check_snapshot_time(ft):
    start = pd.to_datetime(ft["snapshot_month"] + "-01", utc=True)
    late = int((start > pd.to_datetime(ft["created_at"], utc=True)).sum())
    return late == 0, late


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", default=str(D / "labeled_prs_v1.csv"))
    ap.add_argument("--snapshots", default=str(D / "graph_snapshots_v1.csv"))
    ap.add_argument("--snapshot-index", default=str(D / "graph_snapshots_index_v1.csv"))
    ap.add_argument("--changelog", default=str(D / "changelog_features.csv"))
    ap.add_argument("--out", default=str(D / "feature_table_v1.csv"))
    ap.add_argument("--report", default=str(D / "dataset_checks_v1.md"))
    a = ap.parse_args()

    labeled_all = pd.read_csv(a.labels, dtype={"pr_number": str, "eff_old_version": str, "eff_new_version": str},
                              keep_default_na=True)
    for c in ("eff_old_version", "eff_new_version"):
        labeled_all[c] = labeled_all[c].fillna("")
    snaps = pd.read_csv(a.snapshots)
    index = pd.read_csv(a.snapshot_index)
    changelog = pd.read_csv(a.changelog, dtype={"old_version": str, "new_version": str})
    ft, full = build(labeled_all, snaps, index, changelog)
    ft.drop(columns="snapshot_month").to_csv(a.out, index=False)

    r_ok, r_msg = check_rows(ft, labeled_all)
    b_ok, b_msg, per_repo, b_warn = check_balance(ft)
    n_ok, null_rows, unexplained = check_nulls(ft)
    h_ok, h_n, h_bad = check_hist_leakage(full, ft)
    s_ok, s_late = check_snapshot_time(ft)
    scraped = float(ft["changelog_scraped"].mean()) if len(ft) else 0.0
    ok = lambda x: "PASS" if x else "FAIL"

    lines = ["# Dataset checks - feature_table_v1 (Checkpoint 2)", "",
             f"1. **Row counts match: {ok(r_ok)}** - {r_msg}",
             f"2. **Class balance reported: PASS** - {b_msg}"
             + (f". WARNING: fewer than {MIN_POSITIVES} positives, the data-scarcity contingency decision is due" if b_warn else ""),
             f"3. **No unexplained null features: {ok(n_ok)}** - "
             + ("none" if not null_rows else "; ".join(f"{c}: {n} null ({e} expected)" for c, n, e in null_rows)),
             f"4. **Historical rate uses only earlier data: {ok(h_ok)}** - brute-force recomputation on {h_n} random rows"
             + ("" if h_ok else f"; mismatching row positions {h_bad}"),
             f"5. **Graph snapshot never newer than the PR: {ok(s_ok)}** - {s_late} rows violate",
             "", "## Coverage notes",
             f"- changelog features matched for {scraped:.0%} of rows (`changelog_scraped`); the rest are unscraped, "
             "not 'no changelog'. Person A's scraper must be run on `data/pr_bumps_for_changelog.csv` first.",
             f"- rows with no repo snapshot at all: {int(ft['snapshot_missing'].sum())}; "
             f"package not imported in its snapshot (dev tool / transitive): {int(ft['not_in_graph'].sum())}; "
             f"depth missing (test-only or not imported): {int(ft['depth_missing'].sum())}",
             "", "## Class balance per repo", "", md_table(per_repo.reset_index()), "",
             "## Column groups",
             f"- ID: {', '.join(ID_COLS)}", f"- label: {LABEL}",
             f"- meta (outcome description, NOT features): {', '.join(META_COLS)}",
             f"- features: {', '.join(FEATURES)}",
             f"- excluded outcome/leakage columns (never features): {', '.join(OUTCOME_COLS)}", ""]
    Path(a.report).write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:9]))
    print(f"\nWrote {a.out} and {a.report}")
    sys.exit(0 if (r_ok and n_ok and h_ok and s_ok) else 1)


if __name__ == "__main__":
    main()
