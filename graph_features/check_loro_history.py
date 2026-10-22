"""How much of the historical-breakage evidence comes from the SAME repo? (PRognosis, Week 9-12 data check)

In leave-one-repo-out (LORO) evaluation the held-out repo should look like a repo the model has never seen.
But hist_* features pool verdicts across repos, so for a held-out PR they still include that repo's own
earlier PRs for the same package. This script measures that share and writes a copy of the feature table whose
hist_* columns use ONLY other repos' earlier verdicts, so LORO can be re-run on it.

    python graph_features/check_loro_history.py --out /tmp/feature_table_xrepo.csv

Same smoothing as historical_rate.py (PRIOR_RATE 0.10, PRIOR_STRENGTH 20, M 10). Read-only on data/.
Re-run the modeling LORO on --out (and once without hist_* columns) and report all three side by side.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
M, PRIOR_RATE, PRIOR_STRENGTH = 10.0, 0.10, 20.0


def cross_repo_history(f):
    """Return (table with cross-repo-only hist_* columns, same-repo evidence counts per row)."""
    created = pd.to_datetime(f["created_at"], utc=True)
    known = pd.to_datetime(f["ci_completed_at"], utc=True, errors="coerce").fillna(
        pd.to_datetime(f["closed_at"], utc=True, errors="coerce"))
    y, pkg, repo = f["label"].to_numpy(), f["package_norm"].to_numpy(), f["repo"].to_numpy()
    k_l, n_l, g_l, r_l, same = [], [], [], [], []
    for i in range(len(f)):
        prior = (known < created.iloc[i]).to_numpy()
        same_pkg = prior & (pkg == pkg[i])
        same.append((int((same_pkg & (repo == repo[i])).sum()), int(same_pkg.sum())))
        oth = prior & (repo != repo[i])
        p0 = (y[oth].sum() + PRIOR_STRENGTH * PRIOR_RATE) / (oth.sum() + PRIOR_STRENGTH)
        sp = oth & (pkg == pkg[i])
        k, n = y[sp].sum(), sp.sum()
        k_l.append(k); n_l.append(n); g_l.append(p0); r_l.append((k + M * p0) / (n + M))
    out = f.copy()
    out["hist_k"], out["hist_n"], out["hist_global_rate"], out["hist_rate"] = k_l, n_l, g_l, r_l
    return out, np.array(same)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--table", default=str(ROOT / "data" / "feature_table_v2.csv"))
    ap.add_argument("--labeled", default=str(ROOT / "data" / "labeled_prs_v2.csv"))
    ap.add_argument("--out", required=True, help="where to write the cross-repo-only feature table (not data/)")
    a = ap.parse_args()
    f = pd.read_csv(a.table)
    l = pd.read_csv(a.labeled)[["repo", "pr_number", "ci_completed_at", "closed_at"]]
    f = f.merge(l, on=["repo", "pr_number"], how="left")
    xf, s = cross_repo_history(f)
    has = s[:, 1] > 0
    print(f"rows with any earlier same-package evidence: {has.sum()} of {len(f)}")
    print(f"  of those, {(s[has, 0] > 0).mean():.0%} include same-repo evidence")
    print(f"  same-repo share of all evidence: {s[has, 0].sum() / s[has, 1].sum():.0%}")
    xf.drop(columns=["ci_completed_at", "closed_at"]).to_csv(a.out, index=False)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
