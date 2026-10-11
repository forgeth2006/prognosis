"""List the PyPI project links for every package the scraper missed (reads the local cache).

Save as scraping/changelog/diagnose_misses.py and run from the repo root:
    python scraping/changelog/diagnose_misses.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import changelog_scraper as c

df = pd.read_csv(c.OUT)
for pkg in df.loc[df["source_type"] == "none", "package"].unique():
    meta = c.cached_get(f"https://pypi.org/pypi/{pkg}/json", as_json=True)
    print(f"\n== {pkg}")
    if not meta:
        print("  no PyPI metadata")
        continue
    for key, url in (meta["info"].get("project_urls") or {}).items():
        print(f"  {key}: {url}")