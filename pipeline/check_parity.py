"""Check that the live feature code reproduces the frozen training table (Person C).

    python pipeline/check_parity.py

Takes 150 random PRs from feature_table_v2.csv, rebuilds their features through the live path
(compute_features) from the raw labeled rows and the training snapshots, and compares column by column.
The historical rate is checked on the newest PR (the only one whose history is unchanged when it is
treated as 'new'). Changelog features are skipped: the live path leaves them 'not scraped' on purpose.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from features_live import CHANGELOG_COLS, FEATURES, ROOT, compute_features, prep  # noqa: E402

D = ROOT / "data"
HIST = ["hist_k", "hist_n", "hist_rate", "hist_global_rate"]
KEY = ["repo", "pr_number"]


def compare(a, b, cols):
    bad = {}
    for c in cols:
        if not (pd.api.types.is_numeric_dtype(a[c]) and pd.api.types.is_numeric_dtype(b[c])):
            n = int((a[c].astype(str) != b[c].astype(str)).sum())
        else:
            n = int((~np.isclose(a[c].astype(float), b[c].astype(float), equal_nan=True)).sum())
        if n:
            bad[c] = n
    return bad


ft = pd.read_csv(D / "feature_table_v2.csv")
lab = pd.read_csv(D / "labeled_prs_v2.csv")
lab = lab[lab["label"].notna()]
snaps = pd.read_csv(D / "graph_snapshots_v2.csv")
index = pd.read_csv(D / "graph_snapshots_index_v2.csv")
failed = False

sample = ft.sample(150, random_state=0)[KEY]
new = lab.merge(sample, on=KEY)
rest = lab.merge(sample, on=KEY, how="left", indicator=True)
rest = rest[rest["_merge"] == "left_only"].drop(columns="_merge")
feat = compute_features(new, rest, snaps, index)
a = prep(feat).set_index(KEY).sort_index()
b = prep(ft).set_index(KEY).loc[a.index]
cols = [c for c in FEATURES if c not in HIST and c not in CHANGELOG_COLS]
bad = compare(a, b, cols)
print(f"bump + graph features, {len(a)} PRs, {len(cols)} columns:",
      "all match" if not bad else f"MISMATCH {bad}")
failed |= bool(bad)

newest = lab.sort_values("created_at").tail(1)
others = lab.drop(newest.index)
f1 = compute_features(newest, others, snaps, index)
a1 = prep(f1).set_index(KEY)
b1 = prep(ft).set_index(KEY).loc[a1.index]
bad = compare(a1, b1, HIST)
print("historical rate on the newest PR:", "match" if not bad else f"MISMATCH {bad}")
failed |= bool(bad)

print("PARITY", "FAILED" if failed else "OK")
sys.exit(1 if failed else 0)