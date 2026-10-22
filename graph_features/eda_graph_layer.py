"""Graph-layer EDA (PRognosis, Week 9): extra charts that go beyond eda_features_vs_label.py.

Esther's starter script bins every numeric feature on its own. This script adds what that cannot show:
  1. meaningful bins for blast radius / depth, with the "not imported" and "test-only" cases split out,
     every bar with a 95% Wilson interval and k/n printed on it (breakages / PRs)
  2. the categorical features the starter skips (bump type, changelog keyword flag)
  3. confounding checks: repo, package and week effects (a few dev tools and a few bad weeks carry
     a large share of the breakages, so a pooled bar can mislead)
  4. a forest plot of crude vs repo-stratified odds ratios with package-cluster bootstrap intervals

Read-only on data/. Run from the repo root:
    python graph_features/eda_graph_layer.py
Writes report/figures/eda/graph_layer_{1,2,3}_*.png, eda_graph_layer_summary.csv, eda_graph_layer_effects.csv
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e3e2de"
BLUE, ORANGE, GREY = "#2a78d6", "#eb6834", "#a9a8a2"
SEED = 7


# ------------------------------------------------------------------ stats
def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def mh_odds_ratio(df, exposed, strata):
    """Mantel-Haenszel common odds ratio of label ~ exposed across strata (strata without both
    exposure levels or without outcome variation contribute nothing)."""
    num = den = 0.0
    for _, g in df.groupby(strata):
        e, y = g[exposed].astype(bool), g["label"].astype(bool)
        a, b, c, d = (e & y).sum(), (e & ~y).sum(), (~e & y).sum(), (~e & ~y).sum()
        n = a + b + c + d
        if n:
            num += a * d / n
            den += b * c / n
    return num / den if den else np.nan


def crude_or(df, exposed):
    e, y = df[exposed].astype(bool), df["label"].astype(bool)
    a, b, c, d = [(x + 0.5) for x in ((e & y).sum(), (e & ~y).sum(), (~e & y).sum(), (~e & ~y).sum())]
    return a * d / (b * c)


def cluster_bootstrap(df, fn, cluster="package_norm", reps=1000, seed=SEED):
    """Percentile 95% interval of fn(resampled df), resampling whole packages (PRs of the same
    package are not independent: one tool breaking hits many PRs)."""
    rng = np.random.default_rng(seed)
    groups = {k: g for k, g in df.groupby(cluster)}
    keys = list(groups)
    out = []
    for _ in range(reps):
        pick = rng.choice(len(keys), size=len(keys), replace=True)
        v = fn(pd.concat([groups[keys[i]] for i in pick], ignore_index=True))
        if np.isfinite(v):
            out.append(v)
    return (np.percentile(out, 2.5), np.percentile(out, 97.5)) if len(out) > reps * 0.5 else (np.nan, np.nan)


# ------------------------------------------------------------------ drawing
def style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=8, length=0)
    ax.yaxis.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)


def rate_panel(ax, groups, base, title, note=None):
    """groups: list of (label, k, n, color). Bars with Wilson whiskers and k/n labels."""
    style(ax)
    for i, (lab, k, n, col) in enumerate(groups):
        r = k / n if n else 0
        lo, hi = wilson(k, n)
        ax.bar(i, r * 100, width=0.55, color=col, zorder=2)
        ax.plot([i, i], [lo * 100, hi * 100], color=INK, lw=1.1, zorder=3)
        ax.text(i, hi * 100 + 0.8, f"{k}/{n}", ha="center", va="bottom", fontsize=7.5, color=INK2,
                bbox=dict(facecolor=SURFACE, edgecolor="none", pad=1.0), zorder=4)
    ax.axhline(base * 100, color=INK2, ls=(0, (4, 3)), lw=1, zorder=1)
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels([g[0] for g in groups], fontsize=8)
    ax.set_ylabel("breakage rate, %", fontsize=8, color=INK2)
    ax.set_title(title, fontsize=10, color=INK, loc="left", fontweight="bold")
    ax.set_ylim(0, max(34, ax.get_ylim()[1]))
    if note:
        ax.text(0.99, 0.97, note, transform=ax.transAxes, ha="right", va="top", fontsize=7, color=INK2)


def rows_of(name, groups):
    return [dict(chart=name, group=g[0], breakages=g[1], n=g[2], rate=g[1] / g[2] if g[2] else np.nan,
                 ci_low=wilson(g[1], g[2])[0], ci_high=wilson(g[1], g[2])[1]) for g in groups]


def split(df, mask_defs, color=BLUE):
    out = []
    for lab, m in mask_defs:
        s = df[m]
        out.append((lab, int(s["label"].sum()), len(s), color if not lab.startswith("*") else GREY))
    return [(l.lstrip("*"), k, n, c) for l, k, n, c in out]


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--table", default=str(ROOT / "data" / "feature_table_v2.csv"))
    ap.add_argument("--out", default=str(ROOT / "report" / "figures" / "eda"))
    ap.add_argument("--reps", type=int, default=1000)
    a = ap.parse_args()
    df = pd.read_csv(a.table)
    df = df[df["label"].notna()].copy()
    df["label"] = df["label"].astype(int)
    df["created"] = pd.to_datetime(df["created_at"], utc=True)
    base, N, K = df["label"].mean(), len(df), int(df["label"].sum())
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    summary = []
    print(f"{N} rows, {K} breakages ({base:.1%})")

    imported = df["not_in_graph"] == 0
    test_only = (df["not_in_graph"] == 0) & (df["depth_missing"] == 1)
    has_depth = df["depth_missing"] == 0

    # ---------------- figure 1: graph features with sensible bins + categorical controls
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.6), facecolor=SURFACE)
    b = df["blast_direct"]
    g_blast = split(df, [("*0\n(not imported)", b == 0), ("1 file", b == 1), ("2-3", (b >= 2) & (b <= 3)),
                         ("4-9", (b >= 4) & (b <= 9)), ("10+", b >= 10)])
    rate_panel(axes[0, 0], g_blast, base, "Blast radius: files importing the package",
               "whiskers: 95% interval; dashed: overall")
    d = df["depth_min"]
    g_depth = split(df, [("*not imported", ~imported), ("*test-only", test_only), ("depth 0", d == 0),
                         ("depth 1", d == 1), ("depth 2+", d >= 2)])
    rate_panel(axes[0, 1], g_depth, base, "Depth: hops from an entry point (grey = no depth exists)")
    g_bump = split(df, [("patch", df.bump_type == "patch"), ("minor", df.bump_type == "minor"),
                        ("major", df.bump_type == "major"), ("other", df.bump_type == "other")])
    rate_panel(axes[1, 0], g_bump, base, "Control: bump type")
    kw = df["has_breaking_keyword"].astype(str)
    g_kw = split(df, [("changelog:\nno keyword", kw == "False"), ("changelog:\nbreaking keyword", kw == "True"),
                      ("*no changelog\nfound", ~kw.isin(["True", "False"]))])
    rate_panel(axes[1, 1], g_kw, base, "Control: changelog breaking-keyword flag")
    fig.suptitle(f"Breakage rate by graph feature (n = {N}, {K} breakages, {base:.1%} overall)",
                 fontsize=12, color=INK, x=0.01, ha="left", fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(out / "graph_layer_1_features.png", dpi=150, facecolor=SURFACE)
    plt.close(fig)
    for name, g in [("blast_direct", g_blast), ("depth", g_depth), ("bump_type", g_bump), ("changelog_keyword", g_kw)]:
        summary += rows_of(name, g)

    # ---------------- figure 2: confounding
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.4), facecolor=SURFACE, gridspec_kw={"width_ratios": [1.1, 1, 1]})
    # (a) imported vs not imported, within each repo
    ax = axes[0]
    style(ax)
    ax.yaxis.grid(False)
    ax.xaxis.grid(True, color=GRID, lw=0.6)
    rep = []
    for repo, g in df.groupby("repo"):
        gi, gn = g[g.not_in_graph == 0], g[g.not_in_graph == 1]
        if len(gi) >= 10 and len(gn) >= 10:
            rep.append((repo, gi.label.mean(), len(gi), int(gi.label.sum()), gn.label.mean(), len(gn), int(gn.label.sum())))
    rep.sort(key=lambda r: r[4] - r[1])
    for i, (repo, ri, ni, ki, rn, nn, kn) in enumerate(rep):
        ax.plot([ri * 100, rn * 100], [i, i], color=GRID, lw=2, zorder=1)
        ax.scatter(ri * 100, i, s=46, color=BLUE, zorder=3, edgecolor=SURFACE, linewidth=1.5)
        ax.scatter(rn * 100, i, s=46, color=ORANGE, zorder=3, edgecolor=SURFACE, linewidth=1.5)
        summary.append(dict(chart="within_repo_imported", group=f"{repo}|imported", breakages=ki, n=ni, rate=ri,
                            ci_low=wilson(ki, ni)[0], ci_high=wilson(ki, ni)[1]))
        summary.append(dict(chart="within_repo_imported", group=f"{repo}|not_imported", breakages=kn, n=nn, rate=rn,
                            ci_low=wilson(kn, nn)[0], ci_high=wilson(kn, nn)[1]))
    ax.set_yticks(range(len(rep)))
    ax.set_yticklabels([f"{r[0].split('/')[1]}  ({r[3]}/{r[2]} vs {r[6]}/{r[5]})" for r in rep], fontsize=7.5)
    ax.set_xlabel("breakage rate, %", fontsize=8, color=INK2)
    ax.set_title("Imported vs not imported, within each repo", fontsize=10, color=INK, loc="left", fontweight="bold")
    ax.scatter([], [], color=BLUE, s=30, label="imported by repo code")
    ax.scatter([], [], color=ORANGE, s=30, label="not imported (tool / transitive)")
    ax.legend(fontsize=7.5, frameon=False, loc="lower right", labelcolor=INK2)
    # (b) top packages by breakages
    ax = axes[1]
    style(ax)
    ax.yaxis.grid(False)
    ax.xaxis.grid(True, color=GRID, lw=0.6)
    pk = df.groupby("package_norm").agg(k=("label", "sum"), n=("label", "size"), nig=("not_in_graph", "mean"))
    top = pk.sort_values(["k", "n"], ascending=False).head(12).iloc[::-1]
    ax.barh(range(len(top)), top.k, height=0.55, color=[GREY if v >= 0.5 else BLUE for v in top.nig], zorder=2)
    for i, (name, r) in enumerate(top.iterrows()):
        ax.text(r.k + 0.2, i, f"{int(r.k)}/{int(r.n)} PRs", va="center", fontsize=7.5, color=INK2)
    ax.set_yticks(range(len(top)))
    ax.set_yticklabels(top.index, fontsize=8)
    ax.set_xlabel("breakages", fontsize=8, color=INK2)
    share5 = pk.k.sort_values(ascending=False).head(5).sum() / K
    ax.set_title(f"Top packages carry the breakages (top 5 = {share5:.0%})", fontsize=10, color=INK, loc="left",
                 fontweight="bold")
    ax.text(0.99, 0.03, "grey: mostly not imported by repo code", transform=ax.transAxes, ha="right", fontsize=7, color=INK2)
    summary += [dict(chart="top_packages", group=n, breakages=int(r.k), n=int(r.n), rate=r.k / r.n,
                     ci_low=wilson(int(r.k), int(r.n))[0], ci_high=wilson(int(r.k), int(r.n))[1])
                for n, r in pk.sort_values(["k", "n"], ascending=False).head(12).iterrows()]
    # (c) shared-cause weeks
    ax = axes[2]
    style(ax)
    ax.yaxis.grid(False)
    ax.xaxis.grid(True, color=GRID, lw=0.6)
    df["week"] = df["created"].dt.strftime("%G-W%V")
    w = df.groupby(["repo", "week"]).label.agg(k="sum", n="count").reset_index()
    bad = w[(w["n"] >= 3) & (w["k"] / w["n"] >= 0.5)].sort_values("k").tail(10)
    inside = int(w.merge(bad[["repo", "week"]], on=["repo", "week"])["k"].sum())
    ax.barh(range(len(bad)), bad["n"], height=0.55, color=GRID, zorder=2)
    ax.barh(range(len(bad)), bad["k"], height=0.55, color=BLUE, zorder=3)
    ax.set_yticks(range(len(bad)))
    ax.set_yticklabels([f"{r.repo.split('/')[1]} {r.week}" for r in bad.itertuples()], fontsize=7.5)
    ax.set_xlabel("PRs that week (grey) and breakages (blue)", fontsize=8, color=INK2)
    ax.set_title(f"Weeks when most PRs failed together:\n{inside} of {K} breakages fall in these", fontsize=10, color=INK, loc="left",
                 fontweight="bold")
    summary += [dict(chart="shared_cause_weeks", group=f"{r.repo} {r.week}", breakages=int(r.k), n=int(r.n),
                     rate=r.k / r.n, ci_low=np.nan, ci_high=np.nan) for r in bad.itertuples()]
    fig.suptitle("What can distort the graph-feature bars", fontsize=12, color=INK, x=0.01, ha="left", fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(out / "graph_layer_2_confounding.png", dpi=150, facecolor=SURFACE)
    plt.close(fig)

    # ---------------- figure 3: crude vs repo-stratified odds ratios
    d3 = df.copy()
    d3["imported"] = (d3.not_in_graph == 0).astype(int)
    d3["blast_ge2"] = (d3.blast_direct >= 2).astype(int)
    d3["used_in_src"] = (d3.blast_direct_src >= 1).astype(int)
    d3["repo_bump"] = d3["repo"] + "|" + d3["bump_type"]
    specs = [("imported by repo code (vs not imported)", "imported", d3),
             ("blast radius 2+ files (vs 0-1)", "blast_ge2", d3),
             ("used in library code (vs tests/none)", "used_in_src", d3),
             ("depth 0 (vs depth 1+), rows with a depth", "depth0", d3[d3.depth_missing == 0].assign(
                 depth0=lambda x: (x.depth_min == 0).astype(int)))]
    effects = []
    for label, col, dd in specs:
        crude = crude_or(dd, col)
        for name, strata in (("repo-stratified", "repo"), ("repo x bump-type stratified", "repo_bump")):
            est = mh_odds_ratio(dd, col, strata)
            lo, hi = cluster_bootstrap(dd, lambda x, c=col, s=strata: mh_odds_ratio(x, c, s), reps=a.reps)
            effects.append(dict(exposure=label, adjustment=name, odds_ratio=est, ci_low=lo, ci_high=hi,
                                crude_or=crude, n=len(dd), breakages=int(dd.label.sum())))
        print(f"{label}: crude OR {crude:.2f}")
    eff = pd.DataFrame(effects)
    eff.to_csv(out / "eda_graph_layer_effects.csv", index=False)
    fig, ax = plt.subplots(figsize=(10.5, 5.2), facecolor=SURFACE)
    style(ax)
    ax.yaxis.grid(False)
    ax.xaxis.grid(True, color=GRID, lw=0.6)
    y, ticks = 0, []
    for label, g in eff.groupby("exposure", sort=False):
        ax.scatter(g.crude_or.iloc[0], y, marker="s", s=38, color=GREY, zorder=3)
        y += 1
        for _, r in g.iterrows():
            col = BLUE if r.adjustment == "repo-stratified" else ORANGE
            ax.plot([r.ci_low, r.ci_high], [y, y], color=col, lw=1.6, zorder=2)
            ax.scatter(r.odds_ratio, y, s=42, color=col, zorder=3, edgecolor=SURFACE, linewidth=1.5)
            ax.text(max(r.ci_high, r.odds_ratio) * 1.12 if np.isfinite(r.ci_high) else r.odds_ratio * 1.12, y,
                    f"{r.odds_ratio:.2f}", va="center", fontsize=7.5, color=INK2)
            y += 1
        ticks.append((y - 2, label))
        y += 1
    ax.axvline(1, color=INK2, lw=1)
    ax.set_xscale("log")
    ax.set_xticks([0.25, 0.5, 1, 2, 4])
    ax.set_xticklabels(["0.25", "0.5", "1", "2", "4"])
    ax.set_yticks([t[0] for t in ticks])
    ax.set_yticklabels([t[1] for t in ticks], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("odds ratio for breakage (log scale; 1 = no association)", fontsize=8, color=INK2)
    ax.scatter([], [], marker="s", color=GREY, s=30, label="crude")
    ax.plot([], [], color=BLUE, lw=1.6, label="repo-stratified (95% interval, resampling packages)")
    ax.plot([], [], color=ORANGE, lw=1.6, label="repo x bump-type stratified")
    ax.legend(fontsize=7.5, frameon=False, loc="upper center", bbox_to_anchor=(0.45, -0.12), ncol=3, labelcolor=INK2)
    ax.set_xlim(0.04, 9)
    ax.set_title("Do graph features still matter once repo and bump type are held fixed?", fontsize=11, color=INK,
                 loc="left", fontweight="bold")
    fig.tight_layout()
    fig.savefig(out / "graph_layer_3_adjusted_odds.png", dpi=150, facecolor=SURFACE)
    plt.close(fig)

    pd.DataFrame(summary).to_csv(out / "eda_graph_layer_summary.csv", index=False)
    print("\n" + eff.round(2).to_string(index=False))
    print(f"\nshared-cause weeks: {inside} of {K} breakages sit in {len(bad)} repo-weeks with >=3 PRs and >=50% failing")
    print(f"top-5 packages hold {share5:.0%} of breakages; fail_confidence confirmed: "
          f"{int((df.fail_confidence == 'confirmed').sum())} of {K}")
    print("wrote figures and CSVs to", out)


if __name__ == "__main__":
    main()
