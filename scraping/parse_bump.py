"""Parsing helpers for Dependabot bump PRs (PRognosis).

Pure functions, no network: PR title -> package / old / new version,
version delta classification, changed-file classification, and link extraction
from the PR body.
"""
import re

# ---- titles -------------------------------------------------------------------
GROUPED = re.compile(
    r"\bbump the .+ group|\bacross \d+ director|\bwith \d+ updates?\b"
    r"|\bbump\s+\S+(?:,\s*\S+)*\s+and\s+\S+",
    re.I,
)
SINGLE = re.compile(r"\bbump\s+(?P<pkg>\S+)\s+from\s+(?P<old>\S+)\s+to\s+(?P<new>\S+)", re.I)
RANGE = re.compile(r"\bupdate\s+(?P<pkg>\S+)\s+requirement\s+from\s+(?P<old>\S+)\s+to\s+(?P<new>\S+)", re.I)


def parse_title(title):
    """Return dict(package, old_version, new_version, is_grouped, is_range_update, title_parsed)."""
    out = {"package": "", "package_norm": "", "old_version": "", "new_version": "",
           "is_grouped": False, "is_range_update": False, "title_parsed": False}
    title = title or ""
    if GROUPED.search(title) and not SINGLE.search(title):
        out["is_grouped"] = True
        return out
    m = SINGLE.search(title)
    if m:
        out["is_range_update"] = False
    else:
        m = RANGE.search(title)
        if m:
            out["is_range_update"] = True
    if not m:
        return out
    out["package"] = m["pkg"].strip("`'\"")
    out["package_norm"] = normalize_name(out["package"])
    out["old_version"] = m["old"].strip("`'\"")
    out["new_version"] = m["new"].strip("`'\".")
    out["title_parsed"] = True
    return out


def normalize_name(name):
    """PEP 503 normalisation: lower-case, runs of - _ . become a single '-'."""
    return re.sub(r"[-_.]+", "-", name).lower()


# ---- versions -----------------------------------------------------------------
_REL = re.compile(r"^v?(\d+(?:\.\d+)*)(.*)$")
_PRE = re.compile(r"(a|b|rc|c|alpha|beta|pre|preview|dev)\.?\d*", re.I)


def _release(ver):
    m = _REL.match(ver.strip())
    if not m:
        return None, ""
    return [int(x) for x in m.group(1).split(".")], m.group(2)


def version_delta(old, new):
    """Classify the jump between two version strings.

    bump_type: major | minor | patch | other | downgrade | unknown
    Also flags pre-releases and 0.x versions (where minors are conventionally breaking).
    """
    o, orest = _release(old)
    n, nrest = _release(new)
    out = {"bump_type": "unknown", "is_prerelease": False, "is_zero_major": False,
           "major_delta": "", "minor_delta": "", "patch_delta": ""}
    if o is None or n is None:
        return out
    out["is_prerelease"] = bool(_PRE.match(nrest.lstrip("-_.+"))) or bool(_PRE.match(orest.lstrip("-_.+")))
    pad = lambda v: (v + [0, 0, 0])[:3] + v[3:]
    op, np_ = pad(o), pad(n)
    out["is_zero_major"] = op[0] == 0
    out["major_delta"], out["minor_delta"], out["patch_delta"] = (np_[0] - op[0], np_[1] - op[1], np_[2] - op[2])
    if np_ < op:
        out["bump_type"] = "downgrade"
    elif np_[0] != op[0]:
        out["bump_type"] = "major"
    elif np_[1] != op[1]:
        out["bump_type"] = "minor"
    elif np_[2] != op[2]:
        out["bump_type"] = "patch"
    else:
        out["bump_type"] = "other"
    return out


# ---- changed files ------------------------------------------------------------
MANIFEST = re.compile(
    r"(^|/)(requirements[^/]*\.(txt|in)|constraints[^/]*\.txt|pyproject\.toml|uv\.lock|poetry\.lock"
    r"|pdm\.lock|Pipfile(\.lock)?|setup\.(py|cfg)|pylock[^/]*\.toml)$"
    r"|(^|/)(requirements|constraints|deps|dependencies)/[^/]+\.(txt|in)$"
)
CI_CONFIG = re.compile(r"^\.github/|(^|/)(\.gitlab-ci\.yml|\.travis\.yml|tox\.ini|noxfile\.py|\.pre-commit-config\.yaml|azure-pipelines\.yml)$")


def classify_files(paths):
    """Return dict(ecosystem, n_files, n_non_dependency_files, touches_ci_config).

    ecosystem is 'pip' only when every changed file is a Python dependency manifest/lock file.
    """
    paths = list(paths)
    non_dep = [p for p in paths if not MANIFEST.search(p)]
    if paths and not non_dep:
        eco = "pip"
    elif paths and all(p.startswith(".github/workflows/") or p.endswith("action.yml") for p in paths):
        eco = "github-actions"
    elif paths and all(re.search(r"(^|/)(Dockerfile[^/]*|docker-compose[^/]*\.ya?ml)$", p) for p in paths):
        eco = "docker"
    elif paths and all(re.search(r"(^|/)(package(-lock)?\.json|yarn\.lock|pnpm-lock\.yaml)$", p) for p in paths):
        eco = "npm"
    elif paths and all(re.search(r"(^|/)(Cargo\.(toml|lock))$", p) for p in paths):
        eco = "cargo"
    elif paths and all(p.endswith(".pre-commit-config.yaml") for p in paths):
        eco = "pre-commit"
    else:
        eco = "other" if paths else "unknown"
    return {"ecosystem": eco, "n_files": len(paths), "n_non_dependency_files": len(non_dep),
            "touches_ci_config": any(CI_CONFIG.search(p) for p in paths)}


# ---- PR body links ------------------------------------------------------------
_A = re.compile(r'<a\s+href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
_MD = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")


def extract_links(body):
    """Pull the changelog / release-notes / compare / source-repo links Dependabot puts in the PR body."""
    body = body or ""
    links = [(text, url) for url, text in _A.findall(body)] + [(t, u) for t, u in _MD.findall(body)]
    out = {"changelog_url": "", "release_notes_url": "", "compare_url": "", "source_repo_url": ""}
    for text, url in links:
        t = text.lower()
        if not out["changelog_url"] and "changelog" in t:
            out["changelog_url"] = url
        elif not out["release_notes_url"] and ("release" in t and "compare" not in url):
            out["release_notes_url"] = url
        if not out["compare_url"] and "/compare/" in url:
            out["compare_url"] = url
    m = re.search(r"Bumps\s+\[[^\]]+\]\((https?://[^)\s]+)\)", body) or re.search(
        r"Updates\s+the\s+requirements\s+on\s+\[[^\]]+\]\((https?://[^)\s]+)\)", body)
    if m:
        out["source_repo_url"] = m.group(1)
    return out
