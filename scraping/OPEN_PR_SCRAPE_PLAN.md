# Open-PR scrape: ON HOLD until after the final freeze (Esther, Checkpoint 3)

Do **not** run this before Esther confirms the final freeze. It would add rows and change the frozen dataset.

Why: the frozen scrape is closed-only, so failures still open are missing (40% of breakages stayed open 7+ days; see `report/data_issues_found_in_modeling.md`).

Plan, to run only on approval, into separate files (never over `data/*_v2.csv`):
1. `python scraping/scrape_prs.py --state open --out data/prs_open_v3.csv ...` (same repos and flags as the original scrape)
2. Label with `label_ci.py`; clean with `clean_dataset.py`; build features with `graph_features/build_feature_table.py` into `*_v3` files.
3. Report: how many open PRs, how many breakages among them, and the breakage rate by chunk with and without them. Only then discuss whether v3 replaces v2.
