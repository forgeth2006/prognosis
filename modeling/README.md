# modeling/ (Person C)

## Status
Draft stage. Waiting on B's 3-repo validation to know the real breakage rate.

## Temporal split
`temporal_split.py` loads `data/labeled_prs_v0.csv`, keeps labeled rows, left-joins
`data/graph_prototype_v0.csv` on `repo` + `package`, and splits by `created_at`
(oldest 80% train, newest 20% test). It asserts train and test do not overlap in time.

## Decisions
- PRs with no graph row: blast radius 0 plus a `not_in_graph` flag.
- Depth NaN for test-only packages: [pending B's answer].
- Outcome columns (ci_status, n_workflow_runs, failed_workflows, flaky_workflows,
  fail_confidence) are excluded from features to avoid leakage.

## Open items for Checkpoint 2
- Class balance (label=1 share) once B's validation arrives.
- Historical breakage rate feature must use only earlier bumps (point-in-time).
- Graph features are a snapshot of the repo today, not at each PR's date.