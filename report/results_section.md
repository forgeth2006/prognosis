# Results

## Ranking quality (final, time-ordered, label-purged windows)
| model | PR-AUC (95% interval) | per-window PR-AUC |
|---|---|---|
| random ranking | 0.079 | |
| baseline (major bump) | 0.088 (0.069-0.115) | 0.134 / 0.085 / 0.060 / 0.074 |
| logistic regression | 0.154 (0.109-0.220) | 0.221 / 0.139 / 0.085 / 0.058 |
| logistic regression, balanced + Platt (final) | 0.143 (0.103-0.203) | 0.200 / 0.136 / 0.073 / 0.072 |

The learned model ranks breakages better than the version-number rule and at 1.8 times the random-ranking score (0.143 against 0.079), but the gain is modest and shrinks in later
windows. The intervals of the baseline and the final model overlap slightly (0.115 against 0.103), so the
difference is suggestive, not established. The two logistic regression variants cannot be told apart on ranking.

## Review queue
| PRs reviewed (highest score first) | breakages caught | precision | recall | lift |
|---|---|---|---|---|
| top 5% (53) | 11 of 83 | 0.208 | 0.133 | 2.6 |
| top 10% (105) | 20 of 83 | 0.190 | 0.241 | 2.4 |
| top 20% (210) | 33 of 83 | 0.157 | 0.398 | 2.0 |

The "major bump" rule flags 115 PRs and catches 15 breakages (precision 0.130, recall 0.181). At about the same
review workload, the final model catches 20.

## Class imbalance and calibration (exploratory runs, without the label purge)
Class weighting and oversampling did not change ranking (PR-AUC 0.149, 0.148 and 0.140, overlapping intervals) but
inflated the probabilities (Brier 0.285 for the weighted, uncalibrated model). Platt scaling reduced Brier to 0.104
and ECE from 0.360 to 0.085; isotonic regression was slightly worse (0.118, 0.100). In the final purged run the
calibrated model has Brier 0.101 and ECE 0.080, but a model that always predicts the average rate scores 0.073, so
the scores should not be read as precise probabilities.

## Sufficiency test: gradient boosting against logistic regression
In time-ordered windows boosting scored higher (PR-AUC 0.258 against 0.126; difference +0.131, 95% interval +0.064
to +0.206; better in 3 of 4 windows), but this rests on the first window (0.482), which is concentrated in two
repositories. In windows 2 to 4 the models are close. With whole repositories held out, boosting is worse (pooled
0.078 against 0.105, difference -0.027, interval -0.045 to -0.013; mean per-repository PR-AUC 0.216 against 0.239;
better in 5 of 11 repositories). Logistic regression is therefore sufficient here (indicative, given 129 breakages).

## Feature groups
We removed one feature group at a time from the final model and measured the change in pooled PR-AUC on the same
label-purged windows (95% interval over PRs).

| variant | features | PR-AUC | change vs all features (95% interval) |
|---|---|---|---|
| all features | 25 | 0.143 | |
| bump features only | 7 | 0.140 | -0.003 (-0.043 to +0.044) |
| without dependency graph | 16 | 0.131 | -0.012 (-0.037 to +0.018) |
| without package history | 21 | 0.141 | -0.002 (-0.034 to +0.037) |
| without changelog | 20 | 0.139 | -0.003 (-0.014 to +0.009) |
| without bump features | 18 | 0.146 | +0.003 (-0.016 to +0.036) |

No group's removal produced a detectable change, and a model using only the seven version-bump features
matched the full model within the uncertainty. We therefore cannot show that the dependency-graph features
improve ranking in this dataset. With 83 breakages in the test windows the intervals are roughly +/-0.03 to
+/-0.04 PR-AUC wide, so modest contributions cannot be ruled out either. The learned model's advantage over the
"major bump" rule (0.143 against 0.088) is already reached with the bump features alone, so it comes from weighing
the version information, not from the added feature groups.

## Live pipeline
As of 2026-10-25 (last run 12:21 UTC), the database written by the scheduled pipeline holds 33 scored open
Dependabot PRs (2 in the "review first" band, 15 in "look closer", 16 "routine") and 27 skipped PRs. The skipped
PRs were excluded by the same rules used in training:                                                     
                                                     note  n
                 excluded by training rules: range_update  9
                 excluded by training rules: grouped_bump  8
excluded by training rules: non_pip_or_non_manifest:other  7
excluded by training rules: non_pip_or_non_manifest:cargo  2
  excluded by training rules: non_pip_or_non_manifest:npm  1
          run_id status  n_seen  n_scored  n_skipped
20261025T122107Z     ok      55         0         27
20261025T114617Z     ok      55         0         27
20261025T112908Z     ok      56         1         27.
 The pipeline runs every 6 hours on GitHub
Actions and publishes its database to the `live-data` branch. The live scores are used to rank PRs; they range
from 0.05 to 0.07 and are not precise probabilities.
## Limitations
- Only 129 breakages (83 in the test windows, 15 to 32 per window); small differences are noise. Intervals resample
  PRs, not repositories or windows, so they are narrower than the true uncertainty.
- The model type, class weighting and calibration were chosen after seeing all test windows, so this is a strict
  re-validation, not a test on untouched data.
- Breakage rates differ by repository (0% to 33%) and fell over time (about 17.6% in the oldest fifth to 5.7% in the
  newest two fifths), and the two are partly confounded.
- Package history can reflect a single episode: sphinx has 5 of its 6 breakages within four days in December 2025
  and no labeled PR after 6 January, so its live scores rest on one burst.
- Breakage labels come from a single CI run: 124 of the 129 breakages (96%) failed on their first attempt, and only
  5 were confirmed by a failed re-run, so some labels may be flaky failures. For the same reason a
  confirmed-only sensitivity analysis is not possible (5 positives).
- Live PRs use "not scraped" changelog features, and only Dependabot PRs are collected.
-Limitations: “The ablation cannot detect contributions smaller than roughly 0.03 to 0.04 PR-AUC. Package history shows no detectable accuracy gain, yet it drives the live ranking of packages with one burst of breakages (sphinx).”