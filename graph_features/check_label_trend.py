"""Why does the breakage rate fall across time chunks? (PRognosis, Week 9-12 data check)

Person C found 17.5% -> 12.2% -> 8.0% -> 5.7% -> 5.7% across five time-ordered chunks of the frozen
table. This script tests candidate explanations, read-only on data/:

  repo mix        - repos enter the window at different dates (the scrape took the newest PRs per repo),
                    and their breakage rates differ from 0% to 33%
  shared-cause    - repo-weeks where >= half of >= 3 PRs failed together (one broken base branch or tool
  weeks             release), concentrated early in the window
  censoring       - only CLOSED PRs were scraped; failing PRs stay open far longer than passing ones, so the
                    newest chunk is missing its failures. Compared on PRs closed within 2 days.

Each adjustment is a logistic regression with repo effects and chunk effects, averaged over the overall
repo mix. Caveat: shared-cause weeks and time-to-close are defined from the outcome, so these are
diagnostics, not corrected estimates.

    python graph_features/check_label_trend.py
Writes report/figures/eda/label_trend.png and label_trend_summary.csv
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parents[1]
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e3e2de"
BLUE, ORANGE, GREY = "#2a78d6", "#eb6834", "#a9a8a2"


def load(table, labeled, chunks=5):
    f = pd.read_csv(table)
    l = pd.read_csv(labeled)
    l = l[l["label"].notna()][["repo", "pr_number", "closed_at", "merged"]]
    d = f.merge(l, on=["repo", "pr_number"], how="left")
    assert len(d) == len(f), "join with labeled table changed the row count"
    for c in ("created_at", "closed_at"):
        d[c] = pd.to_datetime(d[c], utc=True)
    d = d.sort_values("created_at").reset_index(drop=True)
    d["chunk"] = pd.cut(np.arange(len(d)), chunks, labels=False)       # same equal-count chunks as modeling
    d["days_open"] = (d["closed_at"] - d["created_at"]).dt.total_seconds() / 86400
    d["week"] = d["created_at"].dt.strftime("%G-W%V")
    w = d.groupby(["repo", "week"])["label"].agg(k="sum", n="count").reset_index()
    bad = w[(w["n"] >= 3) & (w["k"] / w["n"] >= 0.5)][["repo", "week"]].assign(shared=1)
    d = d.merge(bad, on=["repo", "week"], how="left")
    d["shared"] = d["shared"].fillna(0).astype(int)
    return d


def repo_adjusted(sub, chunks=5, weights=None):
    """Predicted breakage rate per chunk from label ~ repo + chunk, averaged over the repo mix."""
    weights = sub if weights is None else weights
    chunk_cols = [f"c_{c}" for c in range(1, chunks)]
    def design(repos, chunk):
        X = pd.get_dummies(repos).reindex(columns=repo_cols, fill_value=0).astype(float)
        for c in range(1, chunks):
            X[f"c_{c}"] = float(chunk == c) if np.isscalar(chunk) else (chunk == c).astype(float)
        return X
    repo_cols = sorted(sub["repo"].unique())
    X = design(sub["repo"], sub["chunk"].to_numpy())
    m = LogisticRegression(C=1.0, max_iter=3000).fit(X, sub["label"])
    mix = weights[weights["repo"].isin(repo_cols)]["repo"]
    return {c: float(m.predict_proba(design(mix, c))[:, 1].mean()) for c in range(chunks)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--table", default=str(ROOT / "data" / "feature_table_v2.csv"))
    ap.add_argument("--labeled", default=str(ROOT / "data" / "labeled_prs_v2.csv"))
    ap.add_argument("--out", default=str(ROOT / "report" / "figures" / "eda"))
    a = ap.parse_args()
    d = load(a.table, a.labeled)
    K = int(d["label"].sum())
    series = {
        "observed": d.groupby("chunk")["label"].mean().to_dict(),
        "repo-adjusted": repo_adjusted(d),
        "repo-adjusted, shared-cause weeks removed": repo_adjusted(d[d["shared"] == 0], weights=d),
        "repo-adjusted, closed within 2 days": repo_adjusted(d[d["days_open"] <= 2], weights=d),
        "both": repo_adjusted(d[(d["days_open"] <= 2) & (d["shared"] == 0)], weights=d),
    }
    summ = pd.DataFrame(series).round(4)
    summ.index.name = "chunk"
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    summ.to_csv(out / "label_trend_summary.csv")
    print((summ * 100).round(1).to_string())

    open7 = d[d["days_open"] > 7]
    print(f"\nbreakages still open after 7+ days before closing: {int((open7['label'] == 1).sum())} of {K} "
          f"({(open7['label'] == 1).sum() / K:.0%}); clean PRs: {int((open7['label'] == 0).sum())} of "
          f"{int((d['label'] == 0).sum())} ({(open7['label'] == 0).sum() / (d['label'] == 0).sum():.0%})")
    print("merged share  breaking vs clean:", d.groupby("label")["merged"].mean().round(3).to_dict())
    print("median days open  breaking vs clean:", d.groupby("label")["days_open"].median().round(2).to_dict())
    print("breakages in shared-cause weeks by chunk:", d[d["shared"] == 1].groupby("chunk")["label"].sum().to_dict())

    fig, ax = plt.subplots(figsize=(8.5, 4.8), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.yaxis.grid(True, color=GRID, lw=0.6)
    ax.tick_params(colors=INK2, labelsize=8, length=0)
    styles = {"observed": (INK, 2.2), "repo-adjusted": (BLUE, 1.6),
              "repo-adjusted, shared-cause weeks removed": (ORANGE, 1.6),
              "repo-adjusted, closed within 2 days": (GREY, 1.6), "both": (GREY, 1.0)}
    for name, (col, lw) in styles.items():
        ys = [series[name][c] * 100 for c in range(5)]
        ax.plot(range(5), ys, color=col, lw=lw, marker="o", ms=4, ls="-" if name != "both" else "--")
        ax.text(4.08, ys[-1], name, fontsize=7.5, color=INK2, va="center")
    ax.set_xticks(range(5))
    ax.set_xticklabels(["chunk 1\n(oldest)", "2", "3", "4", "chunk 5\n(newest)"], fontsize=8)
    ax.set_ylabel("breakage rate, %", fontsize=8, color=INK2)
    ax.set_xlim(-0.2, 6.6)
    ax.set_ylim(0, 20)
    ax.set_title("How much of the falling breakage rate survives adjustment?", fontsize=11, color=INK, loc="left",
                 fontweight="bold")
    fig.tight_layout()
    fig.savefig(out / "label_trend.png", dpi=150, facecolor=SURFACE)
    print("wrote", out / "label_trend.png")


if __name__ == "__main__":
    main()
