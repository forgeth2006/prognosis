"""Changelog scraper v0 (PRognosis).

For each (package, old_version, new_version) bump, find the changelog text
between the two versions and turn it into simple numeric features.

Put this file at scraping/changelog/changelog_scraper.py and run it from the
repo root:
    python scraping/changelog/changelog_scraper.py                       (built-in test list)
    python scraping/changelog/changelog_scraper.py data/pr_bumps_for_changelog.csv
    python scraping/changelog/changelog_scraper.py data/pr_bumps_for_changelog.csv --limit 20
    python scraping/changelog/changelog_scraper.py data/labeled_prs_v2.csv --labeled-only
The CSV needs package, old version and new version columns; common names are detected.
"""
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "scraping" / "changelog" / "cache"
OUT = ROOT / "data" / "changelog_features.csv"
HEADERS = {"User-Agent": "PRognosis-student-project (academic use)"}
DELAY = 1.0  # seconds between uncached requests
FILE_NAMES = ["CHANGELOG.md", "CHANGELOG.rst", "CHANGES.md", "CHANGES.rst",
              "HISTORY.md", "HISTORY.rst", "NEWS.md", "NEWS.rst",
              "CHANGELOG", "CHANGES", "HISTORY", "NEWS", "CHANGELOG.txt", "CHANGES.txt",
              "docs/changelog.rst", "docs/changelog.md", "docs/changes.rst", "doc/changelog.rst"]
BREAKING = re.compile(r"breaking|removed|deprecat", re.I)

# Replace with B's real bump table once it exists.
TESTS = [("requests", "2.31.0", "2.32.0"),
         ("flask", "2.3.0", "3.0.0"),
         ("pandas", "2.0.0", "2.1.0")]


# ---------- fetching (cached + polite) ----------
def cached_get(url, as_json=False):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (hashlib.md5(url.encode()).hexdigest() + ".json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["body"]
    time.sleep(DELAY)
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
    except requests.RequestException:
        return None  # transient error: do not cache
    body = None
    if r.status_code == 200:
        try:
            body = r.json() if as_json else r.text
        except ValueError:
            body = None
    path.write_text(json.dumps({"url": url, "body": body}), encoding="utf-8")
    return body


def html_to_text(html):
    return BeautifulSoup(html, "lxml").get_text("\n")


# ---------- URL helpers ----------
def github_repo(urls):
    for u in urls:
        m = re.search(r"github\.com/([\w.-]+)/([\w.-]+)", u or "")
        if m:
            return m.group(1), re.sub(r"\.git$", "", m.group(2))
    return None


def to_raw(url):
    """github.com/o/r/blob/branch/path -> raw.githubusercontent.com/o/r/branch/path"""
    m = re.match(r"https?://github\.com/([\w.-]+)/([\w.-]+)/blob/(.+)", url or "")
    if m:
        return f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}/{m.group(3)}"
    return None


def candidate_texts(meta):
    """Yield (text, source_type) from most to least reliable source."""
    urls = meta["info"].get("project_urls") or {}
    log_urls = [u for k, u in urls.items()
                if re.search(r"change|history|release|news", k, re.I)]
    for u in log_urls:
        raw = to_raw(u)
        if raw:
            t = cached_get(raw)
            if t:
                yield t, "project_urls_raw"
    repo = github_repo(list(urls.values()) + [meta["info"].get("home_page")])
    if repo:
        for name in FILE_NAMES:
            t = cached_get(f"https://raw.githubusercontent.com/{repo[0]}/{repo[1]}/HEAD/{name}")
            if t:
                yield t, "repo_raw"
    for u in log_urls:
        if not to_raw(u):
            html = cached_get(u)
            if html:
                yield html_to_text(html), "docs_page"


# ---------- extraction ----------
def _is_heading(lines, i):
    s = lines[i].strip()
    if not s:
        return False
    if s.startswith(("#", "[", "v", "V")) or s[0].isdigit():
        return True
    return i + 1 < len(lines) and re.fullmatch(r"[=\-~^]{3,}", lines[i + 1].strip()) is not None


def _find_all(lines, version):
    pat = re.compile(rf"(?<![\d.]){re.escape(version)}(?!\d|\.\d)")
    return [i for i, line in enumerate(lines) if pat.search(line) and _is_heading(lines, i)]


def _find(lines, version):
    hits = _find_all(lines, version)
    return hits[0] if hits else None


def extract(text, old_v, new_v):
    """Return the changelog entries after old_v up to and including new_v."""
    lines = text.splitlines()
    news, olds = _find_all(lines, new_v), _find_all(lines, old_v)
    # Newest-first (most common): use the LAST new-version heading that has an old-version
    # heading after it. Docs pages often list versions in a menu first, so this skips the menu.
    for i_new in reversed(news):
        later = [o for o in olds if o > i_new]
        if later:
            return "\n".join(lines[i_new:later[0]])
    # Oldest-first: from just after the old heading to the next heading after the new one
    for i_old in reversed(olds):
        later = [n for n in news if n > i_old]
        if later:
            i_new = later[0]
            end = len(lines)
            for j in range(i_new + 1, len(lines)):
                if _is_heading(lines, j) and re.match(r"[#\[vV\d]", lines[j].strip()):
                    end = j
                    break
            return "\n".join(lines[i_old + 1:end])
    return None


def looks_like_notes(section):
    """Reject menu fragments from docs pages: real notes have several non-empty lines."""
    non_empty = [ln for ln in section.splitlines() if ln.strip()]
    return len(non_empty) >= 3 and len(section) >= 80


def features(section):
    if section is None:
        return {"changelog_found": False, "changelog_chars": None,
                "changelog_lines": None, "has_breaking_keyword": None}
    return {"changelog_found": True, "changelog_chars": len(section),
            "changelog_lines": section.count("\n") + 1,
            "has_breaking_keyword": bool(BREAKING.search(section))}


# ---------- main ----------
def process(pkg, old_v, new_v):
    row = {"package": pkg, "old_version": old_v, "new_version": new_v,
           "source_type": "none", "new_release_date": None}
    meta = cached_get(f"https://pypi.org/pypi/{pkg}/json", as_json=True)
    if meta is None:
        row["source_type"] = "no_pypi"
        return {**row, **features(None)}
    rel = meta.get("releases", {}).get(new_v) or []
    row["new_release_date"] = rel[0]["upload_time"] if rel else None
    for text, source in candidate_texts(meta):
        section = extract(text, old_v, new_v)
        if section and (source != "docs_page" or looks_like_notes(section)):
            row["source_type"] = source
            return {**row, **features(section)}
    return {**row, **features(None)}


def load_pairs(path, labeled_only=False):
    df = pd.read_csv(path, dtype=str)
    low = {c.lower(): c for c in df.columns}
    if labeled_only:  # keep only PRs that have a label (skips excluded rows and GitHub Actions bumps)
        if "label" not in low:
            sys.exit("--labeled-only needs a 'label' column.")
        df = df[df[low["label"]].notna()]

    def pick(*names):
        return next((low[n] for n in names if n in low), None)

    pkg = pick("package_norm", "package", "package_name", "dependency", "name")
    old = pick("eff_old_version", "old_version", "from_version", "version_from", "old")
    new = pick("eff_new_version", "new_version", "to_version", "version_to", "new")
    if not (pkg and old and new):
        sys.exit("Could not find package / old version / new version columns.\n"
                 f"Columns found: {list(df.columns)}")
    pairs = df[[pkg, old, new]].dropna().drop_duplicates()
    return pairs.values.tolist(), (pkg, old, new)


def run_csv(path, limit=None, labeled_only=False):
    pairs, (kp, ko, kn) = load_pairs(path, labeled_only)
    if limit:
        pairs = pairs[:limit]
    print(f"{len(pairs)} unique (package, old, new) pairs", flush=True)
    rows = []
    for i, (p, o, n) in enumerate(pairs, 1):
        try:
            r = process(p, o, n)
        except Exception as e:  # one bad row must not stop the whole run
            r = {"source_type": f"error: {type(e).__name__}", "new_release_date": None,
                 **features(None)}
        extra = {k: v for k, v in r.items() if k not in ("package", "old_version", "new_version")}
        rows.append({kp: p, ko: o, kn: n, **extra})
        if i % 25 == 0:
            print(f"  {i}/{len(pairs)} done", flush=True)
    df = pd.DataFrame(rows)
    out = ROOT / "data" / "changelog_features_v1.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"\ncoverage: {df['changelog_found'].mean():.0%} of {len(df)} pairs -> saved to {out}")
    print(df["source_type"].value_counts().to_string())


if __name__ == "__main__":
    argv = sys.argv[1:]
    labeled_only = "--labeled-only" in argv
    argv = [a for a in argv if a != "--labeled-only"]
    limit = None
    if "--limit" in argv:
        i = argv.index("--limit")
        limit = int(argv[i + 1])
        del argv[i:i + 2]
    if argv:
        run_csv(argv[0], limit, labeled_only)
    else:
        rows = [process(*t) for t in TESTS]
        df = pd.DataFrame(rows)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(OUT, index=False)
        print(df.to_string(index=False))
        print(f"\ncoverage: {df['changelog_found'].mean():.0%}  -> saved to {OUT}")