"""Reusable, deterministic K-means analysis extracted from kmeans.ipynb."""

from itertools import combinations
from importlib.metadata import version
import json
from pathlib import Path

import numpy as np
import polars as pl
from scipy.stats import rankdata
from sklearn.cluster import KMeans
from sklearn.metrics import davies_bouldin_score, silhouette_samples, silhouette_score
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits


def json_values(value):
    if isinstance(value, np.ndarray):
        return json_values(value.tolist())
    if isinstance(value, np.generic):
        return json_values(value.item())
    if isinstance(value, dict):
        return {str(key): json_values(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_values(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


class KMeansAnalysis:
    """Prepare data, evaluate K, and report full/filtered clustering results.

    Deduplicate selected feature vectors before the one-pass 1.5-IQR filter.
    Each run fits its own StandardScaler; original-value plots use its inverse
    transform, not a second unstandardized clustering model.
    """

    def __init__(self, features, k_values=range(2, 11), seed=42, n_init=25,
                 max_iter=300, tol=1e-8):
        self.features = list(features)
        if not self.features or len(set(self.features)) != len(self.features):
            raise ValueError("Provide distinct feature names.")
        self.k_values = sorted(set(k_values))
        self.settings = dict(seed=seed, n_init=n_init, max_iter=max_iter, tol=tol,
                             standard_deviation_ddof=0)

    def prepare_data(self, rows):
        records, vectors, seen = [], [], set()
        invalid = duplicates = 0
        for index, row in enumerate(rows):
            try:
                values = tuple(float(row[feature]) for feature in self.features)
            except (KeyError, TypeError, ValueError):
                invalid += 1
                continue
            if not np.isfinite(values).all():
                invalid += 1
                continue
            if values in seen:
                duplicates += 1
                continue
            seen.add(values)
            records.append({"song_id": index + 1, **{field: row.get(field) or "Unknown"
                                                    for field in ("song", "artist", "album")}})
            vectors.append(values)
        values = np.asarray(vectors, dtype=float)
        if len(values) < 3 or np.any(values.std(axis=0) == 0):
            raise ValueError("Need at least three valid, distinct rows and nonconstant features.")
        return records, values, dict(input_songs=len(rows), invalid_rows=invalid,
                                     duplicate_feature_rows=duplicates, retained_songs=len(values))

    def remove_outliers(self, values):
        q1, q3 = np.quantile(values, [.25, .75], axis=0)
        lower, upper = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
        flags = (values < lower) | (values > upper)
        fences = [dict(feature=feature, lower_fence=lower[index], upper_fence=upper[index])
                  for index, feature in enumerate(self.features)]
        return ~flags.any(axis=1), flags, fences

    def fit_kmeans(self, values, k):
        return KMeans(n_clusters=k, init="k-means++", random_state=self.settings["seed"],
                      n_init=self.settings["n_init"], max_iter=self.settings["max_iter"],
                      tol=self.settings["tol"]).fit(values)

    def evaluate_k(self, values):
        ks = [k for k in self.k_values if 2 <= k <= min(len(values) - 1, len(np.unique(values, axis=0)))]
        if not ks:
            raise ValueError("No valid candidate K.")
        candidates = {k: self.fit_kmeans(values, k) for k in [1, *ks]}
        diagnostics = [dict(k=k, inertia=candidates[k].inertia_,
                            silhouette=silhouette_score(values, candidates[k].labels_),
                            davies_bouldin=davies_bouldin_score(values, candidates[k].labels_)) for k in ks]
        ranks = rankdata([-row["silhouette"] for row in diagnostics]) + rankdata(
            [row["davies_bouldin"] for row in diagnostics])
        suggested = min(zip(ranks, ks))[1]
        for row, rank in zip(diagnostics, ranks):
            row["rank_sum"] = rank
        return candidates, diagnostics, suggested

    def describe_features(self, values):
        return (pl.DataFrame(values, schema=self.features, orient="row")
                .describe(percentiles=[.25, .5, .75])
                .filter(~pl.col("statistic").is_in(["count", "null_count"])).to_dicts())

    def feature_distributions(self, values, labels):
        distributions = {}
        for index, feature in enumerate(self.features):
            vector = values[:, index]
            counts, edges = np.histogram(vector, bins=30)
            profile_edges = np.linspace(vector.min(), vector.max(), 26)
            clusters = []
            for cluster in np.unique(labels):
                group = vector[labels == cluster]
                cluster_counts, _ = np.histogram(group, bins=profile_edges)
                shares = cluster_counts / len(group)
                clusters.append(dict(cluster=int(cluster + 1), counts=cluster_counts,
                                     shares=shares, density=shares / np.diff(profile_edges)))
            distributions[feature] = dict(counts=counts, edges=edges,
                                          profile_edges=profile_edges, clusters=clusters)
        return distributions

    def model_tables(self, values, standardized, model, scaler):
        labels = model.labels_
        distances = np.linalg.norm(standardized - model.cluster_centers_[labels], axis=1)
        scores = silhouette_samples(standardized, labels)
        summary, profiles, shapes = [], [], []
        for cluster in range(model.n_clusters):
            mask = labels == cluster
            group, group_distances, group_scores = values[mask], distances[mask], scores[mask]
            summary.append(dict(cluster=cluster + 1, size=len(group), proportion=len(group) / len(values),
                                mean_distance=group_distances.mean(), within_cluster_SSE=np.square(group_distances).sum(),
                                mean_silhouette=group_scores.mean(), negative_silhouettes=int((group_scores < 0).sum())))
            for index, feature in enumerate(self.features):
                vector = group[:, index]
                q1, median, q3 = np.quantile(vector, [.25, .5, .75])
                profiles.append(dict(cluster=cluster + 1, feature=feature, mean=vector.mean(),
                                     std=vector.std(ddof=1) if len(vector) > 1 else None,
                                     minimum=vector.min(), q1=q1, median=median, q3=q3, maximum=vector.max()))
            points = standardized[mask]
            eigenvalues = np.linalg.eigvalsh(np.atleast_2d(np.cov(points, rowvar=False))) if len(points) > values.shape[1] else None
            shapes.append(dict(cluster=cluster + 1,
                               covariance_eigenvalue_ratio=eigenvalues[-1] / max(eigenvalues[0], 1e-12) if eigenvalues is not None else None,
                               median_distance=np.median(group_distances), p95_distance=np.quantile(group_distances, .95)))
        def centers_table(centers):
            return [dict(cluster=index + 1, **dict(zip(self.features, center))) for index, center in enumerate(centers)]
        return dict(cluster_summary=summary, feature_profiles=profiles, cluster_shape=shapes,
                    centroids_original=centers_table(scaler.inverse_transform(model.cluster_centers_)),
                    centroids_standardized=centers_table(model.cluster_centers_),
                    final_metrics=dict(k=model.n_clusters, inertia=model.inertia_, silhouette=scores.mean(),
                                       davies_bouldin=davies_bouldin_score(standardized, labels), iterations=model.n_iter_),
                    distances=distances, silhouette_values=scores)

    def analyze(self, records, values, k=None):
        if len(values) < 3 or np.any(values.std(axis=0) == 0):
            raise ValueError("Filtering left insufficient rows or a constant feature.")
        scaler = StandardScaler()
        standardized = scaler.fit_transform(values)
        candidates, diagnostics, suggested = self.evaluate_k(standardized)
        chosen = suggested if k is None else k
        if not isinstance(chosen, int) or chosen not in [row["k"] for row in diagnostics]:
            raise ValueError("Choose K from the tested candidates.")
        fitted = candidates[chosen]
        tables = self.model_tables(values, standardized, fitted, scaler)
        correlation = np.corrcoef(values, rowvar=False)
        pairs = [dict(feature_1=self.features[i], feature_2=self.features[j], pearson_r=correlation[i, j],
                      strength="strong" if abs(correlation[i, j]) >= .7 else "moderate" if abs(correlation[i, j]) >= .3 else "weak")
                 for i, j in combinations(range(len(self.features)), 2)]
        candidate_sizes = [dict(k=row["k"], cluster=cluster + 1, songs=int(count)) for row in diagnostics
                           for cluster, count in enumerate(np.bincount(candidates[row["k"]].labels_, minlength=row["k"]))]
        scaling = [dict(feature=feature, mean=scaler.mean_[index], standard_deviation=scaler.scale_[index])
                   for index, feature in enumerate(self.features)]
        return dict(songs=len(values), suggested_k=suggested, k_override=k, k_used=chosen,
                    descriptive=self.describe_features(values), scaling=scaling,
                    correlation=correlation, correlation_pairs=pairs, diagnostics=diagnostics,
                    baseline_inertia=candidates[1].inertia_, candidate_cluster_sizes=candidate_sizes,
                    distributions=self.feature_distributions(values, fitted.labels_),
                    points=dict(songs=records, original=values, standardized=standardized,
                                cluster=fitted.labels_ + 1, distance=tables.pop("distances"),
                                silhouette=tables.pop("silhouette_values")), **tables)

    def run(self, rows, name="Model", k=None, k_without_outliers=None):
        records, values, preprocessing = self.prepare_data(rows)
        keep, flags, fences = self.remove_outliers(values)
        removed = [{**record, **dict(zip(self.features, vector)),
                    "outlier_features": [feature for feature, flag in zip(self.features, marked) if flag]}
                   for record, vector, marked, retained in zip(records, values, flags, keep) if not retained]
        with threadpool_limits(limits=1):
            full = self.analyze(records, values, k)
            filtered = self.analyze([record for record, retained in zip(records, keep) if retained],
                                    values[keep], k_without_outliers)
        return json_values(dict(name=name, features=self.features, settings=self.settings,
                                library_versions={library: version(library) for library in ("numpy", "scikit-learn", "polars")},
                                preprocessing=preprocessing, outlier_fences=fences, removed_songs=removed,
                                runs={"all": full, "without_outliers": filtered}))

    @staticmethod
    def save(report, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(json_values(report), ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n",
                        encoding="utf-8")
