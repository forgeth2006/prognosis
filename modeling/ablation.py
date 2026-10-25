"""Week 16: which feature groups carry the signal? (Person C)

    python modeling/ablation.py

Final-model recipe (balanced logistic regression + Platt calibration) on the strict time-ordered folds
(label purge included), with one feature group removed at a time, plus 'bump only'. The PR-AUC difference
against the full model comes with a 95% bootstrap interval over PRs.
"""
import numpy as np
import pandas as pd
from common import CAT, FEATURES, NUM, ap, boot_ci, evaluate, load, save, time_splits
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from validation import known_time

GROUPS = {
    "bump": ["bump_type", "major_delta", "minor_delta", "patch_delta", "is_prerelease", "is_zero_major",
             "is_range_update"],
    "graph": ["blast_direct", "blast_direct_src", "blast_direct_tests", "blast_transitive", "depth_min",
              "depth_mean", "not_in_graph", "depth_missing", "snapshot_missing"],
    "history": ["hist_rate", "hist_n", "hist_k", "hist_global_rate"],
    "changelog": ["changelog_scraped", "changelog_found", "changelog_chars", "changelog_lines",
                  "has_breaking_keyword"],
}
assert sorted(sum(GROUPS.values(), [])) == sorted(FEATURES), "groups must cover FEATURES exactly"


def make_model(cols):
    parts = []
    num = [c for c in cols if c in NUM]
    cat = [c for c in cols if c in CAT]
    if num:
        parts.append(("num", make_pipeline(SimpleImputer(strategy="constant", fill_value=0), StandardScaler()), num))
    if cat:
        parts.append(("cat", OneHotEncoder(handle_unknown="ignore"), cat))
    return Pipeline([("pre", ColumnTransformer(parts)),
                     ("clf", LogisticRegression(max_iter=2000, class_weight="balanced"))])


def final_recipe(cols):
    """Fit on the older 75% of the training window, Platt-calibrate on the newest 25%."""
    def fp(tr, te):
        tr = tr.sort_values("created_at")
        cut = int(len(tr) * 0.75)
        fit, cal = tr.iloc[:cut], tr.iloc[cut:]
        m = make_model(cols).fit(fit[cols], fit["label"])
        s_cal, s_te = m.decision_function(cal[cols]), m.decision_function(te[cols])
        platt = LogisticRegression(C=1e6).fit(s_cal.reshape(-1, 1), cal["label"])
        return platt.predict_proba(s_te.reshape(-1, 1))[:, 1]
    return fp


df = load()
known, _ = known_time(df, "data/labeled_prs_v2.csv")
splits = []
for name, tr, te in time_splits(df, 5):
    start = df.loc[te, "created_at"].min()
    splits.append((name, tr[(known.loc[tr] < start).to_numpy()], te))

variants = {"all features": FEATURES, "bump only": GROUPS["bump"]}
for g in GROUPS:
    variants[f"without {g}"] = [c for c in FEATURES if c not in GROUPS[g]]

oofs = {}
for name, cols in variants.items():
    oofs[name], folds = evaluate(df, final_recipe(cols), splits)
    oofs[name + "_folds"] = " / ".join(f"{v:.3f}" for v in folds["pr_auc"])

m = oofs["all features"].notna()
y = df.loc[m, "label"].to_numpy()
full = oofs["all features"][m].to_numpy()
rows = []
for name in variants:
    p = oofs[name][m].to_numpy()
    lo, hi = boot_ci(y, p)
    row = dict(variant=name, n_features=len(variants[name]), pr_auc=ap(y, p), ci_lo=lo, ci_hi=hi,
               fold_pr_auc=oofs[name + "_folds"])
    if name != "all features":
        dlo, dhi = boot_ci(y, p, p2=full)
        row.update(diff_vs_all=ap(y, p) - ap(y, full), diff_lo=dlo, diff_hi=dhi)
    rows.append(row)
res = pd.DataFrame(rows)
print(f"pooled test PRs: {len(y)}, breakages: {int(y.sum())}, floor: {y.mean():.3f}\n")
print(res.round(3).to_string(index=False))
save(res, "week16_ablation.csv")