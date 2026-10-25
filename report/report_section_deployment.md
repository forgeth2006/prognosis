# Deployment: the scheduled scoring system

*Author: Esther (Person A). Covers how the trained model runs as a live system. The model itself is described in the modeling section.*

## 1. What the system does

Every 6 hours, a scheduled job on GitHub finds the currently open Dependabot pull requests in the 17 tracked repositories, scores each one for breakage risk with the frozen model, and saves the results. A dashboard reads the saved results. We chose a scheduled batch job instead of a real-time webhook service because a batch job still shows the full input-to-output flow but needs no always-on server and is far simpler to keep running.

## 2. The flow

1. **Trigger.** A GitHub Actions workflow runs every 6 hours (and can also be started by hand from the Actions tab). A lock prevents two runs from overlapping and overwriting each other's results.
2. **Collect.** The scraper fetches open Dependabot pull requests into a separate `data/live` folder, so the frozen training dataset is never touched.
3. **Filter.** The same exclusion rules used in training are applied (for example, grouped or multi-package updates). Skipped pull requests are stored together with the reason.
4. **Features.** Bump features and graph features are computed with the same functions used for training, so the system sees data in the same form the model was trained on. A parity check rebuilds 150 training pull requests through the live path and compares them with the training table: all 16 feature columns match, and the historical rate matches too.
5. **Score.** The frozen model scores each pull request. Pull requests already scored are not scored again. A failure in one repository is logged and the others continue.
6. **Store.** Results are written to a small SQLite database, which the job publishes to a branch called `live-data`. That branch is written only by the job and keeps a single commit, so the repository does not grow every 6 hours. The next run restores the database from this branch before adding new results.
7. **Display.** The Streamlit dashboard shows recent pull requests with a risk band and percentile.

## 3. First live run

The first successful run saw 56 open pull requests, scored 31 and skipped 25. It listed the highest-risk pull requests, for example "review first" and "look closer" bands. The whole run takes about three minutes.

## 4. What the system reports and what it does not

The dashboard shows **risk bands and percentiles, not exact probabilities.** In our evaluation, the calibrated probabilities were still no better than always predicting the average breakage rate (Brier score), so showing "73% risk" would suggest more precision than we have. The ranking of pull requests is more trustworthy than the exact number.

## 5. Problems we hit

The first two GitHub runs failed because of version mismatches. The frozen model was saved with scikit-learn 1.4.2, but GitHub installed the newest scikit-learn, which cannot load an older model file. Pinning the old version then required an older numpy, which in turn required an older pandas. The lesson is that a saved model is only safe to load with the library versions it was saved with, so the versions need to be fixed for as long as the model is frozen. The alternative, retraining the model with current versions, is documented as future work.

## 6. Limits

- Only Dependabot pull requests are found, not Renovate.
- Changelog features are not computed for live pull requests.
- The historical breakage rate uses history up to the dataset freeze and does not update as new pull requests close.
- The scoring database lives on a Git branch, which is fine for a course project but would be replaced by a proper database in production.
- Monitoring for drift (the model becoming less accurate as projects change) is described but not built.

## 7. How this would scale in a company

In a real deployment this would run as a GitHub App with a webhook, posting the risk band directly on each pull request as a comment, with the model retrained on a rolling window to handle drift.
