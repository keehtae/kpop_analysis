"""Edit the three feature lists and K choices here, then run this module.

    python3 -m clustering.models

None chooses K using the notebook's silhouette/Davies-Bouldin rank sum.
"""

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from clustering.kmeans_model import KMeansAnalysis


ROOT = Path(__file__).resolve().parents[1]
MODELS = (
    dict(name="Model 1", features=["danceability", "spectral_flux_mean", "spectral_centroid_mean"],
         k=None, k_without_outliers=None),
    dict(name="Model 2", features=["loudness_ebu128_loudness_range", "tempo_bpm", "spectral_centroid_mean"],
         k=None, k_without_outliers=None),
    dict(name="Model 3", features=["danceability", "dissonance_mean", "spectral_centroid_mean"],
         k=None, k_without_outliers=None),
)
SETTINGS = dict(k_values=range(2, 11), seed=42, n_init=25, max_iter=300, tol=1e-8)


def build_clustering_data(input_path=ROOT / "docs/data/essentia_and_rankings.json",
                          output_dir=ROOT / "docs/data/clustering", progress=False):
    input_path, output_dir = Path(input_path), Path(output_dir)
    source_bytes = input_path.read_bytes()
    source = json.loads(source_bytes)
    required = {feature for model in MODELS for feature in model["features"]} | {"song", "artist", "album"}
    missing = required - set(source["columns"])
    if missing:
        raise ValueError("Missing clustering columns: " + ", ".join(sorted(missing)))
    rows = [dict(zip(source["columns"], row)) for row in source["rows"]]
    manifest = dict(source="gold.essentia_and_rankings", source_sha256=hashlib.sha256(source_bytes).hexdigest(),
                    models=[], comparison=[])
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="clustering-", dir=output_dir.parent) as temporary:
        staging = Path(temporary)
        for index, definition in enumerate(MODELS, 1):
            if len(definition["features"]) != 3:
                raise ValueError(f"{definition['name']} needs three features for its 3D plot.")
            analysis = KMeansAnalysis(definition["features"], **SETTINGS)
            report = analysis.run(rows, definition["name"], definition["k"], definition["k_without_outliers"])
            filename = f"model_{index}.json"
            analysis.save(report, staging / filename)
            manifest["models"].append(dict(name=definition["name"], file=filename, features=definition["features"]))
            for dataset, run in report["runs"].items():
                manifest["comparison"].append(dict(model=definition["name"], dataset=dataset,
                                                   songs=run["songs"], **run["final_metrics"]))
                if progress:
                    print(f"{definition['name']} / {dataset}: {run['songs']} songs; K={run['k_used']}; "
                          f"silhouette={run['final_metrics']['silhouette']:.4f}", flush=True)
        KMeansAnalysis.save(manifest, staging / "manifest.json")
        output_dir.mkdir(parents=True, exist_ok=True)
        for path in staging.iterdir():
            path.replace(output_dir / path.name)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "docs/data/essentia_and_rankings.json")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/data/clustering")
    args = parser.parse_args(argv)
    build_clustering_data(args.input, args.output, progress=True)


if __name__ == "__main__":
    main()
