# Review of the live scoring pipeline's use of the data and graph code (Person B, Week 15)

Read: `pipeline/features_live.py`, `pipeline/score_batch.py`, `pipeline/check_parity.py`, `.github/workflows/score.yml`.
Question from Supreeta: have `add_graph_features`, `snapshots.py` and `scrape_prs.py --state open` been used correctly?

## Used correctly
- **`static_exclusion`**: the raw scrape is read with `dtype=str`, which is what the function expects (it compares to `"True"`), so the live exclusions match training.
- **`scrape_prs.py --state open`**: separate `--out` and `--cache-dir`, cache cleared each run, newest first. The frozen dataset is untouched.
- **`snapshots.py`**: one call per repo with `--months` taken from `created_at[:7]` (UTC), the same month rule as training. The snapshot is the last commit before the 1st of the PR's month, so no future code is used.
- **`add_graph_features`**: called with the same snapshot and index layout as training; the duplicate-key asserts will fire if a snapshot is repeated.
- **`add_historical_rate`**: new PRs have no label or close time, so they are never counted as evidence, and each uses only earlier verdicts.
- **Skips**: a failed repo is logged and skipped, other repos continue.

## Things to fix or state
1. **Cloning cost in the scheduled job.** `snapshots.py` makes a fresh bare clone of every repo on every run (the runner is new each time). Large repos (numpy, saleor, esphome, streamlit) can use much of the 30-minute limit. Cache `graph_features/.checkouts` between runs (`actions/cache`), or run a repo list per run.
2. **`check_parity.py` does not test the live snapshot path.** It rebuilds features from the frozen snapshot files, not from `snapshots.py`. That is useful for the feature code but not for the clone-and-read step. Add one repo-month where `snapshots.py` output is compared with `graph_snapshots_v2.csv` (for example `aio-libs/yarl`, one month).
3. **Historical rate is stale and tied to timestamps.** It uses `labeled_prs_v2.csv`, whose `ci_completed_at` came from run `updated_at`. After the job-timestamp fix (`7373819`) a new version of this file would change `hist_*` for many rows, and the frozen model was trained on the old values. Do not swap the history file without retraining or at least re-running parity.
4. **Same-repo evidence.** For live PRs in a repo the model was trained on, `hist_*` includes that repo's own verdicts, as in training. This is fine for these repos, but it is why leave-one-repo-out numbers do not describe a brand-new repo (see `data_issues_found_in_modeling.md`).
5. **Dependabot only.** The scraper's first-commit check and title parser are Dependabot-specific; Renovate PRs are invisible. Say so on the dashboard.
6. **Dashboard sphinx question.** Three of the top five were sphinx bumps. Check `hist_n`, `hist_k` for sphinx in the frozen table and the model's reasons for those PRs. I checked the frozen table: sphinx has 10 labelled PRs and 6 breakages (60%), spread over 4 repos (frozenlist 3, aiosignal 3, yarl 2, pytest-asyncio 2), and the latest ones carry `hist_rate` of about 0.34-0.39 (5 of 8 earlier verdicts). So the model is leaning on package history, and the evidence is real but thin: 10 PRs, mostly major bumps in sibling aio-libs repos that probably share one docs-build setup, so it is closer to one repeated cause than six independent events. Report it as 'sphinx has broken CI before in this project's repos', not as a general sphinx risk. 
7. **scikit-learn pin.** Esther pinned 1.4.2 in the workflow; `requirements.txt` should match, otherwise anyone running the dashboard on a newer version hits the same load error.
