"""Repo shortlist checker (PRognosis).

Checks candidate repos against the project criteria and writes a CSV:
  1. .github/dependabot.yml updates pip (or uv) packages
  2. at least 100 single-package bump PRs from Dependabot (estimated from a sample)
  3. a GitHub Actions workflow that runs on pull requests and runs tests
  4. a Dependabot PR in the last 180 days (the repo is still active)

Save as scraping/repo_check.py and run from the repo root:
    python scraping/repo_check.py
Add your own candidates, one 'owner/name' per line, in scraping/repos.txt (optional).
If GitHub says you hit a rate limit, wait an hour and run it again.
"""
import csv
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "repo_shortlist_candidates.csv"
EXTRA = Path(__file__).resolve().parent / "repos.txt"
UA = "PRognosis-student-project (academic use)"
SEARCH_DELAY = 7  # GitHub allows 10 search requests per minute without a token
MIN_BUMPS = 100
MAX_AGE_DAYS = 180

SEED = [
    "aio-libs/aiohttp", "home-assistant/core", "apache/airflow", "pallets/flask",
    "django/django", "psf/black", "pytest-dev/pytest", "fastapi/fastapi",
    "pydantic/pydantic", "huggingface/transformers", "scikit-learn/scikit-learn",
    "pandas-dev/pandas", "numpy/numpy", "matplotlib/matplotlib", "python-poetry/poetry",
    "encode/httpx", "encode/django-rest-framework", "celery/celery",
    "sqlalchemy/sqlalchemy", "ansible/ansible", "getsentry/sentry", "mitmproxy/mitmproxy",
    "streamlit/streamlit", "ray-project/ray", "scrapy/scrapy", "pypa/pip",
    "python-pillow/Pillow", "urllib3/urllib3", "certbot/certbot", "freqtrade/freqtrade",
    "langchain-ai/langchain", "Textualize/rich", "Textualize/textual", "tqdm/tqdm",
    "pallets/click", "python-attrs/attrs", "mkdocs/mkdocs", "ipython/ipython",
    "tornadoweb/tornado", "apache/superset", "pyca/cryptography", "sphinx-doc/sphinx",
    "pre-commit/pre-commit", "wagtail/wagtail", "saleor/saleor", "zulip/zulip",
    "OpenBB-finance/OpenBB", "ultralytics/ultralytics",
]

# Python package names never contain "/", while GitHub Actions and pre-commit hooks do
# (e.g. actions/checkout), so excluding "/" keeps Actions bumps out of the count.
BUMP = re.compile(r"[Bb]ump [^\s/]+ from \S+ to \S+|[Uu]pdate [^\s/]+ requirement from \S+ to \S+")
TESTS = re.compile(r"\b(pytest|tox|nox|unittest|nosetests)\b|make (ci|test)\b|coverage run", re.I)


def http_get(url, params=None, as_json=False, auth=False):
    headers = {"User-Agent": UA}
    if auth:
        headers["Accept"] = "application/vnd.github+json"
        if os.environ.get("GITHUB_TOKEN"):
            headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    try:
        r = requests.get(url, headers=headers, params=params, timeout=25)
    except requests.RequestException as e:
        return None, f"network error ({type(e).__name__})"
    if r.status_code in (403, 429) and "rate limit" in r.text.lower():
        return None, "rate limited"
    if r.status_code != 200:
        return None, f"http {r.status_code}"
    try:
        return (r.json() if as_json else r.text), None
    except ValueError:
        return None, "bad response"


def ecosystems(yml_text):
    return re.findall(r"package-ecosystem:\s*[\"']?([\w-]+)", yml_text)


def is_real_ci(workflow_text):
    return "pull_request" in workflow_text and bool(TESTS.search(workflow_text))


def check_repo(repo):
    row = {"repo": repo, "ecosystems": "", "dependabot_prs": "", "est_single_bumps": "",
           "last_dependabot_pr": "", "real_ci": "", "verdict": "FAIL", "reason": ""}
    raw = f"https://raw.githubusercontent.com/{repo}/HEAD/.github"

    # 1. Dependabot config with pip/uv
    text = None
    for name in ("dependabot.yml", "dependabot.yaml"):
        text, _ = http_get(f"{raw}/{name}")
        if text:
            break
    if not text:
        row["reason"] = "no dependabot.yml (or repo not found)"
        return row
    eco = ecosystems(text)
    row["ecosystems"] = " ".join(sorted(set(eco)))
    if not {"pip", "uv"} & set(eco):
        row["reason"] = "Dependabot does not update pip/uv packages"
        return row

    # 2. Dependabot PR volume and recency
    time.sleep(SEARCH_DELAY)
    data, err = http_get("https://api.github.com/search/issues", as_json=True, auth=True,
                         params={"q": f"repo:{repo} is:pr author:app/dependabot",
                                 "per_page": 100, "sort": "created", "order": "desc"})
    if err:
        row["verdict"], row["reason"] = "UNSURE", f"PR search failed: {err}"
        return row
    total, items = data.get("total_count", 0), data.get("items", [])
    share = sum(bool(BUMP.search(i["title"])) for i in items) / len(items) if items else 0
    est = round(total * share)
    row.update(dependabot_prs=total, est_single_bumps=est,
               last_dependabot_pr=items[0]["created_at"][:10] if items else "")
    if est < MIN_BUMPS:
        row["reason"] = f"only about {est} single-package bump PRs"
        return row
    newest = datetime.fromisoformat(items[0]["created_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) - newest > timedelta(days=MAX_AGE_DAYS):
        row["reason"] = "no Dependabot PR in the last 180 days"
        return row

    # 3. Workflow that runs tests on pull requests
    files, err = http_get(f"https://api.github.com/repos/{repo}/contents/.github/workflows",
                          as_json=True, auth=True)
    if err:
        row["verdict"], row["reason"] = "UNSURE", f"workflow listing failed: {err}"
        return row
    names = [f["name"] for f in files if f["name"].endswith((".yml", ".yaml"))][:12]
    row["real_ci"] = any(is_real_ci(http_get(f"{raw}/workflows/{n}")[0] or "") for n in names)
    if not row["real_ci"]:
        row["reason"] = "no workflow runs tests on pull requests"
        return row

    row["verdict"], row["reason"] = "PASS", "meets all four criteria (estimate)"
    return row


def main():
    repos = list(SEED)
    if EXTRA.exists():
        repos += [ln.strip() for ln in EXTRA.read_text().splitlines()
                  if ln.strip() and not ln.startswith("#")]
    repos = list(dict.fromkeys(repos))
    rows = []
    for repo in repos:
        row = check_repo(repo)
        rows.append(row)
        print(f"{row['verdict']:<6} {repo:<34} {row['reason']}", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    passed = [r["repo"] for r in rows if r["verdict"] == "PASS"]
    print(f"\n{len(passed)} of {len(rows)} repos passed. Saved to {OUT}")
    print("Passed:", ", ".join(passed) if passed else "none")


if __name__ == "__main__":
    main()