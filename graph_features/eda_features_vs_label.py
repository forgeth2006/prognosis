"""EDA starter: how does each feature relate to breakage?

Reads the frozen feature table and, for every numeric feature, shows the
breakage rate per bin (quantile bins, or the raw values for flags / small
integer columns). Missing values get their own bar, because "not in graph"
and "no changelog" are real signals in this project, not just gaps.

Run from the repo root:
    python graph_features/eda_features_vs_label.py
    python graph_features/eda_features_vs_label.py --table data/feature_table_v2.csv --label <column>

Writes:
    report/figures/eda/eda_summary.csv        one row per (feature, bin)
    report/figures/eda/eda_features_vs_label.png   one panel per feature (pages if many)

Read-only on data/. Safe to rerun.
"""
import argparse
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LABEL_GUESSES = ["label", "broke_ci", "breakage", "is_breaking", "breaks_ci", "y", "target"]
SKIP_NAME = re.compile(r"(^|_)(id|number|index|idx)$|^pr_?number$|^unnamed", re.I)
PER_PAGE = 12


def find_label(df, wanted):
    if wanted:
        if wanted not in df.columns:
            raise SystemExit(f"label column '{wanted}' not in table. Columns: {list(df.columns)}")
        return wanted
    for g in LABEL_GUESSES:
        if g in df.columns:
            return g
    raise SystemExit("Could not guess the label column. Re-run with --label <column>.\n"
                     f"Columns: {list(df.columns)}")


def fmt(x):
    """Short number label: 1850 -> 1.9k, 0.4012 -> 0.4, -0.001 -> 0."""
    if abs(x) < 0.005:
        return "0"
    if abs(x) >= 1e6:
        return f"{x / 1e6:.1f}M"
    if abs(x) >= 1000:
        return f"{x / 1000:.1f}k"
    return f"{x:.3g}"


def bins_for(series, y):
    """Return list of (bin_label, mask) for one feature."""
    out = []
    miss = series.isna()
    present = series[~miss]
    if present.nunique() <= 6:
        for v in sorted(present.unique()):
            out.append((f"{v:g}" if isinstance(v, (int, float, np.number)) else str(v), series == v))
    else:
        try:
            cats = pd.qcut(present, q=5, duplicates="drop")
        except ValueError:
            cats = None
        if cats is None or cats.nunique() < 2:
            return None
        for iv in cats.cat.categories:
            lo, hi = iv.left, iv.right
            out.append((f"{fmt(lo)}–{fmt(hi)}", (series > lo) & (series <= hi) if iv != cats.cat.categories[0]
                        else (series <= hi)))
    if miss.any():
        out.append(("missing", miss))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", default=str(ROOT / "data" / "feature_table_v2.csv"))
    ap.add_argument("--label", default=None)
    ap.add_argument("--out", default=str(ROOT / "report" / "figures" / "eda"))
    a = ap.parse_args()

    df = pd.read_csv(a.table)
    label = find_label(df, a.label)
    y = pd.to_numeric(df[label], errors="coerce")
    keep = y.notna()
    df, y = df[keep].reset_index(drop=True), y[keep].astype(int).reset_index(drop=True)
    base = y.mean()
    print(f"{len(df)} rows, {int(y.sum())} breakages ({base:.1%}), label column = '{label}'")

    feats = [c for c in df.columns
             if c != label and pd.api.types.is_numeric_dtype(df[c]) and not SKIP_NAME.search(c)
             and df[c].nunique(dropna=True) >= 2]
    print(f"{len(feats)} numeric features")

    rows = []
    for c in feats:
        b = bins_for(df[c], y)
        if not b:
            continue
        for name, mask in b:
            n = int(mask.sum())
            if n == 0:
                continue
            rows.append(dict(feature=c, bin=name, n=n, breakages=int(y[mask].sum()),
                             rate=float(y[mask].mean())))
    summ = pd.DataFrame(rows)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    summ.to_csv(out / "eda_summary.csv", index=False)

    names = list(dict.fromkeys(summ["feature"]))
    pages = [names[i:i + PER_PAGE] for i in range(0, len(names), PER_PAGE)]
    for p, chunk in enumerate(pages, 1):
        cols = 3
        rws = int(np.ceil(len(chunk) / cols))
        fig, axes = plt.subplots(rws, cols, figsize=(5 * cols, 2.8 * rws), squeeze=False)
        for ax in axes.ravel():
            ax.axis("off")
        for ax, f in zip(axes.ravel(), chunk):
            ax.axis("on")
            s = summ[summ.feature == f]
            colors = ["#9aa1ab" if b == "missing" else "#3b6fb6" for b in s["bin"]]
            ax.bar(range(len(s)), s["rate"] * 100, color=colors)
            ax.axhline(base * 100, color="#c0392b", ls="--", lw=1)
            ax.set_xticks(range(len(s)))
            ax.set_xticklabels([f"{b}\n(n={n})" for b, n in zip(s["bin"], s["n"])], fontsize=6.5, rotation=0)
            ax.set_title(f, fontsize=9)
            ax.set_ylabel("breakage %", fontsize=7)
            ax.tick_params(axis="y", labelsize=7)
            for s_ in ("top", "right"):
                ax.spines[s_].set_visible(False)
        fig.suptitle(f"Breakage rate by feature (red dashed = overall {base:.1%}; grey = missing)", fontsize=11)
        fig.tight_layout(rect=[0, 0, 1, 0.96])
        name = "eda_features_vs_label.png" if len(pages) == 1 else f"eda_features_vs_label_{p}.png"
        fig.savefig(out / name, dpi=150)
        plt.close(fig)
        print("wrote", out / name)

    # quick text hint: biggest gaps between bins (descriptive only)
    gaps = (summ[summ.n >= 20].groupby("feature")["rate"].agg(lambda s: s.max() - s.min())
            .sort_values(ascending=False).head(5))
    print("\nBiggest spread in breakage rate across bins (bins with n>=20):")
    for f, g in gaps.items():
        print(f"  {f}: {g:.1%}")
    print("\nwrote", out / "eda_summary.csv")


if __name__ == "__main__":
    main()