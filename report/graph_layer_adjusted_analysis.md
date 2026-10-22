# Graph layer, adjusted analysis (addendum to graph_layer_section.md)

This addendum tests whether the descriptive bars in `graph_layer_section.md` survive adjustment for repo, bump type, package clustering and shared-cause failure weeks.

Data: frozen `data/feature_table_v2.csv`, 1,314 labeled Dependabot bump PRs from 13 repos, 129 breakages (9.8%).
Figures: `report/figures/eda/graph_layer_1_features.png`, `graph_layer_2_confounding.png`,
`graph_layer_3_adjusted_odds.png`; numbers behind every bar in `eda_graph_layer_summary.csv` and
`eda_graph_layer_effects.csv`. Code: `graph_features/eda_graph_layer.py` (read-only on `data/`).

## What the graph features are
For each PR, the repo's import graph is rebuilt as it was at the start of the PR's month (no future code).
Blast radius is the number of files that import the bumped package; depth is how many internal-import hops
separate those files from an entry point. A package that the repo's code never imports (a linter, a test
runner, a transitive pin) has blast radius 0 and no depth. That is 824 of the 1,314 PRs (63%); another 113
are imported only from tests. Only 377 PRs (29%) have a depth at all, and those contain just 26 breakages.

## What the plots show
1. **More connected packages did not break more often. If anything the opposite.** Breakage is 11.2% (92/824)
   for packages the repo does not import, 9.0% (14/155) for 1 importing file, 9.5% (12/126) for 2-3 files,
   5.6% (4/72) for 4-9 and 5.1% (7/137) for 10+ files. The intervals overlap heavily
   (e.g. 4-9 files: roughly 2% to 14%).
2. **Depth is too sparse to read.** Depth 0: 2.5% (4/160); depth 1: 11.7% (19/162); depth 2+: 5.5% (3/55). The
   depth-0 bar rests on 4 breakages. This is not evidence that shallow packages are safer.
3. **The ordinary bump features behave as expected.** Patch bumps break 5.4% (33/612), minor 12.4% (65/525),
   major 17.6% (27/153). Bumps whose changelog contains a breaking keyword break 14.5% (37/255) against 6.2%
   (36/585) when a changelog was found without one.
4. **The historical breakage rate is the strongest single signal.** The top fifth of `hist_rate` has 55
   breakages in 263 PRs (21%), the bottom fifth 14 in 263 (5%). It was built to capture exactly this, so it
   should be checked on the temporal test split, not here.

## Why the graph result should be held loosely
- **Few breakages.** 129 in total, so any bin with fewer than about 10 breakages can swing by several points.
  Each bar carries k/n and a 95% Wilson interval; read the interval, not the bar height.
- **A handful of tools carry the breakages.** Five packages (ruff, tox, coverage, pydantic-core, pre-commit) hold
  38% of all breakages, and nearly all are not imported by repo code. They fail CI because a linter or test tool
  changed behaviour, not because of import coupling. The "not imported" group is therefore a group of tools,
  not a group of unimportant packages.
- **Repos differ a lot.** Breakage ranges from 0% (langchain, pytest) to 33% (numpy), and repos also differ in how
  many packages are imported. Within repos the imported vs not-imported gap points the same way in some repos
  (numpy 1/22 vs 20/42, yarl 8/42 vs 5/10) about equal in esphome, and reversed in paperless-ngx (2/20 vs 2/44).
- **Adjusting removes the signal.** With repo (or repo x bump type) held fixed, every graph odds ratio stays below 1
  but every 95% interval includes 1 (repo-stratified: imported 0.56, 0.29-1.25; blast 2+ files 0.51, 0.24-1.13;
  used in library code 0.68, 0.34-1.40; depth 0, 0.40, 0.07-2.92). Intervals resample whole packages, because PRs of
  one package are not independent. The honest reading is: no detectable effect of blast radius or depth on
  breakage in this sample, and the sample is too small to rule out a modest one.
- **Some breakages are shared events.** 33 of the 129 breakages fall in 9 repo-weeks where at least half of that
  week's PRs failed together (e.g. aiosignal 2025-W46: 5 of 5). That pattern is typical of one broken base branch
  or one tool release hitting every open PR, not of 33 independent bump effects.
- **The labels are mostly single attempts.** 124 of 129 breakages failed once and were not re-run
  (`fail_confidence = single_attempt`); only 5 are `confirmed`. Some are flaky runs.

## Implications for modeling (for Person C)
- Keep the graph features, but expect them to add little beyond repo, bump type and `hist_rate`. If the model
  ignores them, that is a result worth reporting, not a bug.
- Use `bump_type` rather than `minor_delta` / `patch_delta`: the component deltas go negative when a higher
  level resets (all 305 rows with a negative patch delta are minor or major bumps), so their bars mix bump
  types. EDA bars for those two columns should not be read as effects.
- Run two sensitivity checks that need no change to the frozen data: (a) drop the 33 shared-event breakages,
  (b) train on `confirmed` only (too few, 5) or report results with and without `single_attempt` rows.
- Split cross-validation by time, and prefer grouped folds by package or repo so one tool's many PRs do not sit
  on both sides of a split.

## Limits of this analysis
Associations only. Odds ratios assume strata are fixed by repo and bump type; other differences (CI setup,
maintainer behaviour) remain. The graph is static-import only: packages loaded through `importlib` or plugins
count as not imported.
