"""Week 12: sufficiency test, gradient boosting vs logistic regression (same folds, same calibration).
    python modeling/week12_sufficiency.py      (add --cv loro as an extra check)
"""
import argparse

import numpy as np
import pandas as pd
from common import (ap, boot_ci, calibrated_fp, evaluate, get_splits, load, make_logreg,
                    make_pre, report, save)
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.pipeline import Pipeline

parser = argparse.ArgumentParser()
parser.add_argument("--cv", choices=["time", "loro"], default="time")
parser.add_argument("--chunks", type=int, default=5)
a = parser.parse_args()


def make_gb():
    return Pipeline([("pre", make_pre(scale=False)),
                     ("clf", HistGradientBoostingClassifier(
                         max_depth=3, learning_rate=0.05, max_iter=200,
                         class_weight="balanced", random_state=0))])


df = load()
splits = get_splits(df, a.cv, a.chunks)
oof_lr, f_lr = evaluate(df, calibrated_fp(lambda: make_logreg("balanced"), "platt"), splits)
oof_gb, f_gb = evaluate(df, calibrated_fp(make_gb, "platt"), splits)
rows = [report("logreg (balanced, Platt)", df, oof_lr, f_lr),
        report("gradient boosting (balanced, Platt)", df, oof_gb, f_gb)]
save(pd.DataFrame(rows), f"week12_summary_{a.cv}.csv")

m = oof_lr.notna() & oof_gb.notna()
y, p_lr, p_gb = df.loc[m, "label"].to_numpy(), oof_lr[m].to_numpy(), oof_gb[m].to_numpy()
diff = ap(y, p_gb) - ap(y, p_lr)
lo, hi = boot_ci(y, p_gb, p2=p_lr)
wins = int((f_gb["pr_auc"] > f_lr["pr_auc"]).sum())
print(f"\nPR-AUC difference (GB - LR), pooled: {diff:+.3f}  95% CI [{lo:+.3f}, {hi:+.3f}]")
print(f"GB wins {wins} of {len(f_lr)} folds")
print(f"Brier: LR {rows[0]['brier']:.3f} vs GB {rows[1]['brier']:.3f}")
if lo <= 0:
    print("CI includes 0: no demonstrated gain from boosting -> logistic regression is sufficient.")
else:
    print("CI excludes 0: boosting is better here; discuss whether the gain justifies the complexity.")