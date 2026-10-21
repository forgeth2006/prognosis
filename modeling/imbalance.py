"""Week 10: imbalance handling. Weights and oversampling are applied to TRAINING data only.
    python modeling/week10_imbalance.py        (add --cv loro for leave-one-repo-out)
"""
import argparse

import pandas as pd
from common import FEATURES, evaluate, get_splits, load, logreg_fp, make_logreg, report, save

parser = argparse.ArgumentParser()
parser.add_argument("--cv", choices=["time", "loro"], default="time")
parser.add_argument("--chunks", type=int, default=5)
a = parser.parse_args()


def oversample_fp(seed=0):
    def fp(tr, te):
        pos, neg = tr[tr["label"] == 1], tr[tr["label"] == 0]
        boosted = pd.concat([neg, pos.sample(len(neg), replace=True, random_state=seed)])
        m = make_logreg().fit(boosted[FEATURES], boosted["label"])
        return m.predict_proba(te[FEATURES])[:, 1]
    return fp


df = load()
splits = get_splits(df, a.cv, a.chunks)
rows = []
for name, fp in [("logreg, no handling", logreg_fp()),
                 ("logreg, class_weight=balanced", logreg_fp("balanced")),
                 ("logreg, oversampled", oversample_fp())]:
    oof, folds = evaluate(df, fp, splits)
    rows.append(report(name, df, oof, folds))
summary = pd.DataFrame(rows)
print("\n" + summary[["model", "pr_auc", "ci_lo", "ci_hi", "prec_top10", "rec_top10"]].round(3).to_string(index=False))
save(summary, f"week10_summary_{a.cv}.csv")