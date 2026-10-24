# Final validated metrics (Week 13)

Script: `modeling/validation.py`. Outputs: `modeling/results/week13_final_metrics.csv`,
`modeling/results/week13_review_queue.csv`.

## Setup
- Data: `data/feature_table_v2.csv` (frozen dataset): 1314 labeled PRs, 129 breakages (9.8%).
- Strict time-ordered validation: PRs sorted by creation date and cut into 5 chunks. Chunk 1 is only
  ever training data. Each of folds 1-4 trains on everything before a chunk and tests on that chunk
  (263 PRs each; pooled test n = 1052 PRs, 83 breakages; random-ranking floor = 0.079).
- Purge: a training PR is used only if its continuous integration (CI) verdict was already known when
  the test window started. This removed 46, 53, 44 and 47 training rows in folds 1-4 (17.6%, 10.1%,
  5.6%, 4.5% of each training window). No PR was missing a verdict time.
- Test windows start 2026-01-03, 2026-04-25, 2026-07-09 and 2026-09-01.
- Final model: logistic regression with class weighting and Platt calibration, fit on the older 75% of
  each training window and calibrated on the newest 25% (so calibration never sees the future).
- Outcome columns (CI status, workflow counts, failed workflows, etc.) are excluded from the features.

## Results (pooled over the four test windows)
| model | PR-AUC | 95% confidence interval | PR-AUC per fold (1/2/3/4) | Brier | Brier if constant | ECE |
|---|---|---|---|---|---|---|
| baseline (major bump = risky) | 0.088 | 0.069 - 0.115 | 0.134 / 0.085 / 0.060 / 0.074 | n/a | n/a | n/a |
| logistic regression v1 | 0.154 | 0.109 - 0.220 | 0.221 / 0.139 / 0.085 / 0.058 | 0.114 | 0.073 | 0.124 |
| logistic regression, balanced + Platt (final) | 0.143 | 0.103 - 0.203 | 0.200 / 0.136 / 0.073 / 0.072 | 0.101 | 0.073 | 0.080 |

PR-AUC (area under the precision-recall curve) rewards ranking real breakages above safe PRs; random
ranking scores 0.079 here. Brier score is the mean squared error of the predicted probability (lower
is better); "Brier if constant" is the score of always predicting the average breakage rate of the
tested PRs. ECE is the average gap between predicted and observed breakage rates.

## Review queue (final model; what a reviewer gets by checking the riskiest PRs first)
| review | PRs | breakages caught | precision | recall | lift |
|---|---|---|---|---|---|
| top 5% | 53 | 11 | 0.208 | 0.133 | 2.63 |
| top 10% | 105 | 20 | 0.190 | 0.241 | 2.41 |
| top 20% | 210 | 33 | 0.157 | 0.398 | 1.99 |

Lift = precision divided by the overall breakage rate (0.079). For comparison, the baseline rule flags
115 PRs, catches 15 breakages, with precision 0.130 and recall 0.181 (lift 1.65). At about the same
review workload (105 vs 115 PRs) the final model catches 20 breakages against 15.

## What the results say
- Logistic regression ranks breakages better than the "major bump" rule (0.143-0.154 vs 0.088 PR-AUC),
  and about twice as well as chance, but the gain is modest.
- The two logistic regression variants are not distinguishable on ranking (confidence intervals overlap
  almost completely). The final model is preferred because its probabilities are better calibrated
  (ECE 0.080 vs 0.124; Brier 0.101 vs 0.114).
- The probabilities are still not precise: the final model's Brier score (0.101) is worse than
  always predicting the average rate (0.073). The dashboard should show a risk ranking or risk band
  (for example top 5% / top 10% / top 20% of scores), not a precise percentage.
- Performance is highest in the earliest test window and lower in later ones, as the breakage rate
  fell over time (17.6% in the oldest chunk to 5.7% in the last two).

## Limits (read before quoting any number)
- Only 129 breakages (83 in the pooled test windows, 15-32 per window). Differences of about 0.03
  PR-AUC, or a few caught breakages, are within noise. For example, 20 vs 15 breakages caught is not
  a demonstrated difference.
- The confidence intervals resample PRs, not repositories or time windows, so they are narrower than
  the true uncertainty.
- The model type, class weighting and calibration method were chosen after seeing all four windows,
  including the newest. This is a strict re-validation, not a test on untouched data. The dataset is
  frozen, so a genuinely untouched test would need PRs scraped after the freeze.
- Purging changed the final model's pooled PR-AUC from 0.126 to 0.143 (fold 1: 0.152 to 0.200), which
  shows how sensitive these numbers are to small changes in the training set.
- Leave-one-repo-out results and the boosting comparison are in `modeling/sufficiency.md` and
  `modeling/results/`.