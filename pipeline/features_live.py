"""Compute model features for new PRs with the SAME code as training (Person C)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for sub in ("scraping", "graph_features", "modeling"):
    sys.path.insert(0, str(ROOT / sub))

from build_feature_table import add_graph_features  # noqa: E402
from common import COUNTS, FEATURES, NUM, _num  # noqa: E402,F401
from historical_rate import add_historical_rate  # noqa: E402

CHANGELOG_COLS = ["changelog_scraped", "changelog_found", "changelog_chars", "changelog_lines",
                  "has_breaking_keyword"]


def prep(df):
    """Same numeric conversion and log1p as modeling/common.load()."""
    df = df.copy()
    for c in NUM:
        df[c] = _num(df[c])
    for c in COUNTS:
        df[c] = np.log1p(df[c].clip(lower=0))
    return df


def compute_features(new, history, snaps, index):
    """Features for the PRs in `new` (one row each, same order).

    new:     raw bump rows (repo, pr_number, package_norm, created_at, bump columns ...).
    history: labeled PRs (label 0/1, ci_completed_at, closed_at) used for the historical rate.
    snaps, index: output of graph_features/snapshots.py covering each PR's repo and month.
    Changelog features are left as 'not scraped' (see pipeline/README.md).
    """
    new = new.copy()
    new["label"] = np.nan                  # a new PR's verdict is not known yet
    new["ci_completed_at"] = np.nan
    new["closed_at"] = np.nan
    h = history.copy()
    h["_new"], new["_new"] = False, True
    both = pd.concat([h, new], ignore_index=True, sort=False)
    both = add_historical_rate(both)
    out = both[both["_new"]].drop(columns="_new").reset_index(drop=True)
    out = add_graph_features(out, snaps, index)
    out["changelog_scraped"] = 0
    out["changelog_found"] = 0
    for c in ("changelog_chars", "changelog_lines", "has_breaking_keyword"):
        out[c] = np.nan
    missing = [c for c in FEATURES if c not in out.columns]
    if missing:
        raise KeyError(f"feature columns missing after live computation: {missing}")
    assert len(out) == len(new), "feature computation changed the number of PRs"
    return out