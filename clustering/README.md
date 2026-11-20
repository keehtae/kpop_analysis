# Clustering models

Two Python scripts replace the repeated notebook code:

- `kmeans_model.py`: reusable `KMeansAnalysis` class for preparation, one-pass
  outlier filtering, scaling, K selection, model fitting and reports.
- `models.py`: the three feature lists, optional K overrides and shared settings.

From the repository root:

```sh
python3 -m pip install -r clustering/requirements.txt
python3 -m clustering.models
```

The input defaults to the public `docs/data/essentia_and_rankings.json` export.
Reports go to `docs/data/clustering/`. The normal Gold public export also rebuilds
these reports. No local filesystem paths or model pickle files are published.

The feature lists follow the notebook's executable code:

| Model | Features |
| --- | --- |
| Model 1 | `danceability`, `spectral_flux_mean`, `spectral_centroid_mean` |
| Model 2 | `loudness_ebu128_loudness_range`, `tempo_bpm`, `spectral_centroid_mean` |
| Model 3 | `danceability`, `dissonance_mean`, `spectral_centroid_mean` |

Edit `MODELS` in `models.py` to change features or choose K. Each displayed model
uses three features. `None` automatically minimizes the sum of the silhouette
rank (higher is better) and Davies–Bouldin rank (lower is better), breaking ties
with the smaller K. Inertia is displayed separately, as in the notebook.

The notebook's settings are preserved: K=2–10, seed=42, n_init=25, max_iter=300,
tol=1e-8, and population-standard-deviation scaling. Nonfinite feature rows are
excluded, then repeated feature vectors retain their first row. The filtered
run removes rows outside any feature's 1.5-IQR fences, once, and fits a new scaler.
Both runs fit K-means on standardized values. The plot scale toggle changes
coordinates and centroid displays; it does not fit a second model on raw units.

Results are recomputed from the current Gold dataset. They need not match saved
notebook outputs from an older workbook. The manifest records an input hash,
and each model records its numerical-library versions and preprocessing counts.

## Display organization and consolidated charts

All analytical chart families are retained. Repeated notebook figures are
consolidated into controls:

- Original and standardized 3D plots share a values selector.
- Uncolored and clustered scatterplots share a color selector.
- Full-data and outlier-filtered analyses share a dataset selector per model.
- Repeated feature distributions and pairwise plots use feature/pair selectors.
- Both centroid tables share an original/standardized selector.

Correlation matrices, pair correlations, feature distributions, inertia,
silhouette, Davies–Bouldin, candidate cluster sizes, cluster-size bars,
standardized centroid heatmaps and cluster feature distributions are included.
Descriptive/scaling statistics, diagnostics, cluster summaries, centroids,
feature profiles, shape/distance summaries, outlier audits, assignments and
the six-run model comparison remain available as tables and CSV downloads.

Separate copies of the same 3D plot and feature charts were removed because the
selectors show those same results without duplicating large figures. Repeated
notebook dataframe echoes, export messages and serialized estimator files are
not separate website panels. Old narrative commentary was not copied: several
paragraphs describe earlier feature selections and obsolete numeric results.
Blank commentary areas are provided beside charts and below wide outputs.

To add commentary, edit the empty paragraphs in `docs/models.html`. They remain
in place when chart controls change; no commentary is stored in generated JSON.
