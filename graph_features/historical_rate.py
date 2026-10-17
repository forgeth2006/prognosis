"""Point-in-time historical breakage rate per package (PRognosis, Week 7).

For a PR created at time T, the feature uses ONLY bumps whose CI verdict was already known
before T (ci_completed_at < T; closed_at is the fallback when ci_completed_at is missing),
pooled across all repos, in an expanding window. Nothing from T onwards is touched, so there is
no temporal leakage, and the exact same function serves live scoring (feed it the history so far).

Smoothing (Bayesian / Laplace-style shrinkage toward a global rate, so rare packages are not
trusted on 1-2 samples and unseen packages fall back to the global rate):

    p0   = (k_all + PRIOR_STRENGTH * PRIOR_RATE) / (n_all + PRIOR_STRENGTH)       # global rate so far
    rate = (k_pkg + M * p0) / (n_pkg + M)                                          # package rate so far

k/n are breakages / labeled bumps seen so far. Defaults (PRIOR_RATE 0.10, PRIOR_STRENGTH 20, M 10)
are starting values; Person C owns tuning them, the function takes them as arguments.

Output columns added: hist_k, hist_n (package evidence), hist_global_rate, hist_rate.
"""
import pandas as pd

PRIOR_RATE = 0.10      # expected breakage share from the project plan (5-15%)
PRIOR_STRENGTH = 20.0  # pseudo-observations behind the global prior
M = 10.0               # pseudo-observations pulling a package toward the global rate


def known_at(df):
    """Time each label became known: ci_completed_at, else closed_at, else NaT (never counted)."""
    done = pd.to_datetime(df["ci_completed_at"], utc=True, errors="coerce") if "ci_completed_at" in df \
        else pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns, UTC]")
    closed = pd.to_datetime(df["closed_at"], utc=True, errors="coerce") if "closed_at" in df else done
    return done.fillna(closed)


def add_historical_rate(df, m=M, prior_rate=PRIOR_RATE, prior_strength=PRIOR_STRENGTH,
                        key="package_norm"):
    """Return df (labeled rows only) with hist_* columns, computed in creation-time order.

    Required columns: label (0/1), created_at, key, plus ci_completed_at and/or closed_at.
    Row order and index are preserved.
    """
    out = df.copy()
    created = pd.to_datetime(out["created_at"], utc=True)
    known = known_at(out)
    events = sorted((t, i) for i, t in known.items() if pd.notna(t))   # label-known events
    k_all = n_all = 0
    per_pkg = {}  # key -> [k, n]
    ptr = 0
    cols = {"hist_k": {}, "hist_n": {}, "hist_global_rate": {}, "hist_rate": {}}
    for i in created.sort_values(kind="stable").index:
        t = created[i]
        while ptr < len(events) and events[ptr][0] < t:     # strictly earlier only
            _, j = events[ptr]
            y = int(out.at[j, "label"])
            k_all += y
            n_all += 1
            kn = per_pkg.setdefault(out.at[j, key], [0, 0])
            kn[0] += y
            kn[1] += 1
            ptr += 1
        k, n = per_pkg.get(out.at[i, key], (0, 0))
        p0 = (k_all + prior_strength * prior_rate) / (n_all + prior_strength)
        cols["hist_k"][i], cols["hist_n"][i] = k, n
        cols["hist_global_rate"][i] = p0
        cols["hist_rate"][i] = (k + m * p0) / (n + m)
    for c, d in cols.items():
        out[c] = pd.Series(d)
    return out
