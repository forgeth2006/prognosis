# Sufficiency test (Week 12)
Setup: feature_table_v2 (1314 rows, 129 breakages). Time-ordered: 5 chunks, 4 expanding-window folds
(pooled n=1052, 83 breakages). Leave-one-repo-out (11 repos with breakages; pytest and langchain skipped).
Both models class-weighted and Platt-calibrated; GB fixed at depth 3 / 200 trees / lr 0.05, no tuning.

Time-ordered: pooled PR-AUC LR 0.126 vs GB 0.258 (diff +0.131, CI +0.064 to +0.206); GB wins 3 of 4 folds,
but 0.482 of its score is fold 1 (test set concentrated in numpy and frozenlist); in folds 2-4 the models are close.
Leave-one-repo-out: pooled LR 0.105 vs GB 0.078 (diff -0.027, CI -0.045 to -0.013); mean per-repo PR-AUC
LR 0.239 vs GB 0.216; GB wins 5 of 11 repos.
Conclusion: logistic regression is sufficient. Boosting's time-ordered advantage does not hold on unseen repos.
Limits: 129 breakages; row-level bootstrap ignores repo clustering; sibling aio-libs repos make LORO optimistic;
repos with 1-4 breakages give unstable per-repo scores.

Add these two lines:
“Baseline: logistic regression beats the ‘major bump’ rule (pooled PR-AUC 0.149 vs 0.088; random = 0.079, time-ordered folds).”
“Calibration: Platt scaling fixed the probability scale (Brier 0.285 to 0.104), but the calibrated Brier is still no better than always predicting the base rate, so don’t show probabilities as precise percentages yet. Tables: modeling/results/.”