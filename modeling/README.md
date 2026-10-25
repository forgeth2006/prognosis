# modeling/ (Person C)

## Status
Draft stage. Waiting on B's 3-repo validation to know the real breakage rate.

## Temporal split
`temporal_split.py` loads `data/labeled_prs_v0.csv`, keeps labeled rows, left-joins
`data/graph_prototype_v0.csv` on `repo` + `package`, and splits by `created_at`
(oldest 80% train, newest 20% test). It asserts train and test do not overlap in time.

## Decisions
- PRs with no graph row: blast radius 0 plus a `not_in_graph` flag.
- Depth NaN for test-only packages: [pending B's answer].
- Outcome columns (ci_status, n_workflow_runs, failed_workflows, flaky_workflows,
  fail_confidence) are excluded from features to avoid leakage.

## Open items for Checkpoint 2
- Class balance (label=1 share) once B's validation arrives.
- Historical breakage rate feature must use only earlier bumps (point-in-time).
- Graph features are a snapshot of the repo today, not at each PR's date.

## Review of B's label and historical-rate logic (Person C)
- Label rule (`scraping/LABEL_RULES.md`, `label_ci.py`): re-runs, grouped bumps and CI-config
  PRs are handled as documented. Verified: 0 labeled rows touch CI config.
- Historical rate (`graph_features/historical_rate.py`): verdicts are counted only if known
  strictly before the PR's creation; the global rate is also point-in-time; unseen packages
  fall back to the global rate.
- To tune (training period only): PRIOR_RATE, PRIOR_STRENGTH, M.
 - Label defect identified: mitmproxy's 55 failures were attributed to `autofix.ci`, and 25 of
  streamlit's 26 to `Run Semgrep Checks`. `IGNORE_WORKFLOW` now excludes these workflows, with
  regression tests covering ignored workflows and genuine test failures. A fresh full-dataset
  relabel and downstream validation remain to be confirmed.
- Yield: PRs before 2025Q3 have no CI results (0 labeled); from 2025Q4 53-78% label.
  Usable history is about 14 months (2025-08 to 2026-10).
- Only 5 of 215 breakages are `confirmed`, so a confirmed-only sensitivity run is infeasible.
- Open: lint/docs workflows count as failures.

## Baseline (Week 8), computed on labeled_prs_v2 / feature_table_v2
Rule: predict "breaks" when `major_delta > 0`. Script: `modeling/baseline.py`
(temporal split, cutoff 2026-09-01). Labels: v2 (non-test workflows ignored).

| split | n | positives | precision | recall | PR-AUC |
|---|---|---|---|---|---|
| train | 1051 | 114 (10.8%) | 0.182 | 0.211 | 0.124 |
| test | 263 | 15 (5.7%) | 0.143 | 0.200 | 0.074 |

Floor to beat: test PR-AUC 0.074 (prevalence 0.057).
The rule flags few PRs and is only modestly better than chance (train precision 0.182 vs
base rate 0.108). Test has 15 positives (3 true positives), so these numbers are noisy: one
more or fewer hit moves recall by about 7 points.
Breakage rate fell from 10.8% (train) to 5.7% (test): temporal shift or noise, to be checked.
Next: multi-fold time-ordered validation to get stable estimates.
# Sufficiency test (Week 12)
Setup: 5 time-ordered chunks, 4 expanding-window test folds; both models class-weighted and
Platt-calibrated; identical features. GB fixed at depth 3 / 200 trees / lr 0.05 (no tuning: 129 positives).
Result: pooled PR-AUC LR [x] vs GB [y]; difference [d] (95% CI [lo, hi]); GB wins [k] of 4 folds;
Brier LR [a] vs GB [b]; leave-one-repo-out: [summary].
Conclusion: [logistic regression is sufficient / boosting adds value] because [...].
Limits: ~129 positives (~20 per fold); row bootstrap ignores repo clustering; hist_* and
changelog features are present for most but not all rows.

# limitations
- Package history can reflect a single episode. Sphinx has 6 breakages, 5 of them within 4 days
  (Dec 2025, the 9.0.x releases, in three sibling repos), and no labeled sphinx PR after 2026-01-06,
  so the frozen data cannot show whether that risk persisted. Live sphinx PRs therefore score high
  mainly through `hist_rate`. Packages such as ruff, tox and coverage have breakages spread over
  4-12 months, where history is a more credible signal. Possible follow-up: recency-weighted history,
  to be tested on the time-ordered folds before adoption.