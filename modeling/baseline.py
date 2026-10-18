"""Baseline: predict 'breaks' when the bump is a major version change.

Run from the repo root:
    python modeling/baseline.py
"""
import argparse

import pandas as pd
from sklearn.metrics import (average_precision_score, confusion_matrix,
                             precision_score, recall_score)
from temporal_split import temporal_split


def evaluate(name, d):
    y = d["label"].astype(int)
    pred = (d["major_delta"].fillna(0) > 0).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    print(f"{name}: n={len(d)}, positives={y.sum()} ({y.mean():.1%})")
    print(f"  precision={precision_score(y, pred, zero_division=0):.3f}  "
          f"recall={recall_score(y, pred, zero_division=0):.3f}  "
          f"PR-AUC={average_precision_score(y, pred):.3f}  "
          f"(floor = prevalence {y.mean():.3f})")
    print(f"  confusion: TN={tn} FP={fp} FN={fn} TP={tp}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", default="data/feature_table_v1.csv")
    ap.add_argument("--train-frac", type=float, default=0.8)
    a = ap.parse_args()

    df = pd.read_csv(a.table, parse_dates=["created_at"])
    df = df[df["label"].notna()]
    train, test, cutoff = temporal_split(df, a.train_frac)
    print(f"cutoff: {cutoff.date()}")
    evaluate("train", train)
    evaluate("test", test)