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
 - Label defect found: mitmproxy's 55 failures are all `autofix.ci` and 25 of streamlit's 26 are
  `Run Semgrep Checks` (non-test workflows). Removing them leaves about 135 breakages (~10%).
  Needs IGNORE_WORKFLOW update + re-label (Person B).
- Yield: PRs before 2025Q3 have no CI results (0 labeled); from 2025Q4 53-78% label.
  Usable history is about 14 months (2025-08 to 2026-10).
- Only 5 of 215 breakages are `confirmed`, so a confirmed-only sensitivity run is infeasible.
- Open: lint/docs workflows count as failures.

## Baseline (Week 8) — PROVISIONAL, computed on labeled_prs_v1 before the label fix
Rule: predict "breaks" when `major_delta > 0`. Script: `modeling/baseline.py`
(temporal split, cutoff 2026-09-01).

| split | n | positives | precision | recall | PR-AUC |
|---|---|---|---|---|---|
| train | 1096 | 175 (16.0%) | 0.195 | 0.149 | 0.165 |
| test | 275 | 40 (14.5%) | 0.190 | 0.100 | 0.150 |

Floor to beat: test PR-AUC 0.150 (prevalence 0.145). The rule is barely above chance
(TP=4, FP=17, FN=36 on test), so version-bump size alone says little.
Caveats: only 40 test positives, so differences are noisy; labels still include non-test
workflow failures (autofix.ci, Semgrep). Re-run after Person B re-labels.