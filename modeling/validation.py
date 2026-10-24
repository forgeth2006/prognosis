"""Week 13: strict temporal validation and final metrics (Person C).

    python modeling/final_validation.py

1. Purge: a training PR is used only if its CI verdict was already known when the test window starts.
2. Re-run the expanding-window folds for baseline / logistic regression v1 / final model.
3. Review-queue table: what a reviewer gets by checking the top 5/10/20% riskiest PRs.
"""
import argparse

import numpy as np
import pandas as pd
from common import (FEATURES, ap, baseline_fp, boot_ci, calibrated_fp, ece, evaluate, load,
                    logreg_fp, make_logreg, save, time_splits)
from sklearn.metrics import brier_score_loss

LABELS = "data/labeled_prs_v2.csv"
OUTCOME = {"ci_status", "ci_completed_at", "n_workflow_runs", "failed_workflows", "flaky_workflows",
           "fail_confidence", "first_commit_sha", "n_commits", "has_human_commits", "state", "merged",
           "closed_at", "merged_at", "exclusion_reason", "label"}


def known_time(df, labels_path):
    """When each PR's CI verdict became known: ci_completed_at, else closed_at, else created_at."""
    lab = pd.read_csv(labels_path, usecols=["repo", "pr_number", "ci_completed_at", "closed_at"])
    lab = lab.rename(columns={"ci_completed_at": "_ci", "closed_at": "_closed"})
    assert not lab.duplicated(["repo", "pr_number"]).any(), "duplicate PR keys in labels file"
    m = df[["repo", "pr_number"]].merge(lab, on=["repo", "pr_number"], how="left")
    assert len(m) == len(df)
    k = pd.to_datetime(m["_ci"], utc=True, errors="coerce").fillna(
        pd.to_datetime(m["_closed"], utc=True, errors="coerce"))
    k.index = df.index
    missing = int(k.isna().sum())
    return k.fillna(df["created_at"]), missing


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", default=LABELS)
    parser.add_argument("--chunks", type=int, default=5)
    a = parser.parse_args()

    df = load()
    assert not (set(FEATURES) & OUTCOME), "an outcome column is in the feature list"
    known, missing = known_time(df, a.labels)
    print(f"rows: {len(df)}, breakages: {int(df['label'].sum())}; "
          f"rows with no CI-known time (fell back to created_at): {missing}")

    splits = []
    for name, tr, te in time_splits(df, a.chunks):
        start = df.loc[te, "created_at"].min()
        kept = tr[(known.loc[tr] < start).to_numpy()]
        assert df.loc[kept, "created_at"].max() < start
        print(f"{name}: test starts {start.date()}, train {len(tr)} -> {len(kept)} rows after purge")
        splits.append((name, kept, te))

    models = [("baseline (major bump)", baseline_fp, False),
              ("logreg v1", logreg_fp(), True),
              ("logreg balanced + Platt (final)",
               calibrated_fp(lambda: make_logreg("balanced"), "platt"), True)]
    rows, oofs = [], {}
    for name, fp, prob in models:
        oof, folds = evaluate(df, fp, splits)
        oofs[name] = oof
        m = oof.notna()
        y, p = df.loc[m, "label"].to_numpy(), oof[m].to_numpy()
        lo, hi = boot_ci(y, p)
        row = dict(model=name, n=len(y), pos=int(y.sum()), floor=y.mean(), pr_auc=ap(y, p),
                   ci_lo=lo, ci_hi=hi, fold_pr_auc=" / ".join(f"{v:.3f}" for v in folds["pr_auc"]))
        if prob:
            pc = np.clip(p, 0, 1)
            row.update(brier=brier_score_loss(y, pc),
                       brier_if_constant=brier_score_loss(y, np.full(len(y), y.mean())),
                       ece=ece(y, pc))
        rows.append(row)
    res = pd.DataFrame(rows)
    print("\n" + res.round(3).to_string(index=False))
    save(res, "week13_final_metrics.csv")

    final = models[-1][0]
    m = oofs[final].notna()
    y, p = df.loc[m, "label"].to_numpy(), oofs[final][m].to_numpy()
    order = np.argsort(-p, kind="stable")
    q = []
    for f in (0.05, 0.10, 0.20):
        k = max(1, int(round(len(y) * f)))
        hit = int(y[order[:k]].sum())
        q.append(dict(review=f"top {f:.0%}", prs=k, breakages_caught=hit,
                      precision=hit / k, recall=hit / y.sum(), lift=(hit / k) / y.mean()))
    q = pd.DataFrame(q)
    print("\nReview queue (final model, pooled test windows):\n" + q.round(3).to_string(index=False))
    save(q, "week13_review_queue.csv")

    flag = (oofs[models[0][0]][m] > 0).to_numpy()
    hit = int(y[flag].sum())
    print(f"\nBaseline rule flags {int(flag.sum())} PRs: caught {hit} breakages, "
          f"precision {hit / max(1, flag.sum()):.3f}, recall {hit / y.sum():.3f}")