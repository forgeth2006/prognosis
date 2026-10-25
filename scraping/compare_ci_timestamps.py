"""Compare the frozen labels with a re-labelled file that uses job-level CI timestamps (PRognosis, Week 15).

    python scraping/label_ci.py --in data/pr_metadata_raw.csv --out data/validation/labeled_prs_jobtime.csv
    python scraping/compare_ci_timestamps.py --new data/validation/labeled_prs_jobtime.csv

Read-only on data/labeled_prs_v2.csv. Answers, in order:
  1. Did any label change? (the timestamp fix must not change labels; any difference is listed)
  2. How many labelled rows have no job timestamp (ci_completed_at blank)?
  3. Lag from creation and rows dated after the PR closed, old vs new.
  4. Purge size per time-ordered fold: old timestamps, new timestamps (blank -> closed_at), new capped at close.
  5. Does the historical-rate feature change? (rows with a different hist_n or |hist_rate| difference > 0.001)
Prints a recommendation on whether a new dataset version is needed.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "graph_features"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_ci_lag import known_capped, purge_sizes  # noqa: E402
from historical_rate import add_historical_rate, known_at  # noqa: E402

KEY = ["repo", "pr_number"]


def prepare(path):
    d = pd.read_csv(path, low_memory=False)
    d = d[pd.to_numeric(d["label"], errors="coerce").isin([0, 1])].copy()
    d["label"] = d["label"].astype(int)
    for c in ("created_at", "ci_completed_at", "closed_at"):
        d[c] = pd.to_datetime(d[c], utc=True, errors="coerce")
    return d


def label_differences(old, new):
    """Rows labelled in one file and not the other, or labelled differently."""
    m = old[KEY + ["label"]].merge(new[KEY + ["label"]], on=KEY, how="outer", suffixes=("_old", "_new"), indicator=True)
    return m[(m["_merge"] != "both") | (m["label_old"] != m["label_new"])]


def lag_summary(d):
    lag = (d["ci_completed_at"] - d["created_at"]).dt.total_seconds() / 3600
    after = (d["ci_completed_at"] - d["closed_at"]).dt.total_seconds() / 3600
    return {"missing": int(d["ci_completed_at"].isna().sum()), "median_h": round(float(lag.median()), 2),
            "p90_h": round(float(lag.quantile(.9)), 1), "over_7d": int((lag > 168).sum()),
            "after_close_1h": int((after > 1).sum())}


def hist_change(old, new, tol=1e-3):
    """Rows whose historical-rate inputs differ when built from old vs new timestamps."""
    m = old.merge(new[KEY + ["ci_completed_at"]], on=KEY, suffixes=("", "_new"))
    a = add_historical_rate(m)
    b = add_historical_rate(m.assign(ci_completed_at=m["ci_completed_at_new"]))
    changed = (a["hist_n"] != b["hist_n"]) | ((a["hist_rate"] - b["hist_rate"]).abs() > tol)
    return int(changed.sum()), float((a["hist_rate"] - b["hist_rate"]).abs().max()), len(m)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--old", default=str(ROOT / "data" / "labeled_prs_v2.csv"))
    ap.add_argument("--new", required=True)
    a = ap.parse_args()
    old, new = prepare(a.old), prepare(a.new)
    print(f"labelled rows: old {len(old)}, new {len(new)}")

    diff = label_differences(old, new)
    print(f"\n1. label differences: {len(diff)}")
    if len(diff):
        print(diff.head(20).to_string(index=False))

    print("\n2-3. timestamps (old = updated_at based, new = job completed_at):")
    print(pd.DataFrame({"old": lag_summary(old), "new": lag_summary(new)}).to_string())

    print("\n4. purge per time-ordered fold (training rows before -> kept):")
    for name, d, k in (("old timestamps", old, known_at(old)),
                       ("new timestamps", new, known_at(new)),
                       ("new, capped at close", new, known_capped(known_at(new), new["closed_at"]))):
        d = d.reset_index(drop=True)
        k = k.reset_index(drop=True)
        print(f"   {name:22s}", ", ".join(f"{x}->{y}" for x, y in purge_sizes(d["created_at"], k)))

    n_changed, max_diff, n = hist_change(old, new)
    print(f"\n5. historical-rate feature: {n_changed} of {n} rows change; largest |hist_rate| difference {max_diff:.4f}")
    print("   (any change in hist_n counts; the model input is hist_rate, so judge by the size of the difference too)")

    ok = len(diff) == 0
    print("\nRECOMMENDATION:",
          ("labels are unchanged; " if ok else "LABELS CHANGED, investigate before anything else; ")
          + ("hist features essentially unchanged: keep v2, document the timestamp fix, rebuild only at the final freeze if wanted."
             if ok and n_changed <= 0.02 * n else
             "hist features change for a noticeable share of rows: propose a v3 dataset (new files, v2 stays) and ask Supreeta to re-run validation on it."))


if __name__ == "__main__":
    main()
