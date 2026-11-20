"""Prepare the Essentia notebook charts from the public Gold export.

Run: python3 essentia_exploratory.py
Boxplots use Tukey whiskers and preserve song metadata for outlier tooltips.
Modes truncate to hundredths and select the smallest tied mode, as in the notebook.
"""

import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "docs/data"
AUDIO = ("onset_rate", "danceability", "loudness_ebu128_integrated", "loudness_ebu128_loudness_range")
CHORDS = ("chords_changes_rate", "chords_number_rate")
SPECTRAL = tuple(f"spectral_{feature}_{stat}" for feature in ("centroid", "rolloff", "flux")
                 for stat in ("mean", "stdev"))
MFCC = tuple(f"mfcc_mean_{index}" for index in range(1, 14))
BOXPLOTS = ("duration_sec", *AUDIO, *CHORDS, *SPECTRAL, "dissonance_mean", *MFCC)
STYLE = {
    "ink": "#111111", "accent": "#a67c52", "muted": "#676158", "line": "#d6cdc0",
    "fill": "rgba(166,124,82,0.15)",
    "display": "Baskerville, Iowan Old Style, Palatino Linotype, Times New Roman, serif",
    "body": "Avenir Next, Helvetica Neue, Segoe UI, sans-serif",
}


def numeric_rows(rows, column):
    result = []
    for row in rows:
        try:
            value = float(row[column])
        except (TypeError, ValueError):
            continue
        if np.isfinite(value):
            result.append((value, row))
    return result


def make_boxplot(rows, column):
    records = numeric_rows(rows, column)
    if not records:
        return {"whiskers": None, "outliers": [], "count": 0}
    values = np.array([value for value, _ in records])
    q1, median, q3 = np.quantile(values, [0.25, 0.5, 0.75])
    iqr = q3 - q1
    inside = (values >= q1 - 1.5 * iqr) & (values <= q3 + 1.5 * iqr)
    inliers = values[inside]
    outliers = [dict(value=value, **{key: row.get(key) or "Unknown" for key in ("song", "artist", "album")})
                for (value, row), keep in zip(records, inside) if not keep]
    return {"whiskers": [float(min(q1, inliers.min())), float(q1), float(median),
                         float(q3), float(max(q3, inliers.max()))],
            "outliers": outliers, "count": len(records)}


def make_histogram(rows, column, bins=10, bin_width=None):
    values = np.array([value for value, _ in numeric_rows(rows, column)])
    if not values.size:
        return {"bars": [], "count": 0}
    if bin_width is not None:
        start = np.floor(values.min() / bin_width) * bin_width
        stop = np.ceil(values.max() / bin_width) * bin_width + bin_width
        bins = np.arange(start, stop + bin_width, bin_width)
    counts, edges = np.histogram(values, bins=bins)
    return {"bars": [{"start": float(edges[index]), "end": float(edges[index + 1]), "count": int(count)}
                     for index, count in enumerate(counts)], "count": int(values.size)}


def five_number_summary_table(rows, columns):
    summaries = {}
    for column in columns:
        values = np.array([value for value, _ in numeric_rows(rows, column)])
        if not values.size:
            summaries[column] = dict.fromkeys(("max", "min", "mean", "median", "mode"))
            continue
        modes = Counter(np.trunc(values * 100) / 100)
        highest_count = max(modes.values())
        summaries[column] = {
            "max": float(values.max()), "min": float(values.min()), "mean": float(values.mean()),
            "median": float(np.median(values)),
            "mode": float(min(value for value, count in modes.items() if count == highest_count)),
        }
    return summaries


def key_counts(rows):
    counts = {"key": Counter(), "scale": Counter(), "combined": Counter()}
    for row in rows:
        key, scale = row.get("krumhansl_key"), row.get("krumhansl_key_scale")
        if key:
            counts["key"][str(key)] += 1
        if scale:
            counts["scale"][str(scale)] += 1
        if key and scale:
            counts["combined"][f"{key} {scale}"] += 1
    return {name: [{"label": key, "count": count} for key, count in sorted(values.items())]
            for name, values in counts.items()}


def build_exploratory_data(input_path=DATA_DIR / "essentia_and_rankings.json",
                           output_path=DATA_DIR / "essentia_exploratory.json"):
    source = json.loads(Path(input_path).read_text(encoding="utf-8"))
    required = {*BOXPLOTS, "beats_count", "tempo_bpm", "krumhansl_key", "krumhansl_key_scale",
                "song", "artist", "album"}
    missing = required - set(source["columns"])
    if missing:
        raise ValueError("Missing Essentia chart columns: " + ", ".join(sorted(missing)))
    rows = [dict(zip(source["columns"], row)) for row in source["rows"]]
    result = {
        "song_count": len(rows), "style": STYLE,
        "boxplots": {column: make_boxplot(rows, column) for column in BOXPLOTS},
        "histograms": {"beats_count": make_histogram(rows, "beats_count", bin_width=15),
                       "tempo_bpm": make_histogram(rows, "tempo_bpm")},
        "krumhansl": key_counts(rows),
        "summaries": {"audio": five_number_summary_table(rows, AUDIO),
                      "chords": five_number_summary_table(rows, CHORDS),
                      "mfcc": five_number_summary_table(rows, MFCC)},
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n",
                           encoding="utf-8")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DATA_DIR / "essentia_and_rankings.json")
    parser.add_argument("--output", type=Path, default=DATA_DIR / "essentia_exploratory.json")
    args = parser.parse_args(argv)
    result = build_exploratory_data(args.input, args.output)
    print(f"Essentia charts: {result['song_count']:,} songs")


if __name__ == "__main__":
    main()
