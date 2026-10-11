# CI-failure label rule — v0 (draft for B + C to agree before the full scrape)

Implemented in `scraping/label_ci.py`. Every choice below is a constant or a branch in that file.

## Unit and label
One row per **closed Dependabot PR** (merged or not). `label = 1` means the bump made CI fail;
`label = 0` means CI passed; blank means the PR is **excluded** (see `exclusion_reason`).

## Which commit
CI is read from the PR's **first commit** (Dependabot's own commit), not the final head, so a
failure that a maintainer later fixed by pushing extra commits is still a breakage.
`has_human_commits` records whether such a fix happened (useful signal for later).

## Which CI
GitHub Actions workflow runs on that commit with event `pull_request` / `pull_request_target`.
Workflows whose name matches `IGNORE_WORKFLOW` (labelers, codecov, CLA, stale, release/publish,
dependabot auto-merge, previews) are ignored. Cancelled, skipped, neutral and unfinished runs carry no information.

## Re-runs (flaky handling)
- Any remaining workflow failed, `run_attempt == 1`  → **label 1**, `fail_confidence = single_attempt`
- Any remaining workflow failed, `run_attempt > 1`   → **label 1**, `fail_confidence = confirmed` (failed again after a re-run)
- No failure, but a workflow passed only on a re-run (`run_attempt > 1`) → **excluded** `flaky_rerun_passed`
- All passed on the first attempt → **label 0**
- No usable run → **excluded** `no_ci_result`

## Exclusions (decided without any CI lookup)
| reason | why |
|---|---|
| `grouped_bump` | several packages in one PR; cannot attribute the failure |
| `range_update` | "Update X requirement from A to B" changes a version range, not an installed version |
| `non_pip_or_non_manifest:<eco>` | GitHub Actions / Docker / npm / etc. PRs, or PRs touching files other than Python dependency manifests |
| `touches_ci_config` | PR also changed CI config files |
| `unparseable_title`, `bad_version_delta:*` | no usable package / version pair, or a downgrade |
| `first_commit_not_dependabot` | the first commit is human-authored |

## Known noise (document in the report)
- A one-off failure with no re-run may still be flaky: `single_attempt` rows are noisier than `confirmed`.
  Report both, and run a sensitivity check training on `confirmed` only.
- A bump can fail because `main` was already red. Not detected in v0; candidate refinement for Week 5
  (compare against the base branch's latest run).
- Repos not using GitHub Actions for tests get `no_ci_result` (all 18 shortlisted repos use Actions).
