# Data and methodology (report section, Person B, Weeks 9-12)

## 1. What a row is
One row is one Dependabot pull request that bumps a single Python package in a pip manifest. The target is
`label = 1` if CI failed on the PR's first commit (the commit Dependabot wrote, before any human edit) and 0 if it passed.

## 2. Collection
- Source: GitHub REST API, 17 repositories chosen by the team (shortlist in `scraping/shortlist_repos.txt`).
  Up to 300 most-recent **closed** Dependabot PRs per repo (`scraping/scrape_prs.py`). 4,835 PRs scraped.
- Parsing (`parse_bump.py`): package, old and new version from the title; bump type (major/minor/patch), pre-release,
  0.x flags; range updates take versions from the compare URL where possible.
- Changelog features (Person A): `changelog_found`, length, `has_breaking_keyword`.

## 3. Labelling (`label_ci.py`, rules in `scraping/LABEL_RULES.md`)
- Verdict comes from GitHub Actions workflow runs on the first commit, `pull_request` / `pull_request_target` events only,
  minus a regex of non-test workflows (labelers, release drafters, etc.).
- A workflow that failed and then passed on re-run is **flaky** and the PR is excluded (51 PRs); we cannot tell a bad
  upgrade from a flaky test.
- `fail_confidence` records whether a failure was seen once (`single_attempt`) or confirmed on re-run.

## 4. Cleaning (`clean_dataset.py`): 4,835 -> 1,314 labelled rows
| reason excluded | PRs |
|---|---|
| no usable CI result (many repos have no PR-triggered CI on Dependabot PRs) | 1,584 |
| grouped bumps | 488 |
| range-spec updates (no real version pair) | 437 |
| not pip / not a manifest (npm, cargo, docker, other) | 563 |
| duplicate bump (same package, same versions) | 315 |
| touches CI config | 52 |
| flaky re-run | 51 |
| unusable repo, unparseable title, other | 31 |
| **kept** | **1,314 (129 breakages, 9.8%)** |

Four of the 17 repos contribute no labelled rows (pytorch-lightning, rich, mitmproxy, cryptography), so the model sees 13 repos.

## 5. Features
- **Bump**: type, deltas, pre-release, 0.x, range flag.
- **Graph (`graph_features/`)**: for each PR, the repo is graphed *as of the start of the PR's month* from git history
  (no checkout; `snapshots.py`), using static `ast` imports. Blast radius describes the number of modules importing the package, including direct and transitive imports across source and test code. The features also include minimum and mean import depth. `not_in_graph` means the package is a tool or
  transitive dependency never imported; `depth_missing` means test-only or not imported. Both are *flags*, not zeros.
- **Historical breakage** (`historical_rate.py`): per package, pooled across repos, over strictly earlier CI verdicts
  only (using the PR's `ci_completed_at`), smoothed toward 0.10 with strength 20.
- **Never features**: any outcome column (ci_status, failed workflows, merged, closed_at, ...).

## 6. Leakage controls and checks
- Graph snapshot is never newer than the PR (0 violations); history uses earlier verdicts only (brute-force recompute on 300 rows).
- Row counts and keys reconcile between labelled table and feature table; no unexplained nulls (`data/dataset_checks_v2.md`).
- Scraper, labeller, parser, graph-feature, and related analysis code are covered by automated unit tests. The latest test run passed all 85 tests: 52 scraping tests and 33 graph-feature tests.

## 7. CI completion timestamp validation
The CI labelling pipeline derives `ci_completed_at` from completed jobs associated with the relevant GitHub Actions workflow-run attempt. It does not substitute the workflow run's `updated_at` when job completion time cannot be established; in that case, the timestamp is left blank.

### Preliminary validation samples

- **20-PR smoke test:** All 20 PRs were included, with zero positive breakage labels.
- **100-PR multi-repository sample:** 50 PRs were included and 50 were excluded. None of the 50 included PRs received a positive breakage label.
- **20 previously labelled positive examples:** All 20 retained their positive breakage labels in this targeted validation check.

These samples serve different purposes. The positive-example sample was deliberately selected to check whether previously labelled breakages retained their labels. The 100-PR sample was not designed to estimate the dataset's overall breakage rate. Therefore, these preliminary checks do not establish that the full dataset has been revalidated.

### Timestamp comparison

In the earlier comparison with the existing frozen dataset, comparable rows showed either exact timestamp agreement or a one-second difference. This is a preliminary consistency check, not evidence of improved predictive performance.

The frozen feature table and dataset were not modified by these validation experiments.

## 8. Limitations (state these in the report)
1. **Few positives**: 129 breakages; per-repo rates run 0% to 33%. Confidence intervals are wide (see graph-layer section).
2. **Closed-only scrape (right-censoring)**: failing PRs stay open longer (median 3.1 days vs 0.05 for passing; 25% merged vs 92%),
   so the newest chunk is missing breakages that are still open. Rates in recent months are biased down.
3. **Repo mix**: label rates differ strongly by repo and repos enter the window at different dates.
4. **Shared-cause failures**: a broken base branch fails many PRs in a week together; these are not independent examples.
5. **Static graph**: `ast` imports miss dynamic imports, plugins, and non-Python usage.
6. **Confounding**: minor/patch deltas are tied to bump type; do not read their effects separately.
7. **Single CI definition**: "breakage" means "PR CI failed", which includes failures unrelated to the new version.