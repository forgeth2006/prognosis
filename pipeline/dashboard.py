"""PRognosis dashboard (Person C). Run from the repo root:

    streamlit run pipeline/dashboard.py
"""
import os
import sqlite3
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
st.set_page_config(page_title="PRognosis", layout="wide")
st.title("PRognosis: dependency-bump review queue")
st.caption("Scores rank PRs by how likely a bump is to break CI. They are not precise probabilities: "
           "read the band and the percentile, and review the top band first.")

REPO = "forgeth2006/prognosis"


@st.cache_data(ttl=300, show_spinner="Fetching the latest database from the live-data branch ...")
def fetch_live_db(path):
    url = f"https://raw.githubusercontent.com/{REPO}/live-data/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "prognosis-dashboard"})
    if os.environ.get("GITHUB_TOKEN"):               # only needed if the repo is private
        req.add_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    out = Path(tempfile.gettempdir()) / "prognosis_live.db"
    out.write_bytes(data)
    return str(out)


source = st.sidebar.radio("Data source", ["live-data branch", "local file"])
if source == "live-data branch":
    remote_path = st.sidebar.text_input("File in the live-data branch", "prognosis.db")
    try:
        db = fetch_live_db(remote_path)
    except (urllib.error.URLError, OSError) as e:
        st.error(f"Could not fetch the database from the live-data branch ({e}). If the repo is private, "
                 "set GITHUB_TOKEN before starting Streamlit; otherwise pick 'local file'.")
        st.stop()
else:
    db = st.sidebar.text_input("Database", str(ROOT / "data" / "live" / "prognosis.db"))
    if not Path(db).exists():
        st.warning(f"No database at {db}. Run `python pipeline/score_batch.py` (or `--demo 20`) first.")
        st.stop()
con = sqlite3.connect(db)
df = pd.read_sql("SELECT * FROM scored_prs", con)
runs = pd.read_sql("SELECT * FROM runs ORDER BY started_at DESC LIMIT 10", con)
scored, skipped = df[df["status"] == "scored"], df[df["status"] == "skipped"]
if len(runs):
    st.caption(f"Last run: {runs.iloc[0]['finished_at']} ({runs.iloc[0]['status']})")
if "demo" in " ".join(runs["run_id"].astype(str)):
    st.info("Demo data: these PRs were in the model's training data, so the scores are not an evaluation.")

c1, c2, c3, c4 = st.columns(4)
c1.metric("PRs scored", len(scored))
c2.metric("Review first", int((scored["band"] == "review first").sum()))
c3.metric("Look closer", int((scored["band"] == "look closer").sum()))
c4.metric("Skipped (see reasons below)", len(skipped))

bands = st.sidebar.multiselect("Bands", ["review first", "look closer", "routine"],
                               default=["review first", "look closer"])
repos = st.sidebar.multiselect("Repos", sorted(scored["repo"].unique()))
view = scored[scored["band"].isin(bands)]
if repos:
    view = view[view["repo"].isin(repos)]
view = view.sort_values("risk_percentile", ascending=False).copy()
view["riskier than"] = (view["risk_percentile"] * 100).round(0).astype(int).astype(str) + "% of past PRs"
view["bump"] = view["package"].astype(str) + " " + view["old_version"].astype(str) + " -> " + view["new_version"].astype(str)
st.subheader("Review queue")
st.dataframe(view[["band", "riskier than", "repo", "pr_number", "bump", "bump_type", "reasons", "pr_url"]],
             use_container_width=True, hide_index=True,
             column_config={"pr_url": st.column_config.LinkColumn("PR")})
st.caption("'reasons' lists the three features that moved this PR's score most (+ raises risk, - lowers it).")

st.subheader("How reliable is the ranking?")
q = ROOT / "modeling" / "results" / "week13_review_queue.csv"
if q.exists():
    st.write("Held-out time windows (Week 13): checking the riskiest PRs first catches breakages at "
             "about 2x the average rate. Small sample: 83 breakages.")
    st.dataframe(pd.read_csv(q).round(3), hide_index=True)

with st.expander("Skipped PRs and recent runs"):
    st.dataframe(skipped[["repo", "pr_number", "package", "note"]], hide_index=True)
    st.dataframe(runs, hide_index=True)