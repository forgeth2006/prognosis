# Data issues found while reviewing the Weeks 9-12 modeling (Person B)

Everything below is read-only on the frozen dataset. Scripts: `graph_features/check_label_trend.py`, `graph_features/check_loro_history.py`.

## 1. Why the breakage rate falls across time chunks (17.6 -> 5.7%)
Output of `check_label_trend.py` (percent, chunks oldest to newest):

| | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| observed | 17.5 | 12.2 | 8.0 | 5.7 | 5.7 |
| repo-adjusted | 15.1 | 9.6 | 8.7 | 7.0 | 7.3 |
| + shared-cause weeks removed | 10.9 | 7.7 | 7.0 | 6.8 | 6.1 |
| + closed within 2 days only | 6.7 | 3.9 | 5.4 | 5.1 | 4.8 |
| both | 3.9 | 3.2 | 3.4 | 4.6 | 3.7 |

Read: repo mix, early shared-cause weeks and censoring each explain part of the drop, and with all three controlled the rate is
roughly flat (3-5%). Caveat: shared-cause weeks and time-to-close are defined from the outcome, so this is a diagnostic, not a corrected estimate.
Censoring evidence: 40% of breakages were open 7+ days before closing against 7% of clean PRs.
Fix to quantify it: re-scrape **open** PRs (`scrape_prs.py --state open`, separate output file). Needs Esther's OK because the dataset is frozen.

## 2. LORO results are optimistic
In leave-one-repo-out, `hist_*` features still contain verdicts from the held-out repo's own earlier PRs for the same package
(measured: 53% of all earlier same-package evidence is same-repo, and 88% of rows with any evidence include some), which a truly new repo would not have. Proposal: report LORO with cross-repo-only history, or without `hist_*`, next to the current numbers.

## 3. "Logistic regression is sufficient" is not yet supported
The LR vs gradient-boosting ordering flips with the feature setup, and GB results depend on the scikit-learn version (unpinned). Suggest wording:
"no demonstrated gain from the more complex model on this data" and pinning `scikit-learn` in `requirements.txt`, recording versions with results.

## 4. Smaller notes
- `hist_global_rate` and `hist_rate` smoothing constants are fixed by hand, not tuned; say so.
- Imputing graph depth with 0 conflates "test-only" with "depth zero"; keep `depth_missing` in the model.
