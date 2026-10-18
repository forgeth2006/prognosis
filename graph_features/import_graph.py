"""Static import-graph prototype (PRognosis, Week 4).

Builds a file-level import graph of a Python repo with `ast` (static imports only; dynamic
imports via importlib/__import__ are a documented limitation) and computes, per third-party
package, the features the model will use:

    blast_direct       files that import the package directly
    blast_direct_src   ... of which are library/source files
    blast_direct_tests ... of which are test files
    blast_transitive   files that can reach the package through internal imports
                       (everything that would be affected if the package broke)
    depth_min/mean     internal-import hops from the nearest entry point (a source file that
                       nothing else in src imports, or a top-level package __init__) to
                       the files that import the package. Small = close to the core.

Graph: nodes are files and external packages; edge A -> B means "A imports B".

Usage (from repo root):
    python graph_features/import_graph.py path/to/checkout                # one local checkout
    python graph_features/import_graph.py --repos aio-libs/yarl Textualize/rich   # shallow-clones
Output: data/graph_prototype_v0.csv (one row per repo x package).

Prototype scope: graph of the repo at its current HEAD. Per-PR (point-in-time) graphs come in
Weeks 5-7.
"""
import argparse
import ast
import re
import subprocess
import sys
from collections import deque
from pathlib import Path

import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
CHECKOUTS = Path(__file__).resolve().parent / ".checkouts"
SKIP_DIRS = {".git", ".venv", "venv", "env", "node_modules", "build", "dist", "__pycache__", ".tox",
             ".nox", ".eggs", "site-packages", ".mypy_cache", ".pytest_cache", "_vendor", "vendored"}
SRC_ROOT_DIRS = {"src", "lib"}
# stdlib-like or shim names that are not real third-party dependencies
NOT_PACKAGES = {"__future__", "distutils", "_distutils_hack", "typing"}

# import name -> distribution name, where they differ (normalised names, see normalize_name)
IMPORT_TO_DIST = {
    "yaml": "pyyaml", "pil": "pillow", "cv2": "opencv-python", "sklearn": "scikit-learn",
    "skimage": "scikit-image", "bs4": "beautifulsoup4", "dateutil": "python-dateutil",
    "dotenv": "python-dotenv", "jwt": "pyjwt", "attr": "attrs", "attrs": "attrs",
    "openssl": "pyopenssl", "git": "gitpython", "serial": "pyserial", "magic": "python-magic",
    "jose": "python-jose", "zmq": "pyzmq", "usb": "pyusb", "crypto": "pycryptodome",
    "nacl": "pynacl", "ruamel": "ruamel-yaml", "pkg-resources": "setuptools", "pkg_resources": "setuptools",
    "grpc": "grpcio", "socks": "pysocks", "wx": "wxpython", "markdown": "markdown", "_pytest": "pytest",
    "pytest_asyncio": "pytest-asyncio", "psycopg2": "psycopg2", "mpl_toolkits": "matplotlib",
    "docutils": "docutils", "setuptools": "setuptools", "pkg_resources": "setuptools",
    "typing_extensions": "typing-extensions", "msgpack": "msgpack", "tomllib": None,
}


def normalize_name(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def dist_name(import_top):
    """Map a top-level import name to a normalised distribution name."""
    key = import_top.lower()
    return IMPORT_TO_DIST.get(key) or IMPORT_TO_DIST.get(import_top) or normalize_name(import_top)


def file_role(rel):
    parts = rel.parts
    name = parts[-1]
    if any(p in ("tests", "test", "testing") for p in parts[:-1]) or name.startswith("test_") \
            or name.endswith("_test.py") or name == "conftest.py":
        return "test"
    if any(p in ("docs", "doc") for p in parts[:-1]):
        return "docs"
    return "src"


def _module_names(rel):
    """Dotted module names a file can be imported as (repo-root and src/ layouts)."""
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return []
    names = [".".join(parts)]
    if parts[0] in SRC_ROOT_DIRS and len(parts) > 1:
        names.append(".".join(parts[1:]))
    return names


def _package_of(rel):
    """Dotted package a file lives in (for relative-import resolution)."""
    parts = list(rel.parent.parts)
    return parts[1:] if parts and parts[0] in SRC_ROOT_DIRS else parts


def _imports(tree, rel):
    """Yield (absolute dotted name, is_relative) for every import in the tree."""
    pkg = _package_of(rel)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name, False
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = pkg[:len(pkg) - (node.level - 1)] if node.level > 1 else pkg
                mod = ".".join(base + ([node.module] if node.module else []))
                rel_flag = True
            else:
                mod, rel_flag = node.module or "", False
            if not mod:
                continue
            yield mod, rel_flag
            for a in node.names:  # `from pkg import submodule`
                if a.name != "*":
                    yield f"{mod}.{a.name}", rel_flag


def read_sources(repo_dir):
    """{relative path (posix str): source text} for every analysable .py file in a checkout."""
    repo_dir = Path(repo_dir).resolve()
    out = {}
    for p in repo_dir.rglob("*.py"):
        rel = p.relative_to(repo_dir)
        if not (set(rel.parts) & SKIP_DIRS):
            out[rel.as_posix()] = p.read_text(encoding="utf-8", errors="replace")
    return out


def build_graph(repo_dir):
    """Return (networkx.DiGraph, stats dict) for a checkout directory."""
    return build_graph_from_sources(read_sources(repo_dir))


def build_graph_from_sources(sources):
    """Same as build_graph but from {relative path: source text}, so graphs can be built
    from any git revision without a checkout (see snapshots.py)."""
    rels = {Path(r): text for r, text in sources.items()}
    dirs_with_init = {r.parent for r in rels if r.name == "__init__.py"}
    index = {}  # dotted module name -> relative file path
    for rel in rels:
        names = _module_names(rel)
        if rel.name != "__init__.py" and rel.parent not in dirs_with_init:
            names.append(rel.stem)  # script-style local import (dir is not a package)
        for n in names:
            index.setdefault(n, rel)
    internal_tops = {n.split(".")[0] for n in index}

    G = nx.DiGraph()
    stats = {"n_files": len(rels), "parse_failures": 0}
    for rel in rels:
        G.add_node(rel.as_posix(), kind="file", role=file_role(rel))
    for rel, text in rels.items():
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError, RecursionError):
            stats["parse_failures"] += 1
            continue
        for dotted, is_rel in _imports(tree, rel):
            top = dotted.split(".")[0]
            if top in internal_tops or is_rel:
                parts = dotted.split(".")
                for k in range(len(parts), 0, -1):  # longest internal prefix wins
                    target = index.get(".".join(parts[:k]))
                    if target is not None:
                        if target != rel:
                            G.add_edge(rel.as_posix(), target.as_posix(), kind="internal")
                        break
            elif top not in sys.stdlib_module_names and top not in NOT_PACKAGES:
                dist = dist_name(top)
                if dist:
                    G.add_node(f"pkg:{dist}", kind="package")
                    G.add_edge(rel.as_posix(), f"pkg:{dist}", kind="external")
    return G, stats


def _entry_points(G):
    src = {n for n, d in G.nodes(data=True) if d["kind"] == "file" and d["role"] == "src"}
    roots = {n for n in src
             if not any(u in src for u in G.predecessors(n))}
    roots |= {n for n in src if n.endswith("__init__.py") and Path(n).parent.parent == Path(".")}
    roots |= {n for n in src if n.endswith("__init__.py") and Path(n).parent.parent.name in SRC_ROOT_DIRS}
    return roots


def package_features(G):
    """One dict per external package in the graph."""
    files = nx.DiGraph(G.subgraph(n for n, d in G.nodes(data=True) if d["kind"] == "file"))
    # BFS depth from entry points over file -> file edges
    depth = {r: 0 for r in _entry_points(G)}
    q = deque(depth)
    while q:
        u = q.popleft()
        for v in files.successors(u):
            if v not in depth:
                depth[v] = depth[u] + 1
                q.append(v)
    rows = []
    for node, d in G.nodes(data=True):
        if d["kind"] != "package":
            continue
        direct = list(G.predecessors(node))
        roles = [G.nodes[f]["role"] for f in direct]
        reach = nx.ancestors(G, node)  # every file that can reach the package
        dd = [depth[f] for f in direct if f in depth]
        rows.append({
            "package": node[4:],
            "package_norm": normalize_name(node[4:]),
            "blast_direct": len(direct),
            "blast_direct_src": roles.count("src"),
            "blast_direct_tests": roles.count("test"),
            "blast_transitive": len(reach),
            "depth_min": min(dd) if dd else "",
            "depth_mean": round(sum(dd) / len(dd), 3) if dd else "",
        })
    return sorted(rows, key=lambda r: (-r["blast_direct"], r["package"]))


def analyze(repo_dir, repo_name):
    return analyze_graph(*build_graph(repo_dir), repo_name)


def analyze_graph(G, stats, repo_name):
    rows = package_features(G)
    for r in rows:
        r.update(repo=repo_name, repo_n_files=stats["n_files"], repo_parse_failures=stats["parse_failures"])
    return rows


def clone(repo):
    dest = CHECKOUTS / repo.replace("/", "__")
    if not dest.exists():
        CHECKOUTS.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", "-q", f"https://github.com/{repo}", str(dest)], check=True)
    return dest


def main():
    import pandas as pd
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("checkout", nargs="?", help="path to an existing local checkout")
    ap.add_argument("--repos", nargs="*", default=[], help="owner/name list to shallow-clone and analyse")
    ap.add_argument("--out", default=str(ROOT / "data" / "graph_prototype_v0.csv"))
    args = ap.parse_args()

    rows = []
    if args.checkout:
        rows += analyze(args.checkout, Path(args.checkout).resolve().name)
    for repo in args.repos:
        rows += analyze(clone(repo), repo)
    if not rows:
        ap.error("give a checkout path or --repos")
    cols = ["repo", "package", "package_norm", "blast_direct", "blast_direct_src", "blast_direct_tests",
            "blast_transitive", "depth_min", "depth_mean", "repo_n_files", "repo_parse_failures"]
    df = pd.DataFrame(rows)[cols]
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    for repo, g in df.groupby("repo"):
        print(f"\n{repo}: {g['repo_n_files'].iloc[0]} files, {len(g)} external packages")
        print(g.head(8)[cols[1:9]].to_string(index=False))
    print(f"\nSaved {len(df)} rows to {args.out}")


if __name__ == "__main__":
    main()
