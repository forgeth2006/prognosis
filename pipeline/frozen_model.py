"""Frozen scoring model: balanced logistic regression + Platt calibration + risk bands (Person C)."""
import numpy as np


class FrozenModel:
    BANDS = ("review first", "look closer", "routine")

    def __init__(self, base, platt, features, ref_scores, version, meta):
        self.base, self.platt, self.features = base, platt, list(features)
        self.ref_scores = np.sort(np.asarray(ref_scores, dtype=float))
        self.cut_high = float(np.quantile(self.ref_scores, 0.95))       # top 5% of reference scores
        self.cut_elevated = float(np.quantile(self.ref_scores, 0.80))   # next 15%
        self.version, self.meta = version, meta

    def score(self, X):
        """Calibrated score in [0, 1]. Use it to RANK PRs, not as a precise probability."""
        s = self.base.decision_function(X[self.features])
        return self.platt.predict_proba(s.reshape(-1, 1))[:, 1]

    def percentile(self, scores):
        """Share of reference PRs with a lower score (0.93 = riskier than 93% of them)."""
        return np.searchsorted(self.ref_scores, np.asarray(scores), side="right") / len(self.ref_scores)

    def band(self, score):
        if score >= self.cut_high:
            return self.BANDS[0]
        return self.BANDS[1] if score >= self.cut_elevated else self.BANDS[2]

    def reasons(self, X, k=3):
        """Top-k features pushing each PR's score up or down (coefficient x standardized value)."""
        pre = self.base.named_steps["pre"]
        Z = pre.transform(X[self.features])
        Z = Z.toarray() if hasattr(Z, "toarray") else np.asarray(Z)
        names = pre.get_feature_names_out()
        contrib = Z * self.base.named_steps["clf"].coef_[0]
        out = []
        for row in contrib:
            idx = np.argsort(-np.abs(row))[:k]
            out.append("; ".join(f"{names[i].split('__', 1)[-1]} ({row[i]:+.2f})" for i in idx))
        return out