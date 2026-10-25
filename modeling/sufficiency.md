# Sufficiency test (Week 12)

**Question.** Is logistic regression (LR) enough for this problem, or do we need a more flexible model such as gradient boosting (GB)?

**Short answer.** On the evidence we have, LR is sufficient. These results are **indicative, not conclusive**, because the dataset has only 129 breakages.

## Setup

- Data: `feature_table_v2` (1,314 rows, 129 breakages), frozen at Checkpoint 2.
- Time-ordered evaluation: 5 chunks, 4 expanding-window test folds (pooled n = 1,052, 83 breakages).
- Leave-one-repo-out (LORO) evaluation: each repo held out in turn. 11 repos with breakages were evaluated; pytest and langchain were skipped.
- Both models in this comparison are class-weighted and Platt-calibrated. GB is fixed at depth 3, 200 trees, learning rate 0.05, with no tuning.
- Metric: PR-AUC (area under the precision-recall curve). "95% confidence interval" is written as CI below; it is unrelated to the CI (continuous integration) build system.

## Results

### Time-ordered folds

| | LR | GB |
|---|---|---|
| Pooled PR-AUC | 0.126 | 0.258 |

- Difference GB minus LR: +0.131 (95% CI +0.064 to +0.206). GB wins 3 of 4 folds.
- The advantage comes almost entirely from fold 1, where GB's PR-AUC is 0.482. That fold's test set is concentrated in numpy (10 of its 32 breakages) and frozenlist (6 of its 8 PRs).
- In folds 2 to 4 the models are close: GB 0.124, 0.098, 0.119 against LR 0.141, 0.075, 0.075.
- GB may be learning which repo a PR comes from, since breakage rates range from 0% to 33% by repo.

### Leave-one-repo-out

| | LR | GB |
|---|---|---|
| Pooled PR-AUC | 0.105 | 0.078 |
| Mean per-repo PR-AUC | 0.239 | 0.216 |

- Pooled difference GB minus LR: -0.027 (95% CI -0.045 to -0.013). The interval is entirely below zero.
- GB wins only 5 of 11 repos, and is worse on the repos where LR does best (aiosignal, frozenlist, yarl, pytest-asyncio).
- GB's time-ordered advantage therefore does not hold on repos it has not seen.

### Supporting results (details in `modeling/results/*.csv`)

- **Baseline ("major bump = risky").** LR beats it. Time-ordered pooled PR-AUC: baseline 0.088, LR 0.149 (95% CI 0.104 to 0.212). In the top 10% riskiest PRs, precision is 0.19 for LR against 0.12 for the baseline. Under LORO, mean per-repo PR-AUC is 0.272 for LR against 0.163 for the baseline (top-10% precision 0.265 against 0.205).
- **Class imbalance.** Class weights (0.148) and oversampling (0.140) made no demonstrable difference to PR-AUC compared with the unweighted LR (0.149). They do inflate the predicted probabilities.
- **Calibration.** Platt scaling fixed the probability scale (Brier score 0.285 to 0.104, expected calibration error 0.36 to 0.085). Isotonic calibration was slightly worse. However, the calibrated Brier score is still no better than always predicting the base rate, so **probabilities should not yet be shown as precise risk percentages**; the ranking of PRs is more trustworthy than the exact numbers.

## Conclusion

Logistic regression is sufficient. It beats the "major bump" baseline, it is interpretable, and boosting's time-ordered advantage does not generalise to unseen repos. We are not claiming boosting never helps, only that we found no reliable evidence that it is needed here. All results are indicative.

## Limitations

- Only 129 breakages; folds contain 15 to 32 breakages each, so every difference is noisy.
- The bootstrap resamples rows, not repos, so the confidence intervals are too narrow because PRs within a repo are not independent.
- The sibling aio-libs repos (aiosignal, frozenlist, yarl) are similar to each other, which makes LORO optimistic.
- Repos with 1 to 4 breakages give unstable per-repo PR-AUC scores.
- The breakage rate falls across the time-ordered chunks (17.6%, 12.2%, 8.0%, 5.7%, 5.7%), which may reflect repo mix or label effects rather than a real change in risk. See `report/` for the label-trend analysis.
