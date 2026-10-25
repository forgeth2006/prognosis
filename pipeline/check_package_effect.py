"""Is the model leaning on one package's history? (Person C)

    python pipeline/check_package_effect.py --package sphinx [--db path\\to\\live.db]

1. top-scored live PRs and the features driving them (needs --db)
2. the package's history in the frozen training data: rows, breakages, repos, distinct bumps, dates, failed workflows
3. counterfactual: score the training rows with and without the package-history features
   (hist_k, hist_n set to 0, hist_rate set to the global rate). In-sample, so read it as 'how much does the
   model rely on history', not as accuracy.
"""
import argparse
import sqlite3
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "modeling"))
import frozen_model  # noqa: E402,F401  (joblib needs the module to unpickle the model)
from common import load  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--package", default="sphinx", help="substring of the package name")
ap.add_argument("--db", help="SQLite file with scored PRs (the live-data database)")
ap.add_argument("--model", default=str(ROOT / "pipeline" / "models" / "model_v1.joblib"))
a = ap.parse_args()
pd.set_option("display.width", 220)
pd.set_option("display.max_colwidth", 90)

if a.db:
    con = sqlite3.connect(a.db)
    top = pd.read_sql("SELECT repo, pr_number, package, old_version, new_version, created_at, band, "
                      "ROUND(risk_score, 3) AS score, reasons FROM scored_prs WHERE status='scored' "
                      "ORDER BY risk_score DESC LIMIT 10", con)
    print("== 1. top 10 scored PRs ==\n" + top.to_string(index=False) + "\n")

df = load(str(ROOT / "data" / "feature_table_v2.csv"))
mask = df["package_norm"].str.contains(a.package, case=False)
sub = df[mask]
print(f"== 2. '{a.package}' in the frozen training data ==")
print(f"labeled rows {len(sub)}, breakages {int(sub['label'].sum())}, rate {sub['label'].mean():.3f} "
      f"(all rows: {df['label'].mean():.3f})")
print(sub.groupby("package_norm")["label"].agg(["count", "sum"]).sort_values("count", ascending=False).head(8).to_string())
br = sub[sub["label"] == 1]
if len(br):
    print("\nbreakages by repo:\n" + br["repo"].value_counts().to_string())
    print(f"\ncreated between {br['created_at'].min():%Y-%m-%d} and {br['created_at'].max():%Y-%m-%d}")
    labels = pd.read_csv(ROOT / "data" / "labeled_prs_v2.csv")
    raw = labels.merge(br[["repo", "pr_number"]], on=["repo", "pr_number"])
    print("\ndistinct bumps (package, old -> new) behind those breakages, and where they happened:")
    print(raw.groupby(["package_norm", "old_version", "new_version"])["repo"]
          .agg(lambda s: ", ".join(sorted(s))).to_string())
    if "failed_workflows" in raw:
        print("\nfailed workflows:\n" + raw["failed_workflows"].value_counts().head(8).to_string())

model = joblib.load(a.model)
X = df.copy()
neutral = df.copy()
neutral["hist_k"] = 0.0                       # log1p(0)
neutral["hist_n"] = 0.0
neutral["hist_rate"] = neutral["hist_global_rate"]
s1, s0 = model.score(X), model.score(neutral)
p1, p0 = model.percentile(s1), model.percentile(s0)
rows = []
for name, m in ((f"'{a.package}' rows", mask.to_numpy()), ("all other rows", ~mask.to_numpy())):
    rows.append({"group": name, "rows": int(m.sum()),
                 "mean percentile": p1[m].mean(), "without package history": p0[m].mean(),
                 "share in top 20%": (p1[m] >= 0.80).mean(), "top 20% without history": (p0[m] >= 0.80).mean()})
print("\n== 3. counterfactual: remove the package-history features ==")
print(pd.DataFrame(rows).round(3).to_string(index=False))