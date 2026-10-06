# Contributing — Branching & Merge Discipline

## Branches

One long-lived branch per person, named by role:

- `person-a` — repo/pipeline-deployment work
- `person-b` — scraping, labeling, graph, features
- `person-c` — modeling, pipeline, dashboard

Work on your own branch. Commit as often as you like — there's no requirement to keep commits clean before a checkpoint.

## Merging into `main`

**Merges happen only at the 5 project checkpoints, not continuously.** At 6 hrs/week each, constant merge conflicts waste scarce time, so batching merges to checkpoints is deliberate.

| Checkpoint | Week | What merges |
|---|---|---|
| 1 — Smoke test | 4 | Early scraped data + early graph prototype |
| 2 — Dataset freeze | 8 | Cleaned labeled data + feature table → one model-ready file |
| 3 — Modeling freeze | 12 | Final trained model + evaluation metrics |
| 4 — Pipeline integration | 14 | Batch pipeline, run live end-to-end |
| 5 — Final review | 16 | Full report + working system |

**Person A executes every checkpoint merge and resolves conflicts.** Before each checkpoint:
1. Whoever owns the branch being merged writes a short summary (2–3 lines) of what changed — not a formal PR description.
2. At least one other team member does a quick sanity-check run before it merges into `main`.
3. Person A merges, tags the commit (e.g. `checkpoint-2-dataset-freeze`), and resolves any conflicts.

## Checkpoint 2 (Week 8) is the one to get right

This is the most important merge in the project. Before merging:
- Row counts match between the labeled data and the feature table — no silent data loss
- Class balance (positive vs. negative examples) is explicitly reported — this is the trigger point for the data-scarcity contingency plan if numbers are too low
- No missing/null features that would silently bias the model

## Checkpoint 3 (Week 12)

- Metrics reported are precision/recall/PR-AUC, never plain accuracy
- Calibration curve is included
- Temporal split is verified — no test-set PR predates a training-set PR
