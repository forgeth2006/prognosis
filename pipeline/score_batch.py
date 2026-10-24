"""Batch scoring pipeline (Person C). Run from the repo root:

    python pipeline/score_batch.py              # live: open Dependabot PRs of the shortlisted repos
    python pipeline/score_batch.py --demo 20    # offline demo on the 20 newest frozen PRs (NOT an evaluation)

Steps: collect open PRs -> drop the ones training excluded -> graph snapshot per repo -> features
(same code as training) -> frozen model -> SQLite. Every PR seen gets a row, scored or skipped with a
reason; a failure in one repo or stage never stops the run.
"""
import argparse
import datetime as dt
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import joblib
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
from features_live import compute_features, prep  # noqa: E402
from label_ci import static_exclusion  # noqa: E402  (the exact exclusion rules used in training)

LIVE = ROOT / "data" / "live"
SCHEMA = """
CREATE TABLE IF NOT EXISTS scored_prs (
  repo TEXT, pr_number INTEGER, pr_url TEXT, title TEXT, package TEXT, old_version TEXT,
  new_version TEXT, bump_type TEXT, created_at TEXT, status TEXT, note TEXT,
  risk_score REAL, risk_percentile REAL, band TEXT, reasons TEXT,
  model_version TEXT, scored_at TEXT, run_id TEXT, PRIMARY KEY (repo, pr_number));
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT, status TEXT,
  n_seen INTEGER, n_scored INTEGER, n_skipped INTEGER, notes TEXT);
"""
ID_COLS = ["repo", "pr_number", "pr_url", "title", "package", "old_version", "new_version",
           "bump_type", "created_at"]


def log(msg):
    print(f"[{dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M:%S}Z] {msg}", flush=True)


def run(cmd, label):
    """Run a helper script without ever raising. Returns True on exit code 0."""
    p = subprocess.run([sys.executable, *cmd], cwd=ROOT, capture_output=True, text=True)
    if p.returncode != 0:
        tail = " | ".join(p.stderr.strip().splitlines()[-3:])
        log(f"{label} failed (exit {p.returncode}): {tail}")
    return p.returncode == 0


def collect_open(repos, max_prs):
    """Scrape open Dependabot PRs into a fresh file (cache cleared so every run sees current PRs)."""
    out = LIVE / "pr_open_raw.csv"
    out.unlink(missing_ok=True)
    shutil.rmtree(LIVE / ".cache", ignore_errors=True)
    cmd = ["scraping/scrape_prs.py", "--state", "open", "--max-prs", str(max_prs),
           "--out", str(out), "--cache-dir", str(LIVE / ".cache")]
    if repos:
        cmd += ["--repos", *repos]
    ok = run(cmd, "PR scrape")
    raw = pd.read_csv(out, dtype=str, keep_default_na=False) if out.exists() else pd.DataFrame()
    return raw, ok


def build_snapshots(new):
    """One snapshots.py call per repo (only the months needed). Returns snaps, index, failed repos."""
    snaps, idx, failed = [], [], []
    for repo, g in new.groupby("repo"):
        months = sorted(set(g["created_at"].astype(str).str[:7]))   # ISO UTC "YYYY-MM"
        tag = repo.replace("/", "__")
        s_out, i_out = LIVE / f"snaps_{tag}.csv", LIVE / f"snaps_index_{tag}.csv"
        for p in (s_out, i_out):
            p.unlink(missing_ok=True)
        ok = run(["graph_features/snapshots.py", "--repos", repo, "--months", *months,
                  "--out", str(s_out), "--index-out", str(i_out)], f"snapshots {repo}")
        try:
            if not ok:
                raise FileNotFoundError("snapshots.py failed")
            snaps.append(pd.read_csv(s_out))
            idx.append(pd.read_csv(i_out))
        except (FileNotFoundError, pd.errors.EmptyDataError):
            failed.append(repo)
    cat = lambda parts: pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()  # noqa: E731
    return cat(snaps), cat(idx), failed


def save(con, rec):
    cols = ID_COLS + ["status", "note", "risk_score", "risk_percentile", "band", "reasons",
                      "model_version", "scored_at", "run_id"]
    con.execute(f"INSERT OR REPLACE INTO scored_prs ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                [rec.get(c) for c in cols])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repos", nargs="*", help="owner/name list (default: scraping/shortlist_repos.txt)")
    ap.add_argument("--max-prs", type=int, default=30, help="max open PRs per repo")
    ap.add_argument("--demo", type=int, help="score the N newest frozen PRs offline (not an evaluation)")
    ap.add_argument("--model", default=str(ROOT / "pipeline" / "models" / "model_v1.joblib"))
    ap.add_argument("--history", default=str(ROOT / "data" / "labeled_prs_v2.csv"))
    ap.add_argument("--db", help="SQLite file (default data/live/prognosis.db, or demo.db with --demo)")
    a = ap.parse_args()

    LIVE.mkdir(parents=True, exist_ok=True)
    db = a.db or str(LIVE / ("demo.db" if a.demo else "prognosis.db"))
    model = joblib.load(a.model)            # a missing or incompatible model is fatal on purpose
    history = pd.read_csv(a.history)
    history = history[history["label"].notna()]
    con = sqlite3.connect(db)
    con.executescript(SCHEMA)
    started = dt.datetime.now(dt.timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ") + ("-demo" if a.demo else "")
    notes, skipped = [], []

    if a.demo:
        log("DEMO: these PRs were in the model's training data, so scores are not an evaluation")
        new = history.sort_values("created_at").tail(a.demo).copy()
        history = history.drop(new.index)
        snaps = pd.read_csv(ROOT / "data" / "graph_snapshots_v2.csv")
        index = pd.read_csv(ROOT / "data" / "graph_snapshots_index_v2.csv")
        n_seen = len(new)
    else:
        raw, ok = collect_open(a.repos, a.max_prs)
        if not ok:
            notes.append("PR scrape incomplete (rate limit or network); remaining PRs on the next run")
        n_seen = len(raw)
        done = {tuple(r) for r in con.execute("SELECT repo, pr_number FROM scored_prs WHERE status='scored'")}
        keep = []
        for rec in raw.to_dict("records"):
            if (rec["repo"], int(rec["pr_number"])) in done:
                continue
            reason = static_exclusion(rec)
            if reason:
                skipped.append((rec, f"excluded by training rules: {reason}"))
            else:
                keep.append(rec)
        new = pd.DataFrame(keep)
        snaps = index = pd.DataFrame()
        if len(new):
            new["pr_number"] = pd.to_numeric(new["pr_number"])
            snaps, index, failed = build_snapshots(new)
            for repo in failed:
                notes.append(f"graph snapshot failed for {repo}")
                for rec in new[new["repo"] == repo].to_dict("records"):
                    skipped.append((rec, "graph snapshot failed (not scored, will retry next run)"))
            new = new[~new["repo"].isin(failed)]

    n_scored = 0
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    if len(new):
        new = new.reset_index(drop=True)
        feat = compute_features(new, history, snaps, index)
        assert (feat["pr_number"].astype(int).to_numpy() == new["pr_number"].astype(int).to_numpy()).all()
        X = prep(feat)
        scores = model.score(X)
        pct, why = model.percentile(scores), model.reasons(X)
        for i, rec in enumerate(new.to_dict("records")):
            save(con, {**{c: rec.get(c) for c in ID_COLS}, "pr_number": int(rec["pr_number"]),
                       "status": "scored", "note": "demo" if a.demo else "", "risk_score": float(scores[i]),
                       "risk_percentile": float(pct[i]), "band": model.band(scores[i]), "reasons": why[i],
                       "model_version": model.version, "scored_at": now, "run_id": run_id})
            n_scored += 1
    for rec, why in skipped:
        save(con, {**{c: rec.get(c) for c in ID_COLS}, "pr_number": int(rec["pr_number"]),
                   "status": "skipped", "note": why, "model_version": model.version,
                   "scored_at": now, "run_id": run_id})
    status = "partial" if notes else "ok"
    con.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?)",
                (run_id, started.isoformat(timespec="seconds"), now, status, n_seen, n_scored,
                 len(skipped), "; ".join(notes)))
    con.commit()
    log(f"run {run_id}: {status}; seen {n_seen}, scored {n_scored}, skipped {len(skipped)}; db {db}")
    for n in notes:
        log(f"note: {n}")
    top = pd.read_sql("SELECT repo, pr_number, package, band, risk_percentile FROM scored_prs "
                      "WHERE run_id=? AND status='scored' ORDER BY risk_percentile DESC LIMIT 5", con, params=(run_id,))
    if len(top):
        log("highest-risk PRs this run:\n" + top.to_string(index=False))
    con.close()


if __name__ == "__main__":
    main()