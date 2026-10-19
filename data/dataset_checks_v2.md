# Dataset checks - feature_table_v1 (Checkpoint 2)

1. **Row counts match: PASS** - labeled rows in labeled_prs_v1 = 1314; feature-table rows = 1314; duplicate (repo, pr_number) keys = 0
2. **Class balance reported: PASS** - 1314 labeled rows, 129 breakages (9.8%)
3. **No unexplained null features: PASS** - depth_min: 937 null (937 expected); depth_mean: 937 null (937 expected); changelog_chars: 474 null (474 expected); changelog_lines: 474 null (474 expected); has_breaking_keyword: 474 null (474 expected)
4. **Historical rate uses only earlier data: PASS** - brute-force recomputation on 300 random rows
5. **Graph snapshot never newer than the PR: PASS** - 0 rows violate

## Coverage notes
- changelog features matched for 100% of rows (`changelog_scraped`); the rest are unscraped, not 'no changelog'. Person A's scraper must be run on `data/pr_bumps_for_changelog.csv` first.
- rows with no repo snapshot at all: 0; package not imported in its snapshot (dev tool / transitive): 824; depth missing (test-only or not imported): 937

## Class balance per repo

| repo | labeled | breakages | rate |
|---|---|---|---|
| aio-libs/aiohttp | 157 | 4 | 0.025 |
| aio-libs/aiosignal | 119 | 28 | 0.235 |
| aio-libs/frozenlist | 88 | 14 | 0.159 |
| aio-libs/multidict | 30 | 5 | 0.167 |
| aio-libs/yarl | 52 | 13 | 0.25 |
| esphome/esphome | 243 | 17 | 0.07 |
| langchain-ai/langchain | 98 | 0 | 0.0 |
| numpy/numpy | 64 | 21 | 0.328 |
| paperless-ngx/paperless-ngx | 64 | 4 | 0.062 |
| pytest-dev/pytest | 45 | 0 | 0.0 |
| pytest-dev/pytest-asyncio | 214 | 16 | 0.075 |
| saleor/saleor | 116 | 6 | 0.052 |
| streamlit/streamlit | 24 | 1 | 0.042 |

## Column groups
- ID: repo, pr_number, package_norm, created_at
- label: label
- meta (outcome description, NOT features): fail_confidence
- features: bump_type, major_delta, minor_delta, patch_delta, is_prerelease, is_zero_major, is_range_update, blast_direct, blast_direct_src, blast_direct_tests, blast_transitive, depth_min, depth_mean, not_in_graph, depth_missing, snapshot_missing, hist_rate, hist_n, hist_k, hist_global_rate, changelog_scraped, changelog_found, changelog_chars, changelog_lines, has_breaking_keyword
- excluded outcome/leakage columns (never features): ci_status, ci_completed_at, n_workflow_runs, failed_workflows, flaky_workflows, fail_confidence, first_commit_sha, n_commits, has_human_commits, state, merged, closed_at, merged_at, exclusion_reason, label
