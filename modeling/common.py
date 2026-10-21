"""Shared helpers for weeks 9-12 (Person C). Imported by the week scripts."""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

TABLE = "data/feature_table_v2.csv"
RESULTS = Path("modeling/results")

CAT = ["bump_type"]
COUNTS = ["blast_direct", "blast_direct_src", "blast_direct_tests", "blast_transitive",
          "hist_n", "hist_k", "changelog_chars", "changelog_lines"]   # skewed -> log1p
OTHER = ["major_delta", "minor_delta", "patch_delta", "is_prerelease", "is_zero_major",
         "is_range_update", "depth_min", "depth_mean", "not_in_graph", "depth_missing",
         "snapshot_missing", "hist_rate", "hist_global_rate", "changelog_scraped",
         "changelog_found", "has_breaking_keyword"]
NUM = OTHER + COUNTS
FEATURES = CAT + NUM   # same list as the feature table's "features" group; no outcome columns


def _num(s):
    m = {True: 1, False: 0, "True": 1, "False": 0}
    return pd.to_numeric(s.map(lambda v: m.get(v, v)), errors="coerce")


def load(path=TABLE):
    df = pd.read_csv(path)
    df = df[df["label"].notna()].copy()
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    for c in NUM:
        df[c] = _num(df[c])
    for c in COUNTS:
        df[c] = np.log1p(df[c].clip(lower=0))
    df["label"] = df["label"].astype(int)
    return df.sort_values("created_at").reset_index(drop=True)


def make_pre(scale=True):
    steps = [SimpleImputer(strategy="constant", fill_value=0)]   # NaN depth -> 0; depth_missing flag keeps the info
    if scale:
        steps.append(StandardScaler())
    return ColumnTransformer([("num", make_pipeline(*steps), NUM),
                              ("cat", OneHotEncoder(handle_unknown="ignore"), CAT)])


def make_logreg(class_weight=None, C=1.0):
    return Pipeline([("pre", make_pre()),
                     ("clf", LogisticRegression(max_iter=2000, C=C, class_weight=class_weight))])


# ---------- splits ----------
def time_splits(df, n_chunks=5):
    """Expanding window: train on everything before chunk k, test on chunk k (k = 1..n_chunks-1)."""
    d = df["created_at"]
    b = np.linspace(0, len(df), n_chunks + 1).astype(int)
    edges = [d.iloc[min(i, len(df) - 1)] for i in b]
    for k in range(1, n_chunks):
        lo, hi = edges[k], edges[k + 1]
        last = k == n_chunks - 1
        tr = df.index[d < lo]
        te = df.index[(d >= lo) & ((d <= hi) if last else (d < hi))]
        yield f"fold{k}", tr, te


def loro_splits(df):
    """Leave one repo out (ignores time): does the model work on an unseen repo?"""
    for r in sorted(df["repo"].unique()):
        te = df.index[df["repo"] == r]
        if df.loc[te, "label"].sum() > 0:
            yield r, df.index[df["repo"] != r], te


def get_splits(df, cv, chunks):
    return list(time_splits(df, chunks) if cv == "time" else loro_splits(df))


# ---------- metrics ----------
def ap(y, p):
    return average_precision_score(y, p) if np.sum(y) > 0 else np.nan


def top_k(y, p, frac=0.10):
    """Review-workload view: flag the top 10% riskiest PRs; how many real breakages are in it?"""
    y, p = np.asarray(y), np.asarray(p)
    k = max(1, int(round(len(y) * frac)))
    hit = y[np.argsort(-p, kind="stable")[:k]].sum()
    return hit / k, hit / max(1, y.sum())


def ece(y, p, bins=5):
    r = pd.Series(p).rank(method="first")
    q = pd.qcut(r, min(bins, len(p)), labels=False)
    g = pd.DataFrame({"y": np.asarray(y), "p": np.asarray(p), "q": q}).groupby("q")
    return float((g.size() / len(y) * (g["y"].mean() - g["p"].mean()).abs()).sum())


def boot_ci(y, p, p2=None, n=1000, seed=0):
    """95% CI of PR-AUC (or of the PR-AUC difference p - p2) by resampling rows."""
    rng = np.random.default_rng(seed)
    y, p = np.asarray(y), np.asarray(p)
    p2 = None if p2 is None else np.asarray(p2)
    out = []
    for _ in range(n):
        s = rng.integers(0, len(y), len(y))
        if y[s].sum() == 0:
            continue
        out.append(ap(y[s], p[s]) - (0 if p2 is None else ap(y[s], p2[s])))
    return np.percentile(out, [2.5, 97.5])


def evaluate(df, fit_predict, splits):
    """fit_predict(train_df, test_df) -> scores. Returns out-of-fold scores + per-fold table."""
    oof = pd.Series(np.nan, index=df.index)
    rows = []
    for name, tr, te in splits:
        p = np.asarray(fit_predict(df.loc[tr], df.loc[te]), dtype=float)
        oof.loc[te] = p
        y = df.loc[te, "label"].to_numpy()
        pk, rk = top_k(y, p)
        rows.append(dict(split=name, n=len(te), pos=int(y.sum()), prevalence=y.mean(),
                         pr_auc=ap(y, p), brier=brier_score_loss(y, np.clip(p, 0, 1)),
                         prec_top10=pk, rec_top10=rk))
    return oof, pd.DataFrame(rows)


def report(name, df, oof, folds):
    m = oof.notna()
    y, p = df.loc[m, "label"].to_numpy(), oof[m].to_numpy()
    lo, hi = boot_ci(y, p)
    pk, rk = top_k(y, p)
    print(f"\n== {name} ==")
    print(folds.round(3).to_string(index=False))
    print(f"pooled: n={len(y)} pos={y.sum()} floor={y.mean():.3f} PR-AUC={ap(y, p):.3f} "
          f"(95% CI {lo:.3f}-{hi:.3f}) | mean fold PR-AUC={folds.pr_auc.mean():.3f} "
          f"+/- {folds.pr_auc.std():.3f} | top-10%: precision={pk:.3f} recall={rk:.3f}")
    return dict(model=name, n=len(y), pos=int(y.sum()), floor=y.mean(), pr_auc=ap(y, p),
                ci_lo=lo, ci_hi=hi, prec_top10=pk, rec_top10=rk,
                brier=brier_score_loss(y, np.clip(p, 0, 1)), ece=ece(y, np.clip(p, 0, 1)))


def save(df, name):
    RESULTS.mkdir(parents=True, exist_ok=True)
    df.to_csv(RESULTS / name, index=False)


# ---------- model runners ----------
def baseline_fp(tr, te):
    return (te["major_delta"].fillna(0) > 0).astype(float)


def logreg_fp(class_weight=None, C=1.0):
    def fp(tr, te):
        m = make_logreg(class_weight, C).fit(tr[FEATURES], tr["label"])
        return m.predict_proba(te[FEATURES])[:, 1]
    return fp


def calibrated_fp(make_model, method):
    """Fit on the older 75% of the training window, calibrate on the newest 25%
    (time-ordered, so calibration never sees the future). method: none | platt | isotonic."""
    def fp(tr, te):
        tr = tr.sort_values("created_at")
        cut = int(len(tr) * 0.75)
        fit, cal = tr.iloc[:cut], tr.iloc[cut:]
        m = make_model().fit(fit[FEATURES], fit["label"])
        s_cal, s_te = m.decision_function(cal[FEATURES]), m.decision_function(te[FEATURES])
        raw = 1 / (1 + np.exp(-s_te))
        if method == "none" or cal["label"].nunique() < 2:
            return raw
        if method == "platt":
            c = LogisticRegression(C=1e6).fit(s_cal.reshape(-1, 1), cal["label"])
            return c.predict_proba(s_te.reshape(-1, 1))[:, 1]
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(s_cal, cal["label"])
        return iso.predict(s_te)
    return fp