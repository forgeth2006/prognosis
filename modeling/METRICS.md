# Evaluation metrics (Person C)

## Problem
Binary classification: will a dependency-bump PR break CI (label=1) or not (label=0).
Output is a calibrated probability, not just a yes/no.

## Validation
Temporal split by `created_at` (oldest 80% train, newest 20% test). No random shuffling.

## Metrics
- Primary: PR-AUC (average precision). Floor = share of positives in the test set.
- Precision and recall at a chosen threshold, plus the confusion matrix.
- Calibration: Brier score and a calibration curve.
- Never plain accuracy (about 84% of rows are label 0).

## Baseline (floor to beat)
Rule: predict "breaks" when major_delta > 0, else "safe".

## Label rule
See scraping/LABEL_RULES.md. Open question: repos with 100% breakage (mitmproxy, streamlit).