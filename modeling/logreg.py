"""Week 9: logistic regression v1 vs the baseline, same time-ordered folds.
    python modeling/week9_logreg.py            (add --cv loro for leave-one-repo-out)
"""
import argparse

import pandas as pd
from common import (FEATURES, baseline_fp, evaluate, get_splits, load, logreg_fp,
                    make_logreg, report, save)

parser = argparse.ArgumentParser()
parser.add_argument("--cv", choices=["time", "loro"], default="time")
parser.add_argument("--chunks", type=int, default=5)
a = parser.parse_args()

df = load()
splits = get_splits(df, a.cv, a.chunks)
rows = []
for name, fp in [("baseline (major bump)", baseline_fp), ("logreg v1", logreg_fp())]:
    oof, folds = evaluate(df, fp, splits)
    rows.append(report(name, df, oof, folds))
summary = pd.DataFrame(rows)
save(summary, f"week9_summary_{a.cv}.csv")

m = make_logreg().fit(df[FEATURES], df["label"])
coef = pd.Series(m[-1].coef_[0], index=m[:-1].get_feature_names_out())
print("\nLargest coefficients (standardized features, fit on all data):")
print(coef.reindex(coef.abs().sort_values(ascending=False).index).head(12).round(3).to_string())