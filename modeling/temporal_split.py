"""Temporal train/test split draft (Person C).

Run from the repo root:
    python modeling/temporal_split.py
"""
import argparse

import pandas as pd

LABELS = "data/labeled_prs_v0.csv"
GRAPH = "data/graph_prototype_v0.csv"

# CI outcome columns: they describe what happened AFTER the bump, so they
# must NOT be used as model features (leakage). To be confirmed with Person B.
OUTCOME_COLS = [
    "ci_status", "n_workflow_runs", "failed_workflows",
    "flaky_workflows", "fail_confidence", "label",
]


def load_labeled(path):
    df = pd.read_csv(path, parse_dates=["created_at"])
    df = df[df["label"].notna()].copy()
    return df.sort_values("created_at").reset_index(drop=True)


def join_graph(labeled, graph_path):
    g = pd.read_csv(graph_path)
    n_before = len(labeled)
    m = labeled.merge(g, on=["repo", "package"], how="left", indicator=True)
    assert len(m) == n_before, "join changed the row count (duplicate graph keys?)"
    m["not_in_graph"] = (m["_merge"] == "left_only").astype(int)
    m = m.drop(columns="_merge")
    blast_cols = [c for c in g.columns if c.startswith("blast_")]
    m[blast_cols] = m[blast_cols].fillna(0)
    return m


def temporal_split(df, train_frac=0.8):
    df = df.sort_values("created_at").reset_index(drop=True)
    cutoff = df["created_at"].iloc[int(len(df) * train_frac)]
    train = df[df["created_at"] < cutoff]
    test = df[df["created_at"] >= cutoff]
    assert train["created_at"].max() < test["created_at"].min(), "time overlap"
    return train, test, cutoff


def report(name, d):
    print(f"{name}: {len(d)} rows | label=1: {int(d['label'].sum())} "
          f"({d['label'].mean():.1%}) | {d['created_at'].min().date()} to "
          f"{d['created_at'].max().date()}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default=LABELS)
    ap.add_argument("--graph", default=GRAPH)
    ap.add_argument("--train-frac", type=float, default=0.8)
    a = ap.parse_args()

    labeled = load_labeled(a.labels)
    print(f"labeled rows: {len(labeled)}")
    data = join_graph(labeled, a.graph)
    print(f"after graph join: {len(data)} rows, not_in_graph: {data['not_in_graph'].sum()}")

    nulls = data.isna().sum()
    print("columns with nulls:\n", nulls[nulls > 0].to_string() or "none")

    train, test, cutoff = temporal_split(data, a.train_frac)
    print(f"cutoff date: {cutoff.date()}")
    report("train", train)
    report("test", test)