"""Fit and freeze the final model on the frozen dataset (Person C).

    python pipeline/train_final.py

Same recipe as the Week 13 final model: balanced logistic regression fit on the older 75% of the
data, Platt calibration on the newest 25%. The risk-band cut points come from the scores of that
newest 25%, which the base model did not train on.
"""
import datetime as dt
import json
import sys
from pathlib import Path

import joblib
import sklearn
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modeling"))
sys.path.insert(0, str(ROOT / "pipeline"))
from common import FEATURES, load, make_logreg  # noqa: E402
from frozen_model import FrozenModel  # noqa: E402

VERSION = "v1"
OUT = ROOT / "pipeline" / "models"

df = load(str(ROOT / "data" / "feature_table_v2.csv"))   # sorted by created_at
cut = int(len(df) * 0.75)
fit, cal = df.iloc[:cut], df.iloc[cut:]
base = make_logreg("balanced").fit(fit[FEATURES], fit["label"])
s_cal = base.decision_function(cal[FEATURES])
platt = LogisticRegression(C=1e6).fit(s_cal.reshape(-1, 1), cal["label"])
ref = platt.predict_proba(s_cal.reshape(-1, 1))[:, 1]

meta = {"version": VERSION, "trained_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": "data/feature_table_v2.csv", "n_rows": len(df), "n_breakages": int(df["label"].sum()),
        "fit_rows": len(fit), "calibration_rows": len(cal),
        "newest_pr_in_training": str(df["created_at"].max()), "sklearn": sklearn.__version__}
model = FrozenModel(base, platt, FEATURES, ref, VERSION, meta)
meta.update(cut_review_first=model.cut_high, cut_look_closer=model.cut_elevated)

OUT.mkdir(parents=True, exist_ok=True)
joblib.dump(model, OUT / f"model_{VERSION}.joblib")
(OUT / f"model_{VERSION}.json").write_text(json.dumps(meta, indent=2))

names = base.named_steps["pre"].get_feature_names_out()
coef = dict(zip(names, base.named_steps["clf"].coef_[0]))
print(f"trained on {len(fit)} rows, calibrated on {len(cal)}; {meta['n_breakages']} breakages in total")
print(f"band cut points: review first >= {model.cut_high:.3f}, look closer >= {model.cut_elevated:.3f}")
print("coefficient of changelog_scraped (expected 0, it was constant in training):",
      round(coef.get("num__changelog_scraped", float("nan")), 4))
print(f"saved {OUT / f'model_{VERSION}.joblib'}")