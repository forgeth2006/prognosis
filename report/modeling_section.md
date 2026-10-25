# Modeling

## Task and label
Each Dependabot bump pull request (PR) is labeled 1 if continuous integration (CI) failed on the bump
and 0 if it passed (rules in `scraping/LABEL_RULES.md`). The model outputs a risk score used to rank
PRs for review. The frozen dataset has 1,314 labeled PRs from 13 repositories, 129 of them breakages (9.8%).

## Features (25 inputs in four groups)
- **Bump (7):** bump type, major/minor/patch version deltas, prerelease, zero-major and range-update flags.
- **Dependency graph (9):** blast radius (files importing the package: direct, in source, in tests,
  transitive), depth, and flags for packages not imported. Computed from a snapshot of each repository taken at
  the start of the PR's month, so a PR only sees earlier code.
- **Package history (4):** the package's smoothed breakage rate over earlier PRs in all repositories, using only
  PRs whose CI verdict was known before the PR was created.
- **Changelog (5):** whether a changelog was found, its size, and a breaking-change keyword. Scraped for the
  frozen data; not available for live PRs.
CI outcome columns are never used as features.

## Validation
PRs are ordered by creation date and cut into five chunks. The oldest chunk is training only; each later chunk is a
test window, trained on everything before it (four windows starting 2026-01-03, 2026-04-25, 2026-07-09 and
2026-09-01; 263 PRs each, 83 breakages pooled). Training PRs whose CI verdict was not yet known when a test window
began are removed (46, 53, 44 and 47 PRs). Metrics: PR-AUC (random ranking scores 0.079), the review queue
(precision, recall and lift in the top 5%, 10% and 20% of scores), Brier score and expected calibration error (ECE).
95% intervals come from bootstrapping PRs. A leave-one-repository-out check tests generalisation to unseen
repositories.

## Models
1. **Baseline:** "major version bump = risky".
2. **Logistic regression:** standardized numeric features, log transform of counts, one-hot bump type, missing
   values set to 0 with indicator flags, L2 penalty.
3. **Class imbalance:** class weights and oversampling (training data only).
4. **Calibration:** Platt scaling fitted on the newest 25% of each training window; isotonic regression compared.
5. **Sufficiency test:** gradient-boosted trees (depth 3, 200 iterations, learning rate 0.05, class-weighted, not
   tuned) against the calibrated logistic regression.

## Final model
Class-weighted logistic regression with Platt calibration, trained on all 1,314 PRs. Scores are turned into bands
using the score distribution of the newest quarter of the data: top 5% "review first", next 15% "look closer",
the rest "routine". The scores are used to rank PRs, not as exact probabilities (see Results).