"""Print the changelog text the scraper extracted for one bump, using the local cache.

Save as scraping/changelog/check_extract.py and run from the repo root:
    python scraping/changelog/check_extract.py requests 2.31.0 2.32.0
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import changelog_scraper as c

pkg, old_v, new_v = sys.argv[1:4]
meta = c.cached_get(f"https://pypi.org/pypi/{pkg}/json", as_json=True)
if meta is None:
    sys.exit("No PyPI metadata (not cached and not reachable right now).")

for text, source in c.candidate_texts(meta):
    section = c.extract(text, old_v, new_v)
    if section:
        print(f"source: {source}\n{'-' * 40}\n{section}")
        break
else:
    print("No changelog section found for this bump.")