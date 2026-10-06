# PRognosis

**Predicting whether a dependency-version-bump pull request will break CI — before it's merged.**

PRognosis scores Dependabot/Renovate bump PRs with a calibrated breakage-risk probability, using features from the bump itself (version-jump size, changelog size) and from a self-built package-dependency graph (blast radius, depth, historical breakage rate). It's a self-scraped dataset and a self-trained statistical model (logistic regression, compared against gradient boosting as a sufficiency check), with class-imbalance handling, calibration, and a temporal train/test split — shipped as a working batch-scoring pipeline with a dashboard, not just a notebook.

## Repo structure

```
/scraping/        Person B — GitHub API scraping, PR/CI metadata, label extraction
/graph_features/  Person B — dependency-graph construction, blast radius, depth, historical rate
/modeling/         Person C — baseline, logistic regression, calibration, sufficiency test, temporal validation
/pipeline/         Person C (build) + Person A (deployment) — batch scoring pipeline, dashboard
/data/              Frozen datasets, versioned by date
/report/            Final write-up
```

## Team

| Person | Role |
|---|---|
| A | Repo setup, merge-conflict resolution at checkpoints, project monitoring, deployment (scheduler/hosting) from Week 13 |
| B | Data scraping/labeling + dependency-graph/feature engineering |
| C | Modeling + product pipeline; assists B on data/features in Weeks 2–7 |

## Workflow

- One branch per person, merged into `main` only at the 5 project checkpoints (Week 4, 8, 12, 14, 16) — see `CONTRIBUTING.md`.
- Dataset freeze (Week 8) and modeling freeze (Week 12) are the two checkpoints that matter most — everything downstream depends on them.

## Getting started

```bash
git clone <repo-url>
cd prognosis
pip install -r requirements.txt
git checkout -b person-b   # or person-a / person-c
```

See `CONTRIBUTING.md` for the full branching and merge-checkpoint convention.
