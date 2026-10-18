# graph_features/ (Person B)

| Script | What it does |
|---|---|
| `import_graph.py` | static `ast` import graph of one checkout; blast radius + depth per package (Week 4 prototype, now also `package_norm`) |
| `snapshots.py` | the same graph for every repo-month, read from git history: a PR only sees code from before its month began (no future leakage) |
| `historical_rate.py` | point-in-time, smoothed breakage rate per package (expanding window, strictly earlier CI verdicts only) |
| `build_feature_table.py` | joins labels + bump + graph + historical rate + changelog features and runs the Checkpoint 2 checks |

## Run order (from the repo root, after the scrape and `clean_dataset.py`)
```bash
python graph_features/snapshots.py --labels data/labeled_prs_v1.csv
python graph_features/build_feature_table.py
python -m unittest discover -s graph_features/tests
```
Outputs: `data/graph_snapshots_v1.csv`, `data/graph_snapshots_index_v1.csv`, `data/feature_table_v1.csv`, `data/dataset_checks_v1.md`.

## Feature meanings and nulls
- `blast_direct*`: files importing the package; `blast_transitive`: files that can reach it through internal imports.
- `depth_min/mean`: internal-import hops from an entry point; **blank on purpose** when only test files import the package
  or nothing imports it (`depth_missing = 1`). Impute in the modeling pipeline, fitted on train only.
- `not_in_graph = 1`: the package is never imported in that snapshot (dev tool, plugin, transitive pin); blast radius is 0.
- `snapshot_missing = 1`: the repo had no commit before the PR's month; blast radius is 0.
- `changelog_scraped = 0`: Person A's scraper has not covered this bump yet (not the same as "no changelog found").
- Never use as features: `ci_status`, `ci_completed_at`, `n_workflow_runs`, `failed_workflows`, `flaky_workflows`,
  `fail_confidence`, `first_commit_sha`, `n_commits`, `has_human_commits`, `state`, `merged`, `closed_at`, `merged_at`.

## Limitations
Static imports only (`importlib`/`__import__` not followed); import-name to package-name uses a small alias table;
snapshots are monthly (start of the PR's month), not per-PR commit.
