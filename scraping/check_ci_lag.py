"""How trustworthy is ci_completed_at? (PRognosis, Week 13 data check)

ci_completed_at is the `updated_at` of the PR's workflow runs. GitHub can change updated_at long after a run
finished, so for some PRs it is later than the day the PR was closed. This prints the lag from creation, how many
rows are dated after their PR closed, and how large a time-ordered purge is with and without capping at close.

    python scraping/check_ci_lag.py            # run from the repo root; read-only on data/
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def known_capped(ci, closed):
    """Time the verdict was known, never later than the PR's close: min(ci_completed_at, closed_at)."""
    return pd.concat([ci, closed], axis=1).min(axis=1)


def purge_sizes(created, known, chunks=5):
    """(rows before, rows kept) per fold for equal-count time-ordered chunks."""
    order = created.sort_values().index
    chunk = pd.Series(pd.cut(np.arange(len(order)), chunks, labels=False), index=order)
    out = []
    for c in range(1, chunks):
        start = created[chunk == c].min()
        tr = chunk[chunk < c].index
        out.append((len(tr), int((known[tr] < start).sum())))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", default=str(ROOT / "data" / "labeled_prs_v2.csv"))
    a = ap.parse_args()
    d = pd.read_csv(a.labels, low_memory=False)
    d = d[d["label"].notna()].copy()
    for c in ("created_at", "ci_completed_at", "closed_at"):
        d[c] = pd.to_datetime(d[c], utc=True, errors="coerce")
    lag = (d["ci_completed_at"] - d["created_at"]).dt.total_seconds() / 3600
    after = (d["ci_completed_at"] - d["closed_at"]).dt.total_seconds() / 3600
    print(f"labelled rows: {len(d)}; lag from creation median {lag.median():.2f}h, p90 {lag.quantile(.9):.1f}h, "
          f">7 days: {(lag > 168).sum()}")
    print(f"dated more than 1h after the PR closed: {(after > 1).sum()} "
          f"(more than 7 days after: {(after > 168).sum()})")
    raw = d["ci_completed_at"].fillna(d["closed_at"])
    capped = known_capped(d["ci_completed_at"], d["closed_at"])
    for name, k in (("as stored", raw), ("capped at close", capped)):
        print(f"purge per fold, {name}: " + ", ".join(f"{a}->{b}" for a, b in purge_sizes(d["created_at"], k)))


if __name__ == "__main__":
    main()
