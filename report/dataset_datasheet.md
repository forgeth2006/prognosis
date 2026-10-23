# Dataset datasheet: PRognosis frozen dataset v2

**Purpose.** Predict whether a Dependabot version bump in a Python repository will fail CI, using only information available when the PR is opened.

**Files.** `data/labeled_prs_v2.csv` (all 4,835 scraped PRs with labels and exclusion reasons), `data/feature_table_v2.csv` (1,314 labelled rows, one per PR), `data/graph_snapshots_v2.csv`, `data/graph_snapshots_index_v2.csv`, `data/changelog_features*.csv`. Frozen at tag `checkpoint-2-dataset-freeze`; no change without telling Esther.

**Composition.** 1,314 PRs from 13 repositories (4 further repositories yielded no labelled rows), created 2025-08-12 to 2026-10-16. 129 breakages (9.8%). Per-repo breakage rate 0% to 33%.

**Label.** 1 if a GitHub Actions workflow triggered by the PR failed on Dependabot's first commit; 0 if all passed. PRs whose failure disappeared on re-run (flaky) are excluded. Details: `scraping/LABEL_RULES.md`.

**Features.** Bump type and version deltas; import-graph blast radius and depth from a point-in-time snapshot of the repo; smoothed historical breakage rate from strictly earlier CI verdicts; changelog indicators. Outcome columns are never features (list in `data/dataset_checks_v2.md`).

**Known biases.** Closed PRs only (failing PRs close later, so recent rows under-count breakages); repo selection by the team, not random; PRs without PR-triggered CI are excluded, so repos with CI differ from those without; failures cluster in shared-cause weeks; static imports miss dynamic use. See `report/data_issues_found_in_modeling.md`.

**Intended use.** Course project analysis and modelling. Not suitable for claims about all Python projects, or for showing precise probabilities.

**Source and licence.** Public GitHub API data about public repositories; no personal data beyond public usernames in PR metadata, which the feature table does not include.

**Reproduce.** `python graph_features/make_report_figures.py`; tests `python -m unittest discover -s graph_features/tests`.
