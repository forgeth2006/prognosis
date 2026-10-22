# scraping/ (Person B)

Run from the repo root. `export GITHUB_TOKEN=<your personal access token>` first (never commit it).

| Step | Command | Output |
|---|---|---|
| 1. Raw PR metadata (Weeks 2-3) | `python scraping/scrape_prs.py --max-prs 300` | `data/pr_metadata_raw.csv` |
| 2. CI labels (Week 4) | `python scraping/label_ci.py --include-range-updates` | `data/labeled_prs_v0.csv` + `_summary.csv` |
| 2b. Cleaning (Week 5) | `python scraping/clean_dataset.py` | `data/labeled_prs_v1.csv` + `_report.csv` |
| 3. Hand-off to Person A | `python scraping/export_for_changelog.py` | `data/pr_bumps_for_changelog.csv` |
| Tests | `python -m unittest discover -s scraping/tests` | |

Both scrapers resume where they stopped (append-only CSV + HTTP cache in `scraping/.cache/`).
Label rule: `LABEL_RULES.md`. Repo list: `shortlist_repos.txt` (Person A's 18 repos).

## Scraping open or all PRs (`--state`)
The frozen dataset is **closed PRs only**, which under-counts slow-to-close failures (see `report/data_issues_found_in_modeling.md`).
`python scraping/scrape_prs.py --state open --out data/prs_open_v2.csv ...` collects open PRs. Always use a separate `--out`;
do not overwrite the frozen files, and tell Esther before any data change.
