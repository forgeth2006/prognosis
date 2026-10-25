"""PRognosis dashboard (Person C). Run from the repo root:

    streamlit run pipeline/dashboard.py
"""
import os
import sqlite3
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
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

st.subheader("Where the risky PRs are")
if len(scored):
    order = [b for b in ["review first", "look closer", "routine"] if b in set(scored["band"])]
    st.bar_chart(scored.pivot_table(index="repo", columns="band", values="pr_number",
                                    aggfunc="count", fill_value=0)[order])
    st.caption("Open PRs scored so far, by repo and risk band.")

st.subheader("Why is this PR ranked here?")
if len(view):
    names = [f"{r.repo} #{r.pr_number}: {r.package} {r.old_version} -> {r.new_version}"
             for r in view.itertuples()]
    row = view.iloc[names.index(st.selectbox("PR", names))]
    effects = {}
    for part in str(row["reasons"]).split(";"):
        name, _, val = part.strip().rpartition(" (")
        if name:
            effects[name] = float(val.rstrip(")"))
    if effects:
        st.bar_chart(pd.Series(effects, name="effect on score"))
        st.caption("The three features that moved this PR's score most. Positive raises the score, negative "
                   "lowers it (model units, before calibration). hist_* = this package's breakage history.")

oof_file = ROOT / "modeling" / "results" / "week13_oof_predictions.csv"
st.subheader("How much does the ranking help?")
if oof_file.exists():
    oof = pd.read_csv(oof_file).sort_values("score", ascending=False).reset_index(drop=True)
    n, pos = len(oof), int(oof["label"].sum())
    grid = np.linspace(0.05, 1.0, 20)
    idx = np.ceil(grid * n).astype(int) - 1
    caught = oof["label"].cumsum().to_numpy() / pos
    st.line_chart(pd.DataFrame({"model ranking": caught[idx], "random order": grid},
                               index=pd.Index((grid * 100).round(0).astype(int), name="% of PRs reviewed")))
    flagged = oof["baseline_flag"].mean()
    base_caught = oof.loc[oof["baseline_flag"] == 1, "label"].sum() / pos
    st.caption(f"Share of breakages caught if you review PRs from the highest score down. Held-out time windows "
               f"(Week 13): {n} PRs, {pos} breakages. For comparison, the 'major bump' rule flags "
               f"{flagged:.0%} of PRs and catches {base_caught:.0%} of the breakages. Small sample, so indicative.")
    q = ROOT / "modeling" / "results" / "week13_review_queue.csv"
    if q.exists():
        st.dataframe(pd.read_csv(q).round(3), hide_index=True)

    st.subheader("Can the score be read as a probability?")
    bins = pd.qcut(oof["score"].rank(method="first"), 5, labels=False)
    cal = oof.groupby(bins).agg(predicted=("score", "mean"), observed=("label", "mean"), PRs=("label", "size"))
    st.line_chart(pd.DataFrame({"observed breakage rate": cal["observed"].to_numpy(),
                                "perfect calibration": cal["predicted"].to_numpy()},
                               index=pd.Index(cal["predicted"].round(3).to_numpy(), name="mean predicted score")))
    st.caption("Held-out PRs grouped into five score bins. Close to the 'perfect' line means the score can be read "
               "as a probability. Scores here are compressed and the sample is small, so use the band and ranking, "
               "not the exact percentage.")
else:
    st.info("Run `python modeling/validation.py` to create the held-out predictions this section needs.")

features = ROOT / "data" / "feature_table_v2.csv"
with st.expander("Does blast radius matter? (frozen data, not model output)"):
    if features.exists():
        d = pd.read_csv(features, usecols=["blast_direct", "label"])
        d = d[d["label"].notna()].copy()
        d["blast"] = pd.cut(pd.to_numeric(d["blast_direct"], errors="coerce").fillna(0),
                            [-1, 0, 2, 9, 1e9], labels=["0", "1-2", "3-9", "10+"])
        rate = d.groupby("blast", observed=True)["label"].agg(rate="mean", PRs="size")
        st.bar_chart(rate["rate"])
        st.caption("Breakage rate by number of files that import the package (n = "
                   + ", ".join(f"{i}: {int(r.PRs)}" for i, r in rate.iterrows())
                   + "). Unadjusted: breakage rates also differ by repo (0-33%) and fell over time, and both "
                     "are mixed into these bins. See the adjusted analysis in report/.")

with st.expander("Skipped PRs and recent runs"):
    st.dataframe(skipped[["repo", "pr_number", "package", "note"]], hide_index=True)
    st.dataframe(runs, hide_index=True)