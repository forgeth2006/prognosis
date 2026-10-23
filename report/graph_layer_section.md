# Graph-Layer Exploratory Analysis

## Dataset

The frozen feature table (`data/feature_table_v2.csv`) contains 1,314 labeled pull requests, including 129 CI breakages and 1,185 non-breakages. The overall observed breakage rate is 9.8%.

## Observed associations

### Historical breakage rate

The lowest `hist_rate` bin had 14 breakages among 263 pull requests (5.3%), while the highest bin had 55 among 263 (20.9%). This descriptive gradient suggests that historical CI outcomes may contain useful information for predicting future breakage. It does not establish that historical rate improves out-of-sample model performance.

### Graph availability, blast radius and depth

For `not_in_graph`, the observed breakage rate was 7.6% when the flag was 0 (37/490) and 11.2% when it was 1 (92/824). For blast radius, breakage rates were 9.0% with 1 importing file, 9.5% with 2–3 files, 5.6% with 4–9 files, and 5.1% with 10+ files, compared with 11.2% for packages not imported by repository code. Thus, greater blast radius did not correspond to a higher observed breakage rate in this dataset.

Rows with missing graph depth (`depth_missing=1`) had a breakage rate of 11.0% (103/937), compared with 6.9% (26/377) when depth was available. Depth-based comparisons are limited by sparse data and few breakages in some bins.

These are descriptive associations, not causal effects. Repository and time can confound the comparisons: observed breakage rates ranged from 0% to 33% across repositories and fell from 17.6% to 5.7% over time. After adjustment for repository, the confidence intervals for blast-radius and depth effects included 1, so this sample did not establish a reliable independent graph-feature effect. See the [adjusted graph-layer analysis](graph_layer_adjusted_analysis.md) for the detailed results and limitations.

### Version-delta features

The `minor_delta` bins had observed breakage rates of 8.1%, 8.3%, and 24.8%. The `patch_delta` bins had rates of 18.0%, 9.9%, 7.4%, and 2.4%.

These features require additional validation before interpretation. Negative deltas and differences in version-update types can complicate their meaning, so these binned patterns should not be presented as evidence that a particular update type causes breakage.

### Changelog features

Pull requests with `changelog_found=1` had an observed breakage rate of 8.7% (73/840), compared with 11.8% (56/474) when changelog information was absent. This is a descriptive association only; the difference may reflect data coverage or other characteristics of the pull requests.

## Limitations

- The dataset contains 129 breakages, so some feature bins have relatively few positive examples.
- The prerelease flag has only one row with value 1 and cannot support a reliable comparison.
- Missing graph features may encode data-collection coverage as well as package structure.
- Binned rates are unadjusted comparisons. They do not account for confounding, establish statistical significance, or demonstrate predictive performance.
- Feature usefulness should be evaluated with the project's leakage-safe temporal split and appropriate held-out metrics.

## Conclusion

Historical breakage rate and graph-feature availability show descriptive differences worth investigating in subsequent modeling. These findings are exploratory and should guide validation, not be treated as causal conclusions or claims of established predictive value.

Figures and supporting bin counts are available in `report/figures/eda/eda_features_vs_label_1.png`, `report/figures/eda/eda_features_vs_label_2.png`, and `report/figures/eda/eda_summary.csv`.

