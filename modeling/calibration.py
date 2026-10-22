"""Week 11: calibration of the class-weighted logistic regression.
    python modeling/week11_calibration.py
"""
import argparse

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from common import (RESULTS, calibrated_fp, evaluate, get_splits, load, make_logreg, report, save)
from sklearn.calibration import calibration_curve

parser = argparse.ArgumentParser()
parser.add_argument("--chunks", type=int, default=5)
a = parser.parse_args()

df = load()
splits = get_splits(df, "time", a.chunks)
rows, curves = [], {}
for method in ["none", "platt", "isotonic"]:
    oof, folds = evaluate(df, calibrated_fp(lambda: make_logreg("balanced"), method), splits)
    rows.append(report(f"logreg balanced, calibration={method}", df, oof, folds))
    m = oof.notna()
    curves[method] = calibration_curve(df.loc[m, "label"], oof[m].clip(0, 1), n_bins=5, strategy="quantile")
summary = pd.DataFrame(rows)
print("\n" + summary[["model", "pr_auc", "brier", "ece"]].round(3).to_string(index=False))
save(summary, "week11_summary.csv")

RESULTS.mkdir(parents=True, exist_ok=True)
plt.figure(figsize=(5, 5))
plt.plot([0, 1], [0, 1], "k--", label="perfect")
for method, (frac_pos, mean_pred) in curves.items():
    plt.plot(mean_pred, frac_pos, marker="o", label=method)
plt.xlabel("mean predicted probability")
plt.ylabel("observed breakage rate")
plt.title("Calibration curve (pooled out-of-fold)")
plt.legend()
plt.tight_layout()
plt.savefig(RESULTS / "calibration_curve.png", dpi=150)
print("saved modeling/results/calibration_curve.png")