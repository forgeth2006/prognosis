"""Rebuild every data/graph figure and table used in the report, from the frozen data (PRognosis, Weeks 13-14).

    python graph_features/make_report_figures.py

Runs, in order: eda_features_vs_label.py, eda_graph_layer.py, check_label_trend.py.
Read-only on data/. Outputs go to report/figures/eda/. Safe to rerun; same input gives the same output.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEPS = ["eda_features_vs_label.py", "eda_graph_layer.py", "check_label_trend.py"]


def main():
    for s in STEPS:
        print(f"== {s}", flush=True)
        subprocess.run([sys.executable, str(HERE / s)], check=True)
    print("done: report/figures/eda/")


if __name__ == "__main__":
    main()
