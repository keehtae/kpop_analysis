"""Build the copied K-pop Data Atlas charts from public Gold rankings.

Chart calculations are retained from the original site's generate_assets.py.
Only this repository's public exports/configuration are read; the original
website directory is never imported, written to, or required after copying.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "docs/data"
DATA_PATH = DATA_DIR / "rankings.json"

COLUMN_NAMES = [
    "year",
    "week",
    "rank",
    "song_title",
    "artist",
    "album",
    "score",
    "production_agency",
    "distribution_agency",
]


def load_data(path: Path = DATA_PATH) -> pl.DataFrame:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {"year", "time", "rank", "song_title", "artist", "album", "score", "production", "distribution"}
    missing = required - set(payload["columns"])
    if missing:
        raise ValueError("The copied Atlas charts require these public ranking columns: " + ", ".join(sorted(missing)))
    frame = pl.DataFrame(payload["rows"], schema=payload["columns"], orient="row").rename({
        "time": "week", "production": "production_agency", "distribution": "distribution_agency",
    })
    return (
        frame
        .with_columns(
            pl.col("year").cast(pl.Int64),
            pl.col("week").cast(pl.Int64),
            pl.col("rank").cast(pl.Int64),
            pl.col("score").cast(pl.Utf8).str.replace_all(",", "").cast(pl.Int64),
        )
        .with_columns(
            pl.concat_str([pl.col("artist"), pl.lit(" - "), pl.col("song_title")]).alias("song_key"),
            pl.struct(["year", "week"]).map_elements(
                lambda row: date.fromisocalendar(row["year"], row["week"], 1),
                return_dtype=pl.Date,
            ).alias("chart_date"),
        )
        .with_columns(
            (pl.col("year").cast(pl.Utf8) + pl.lit("-W") + pl.col("week").cast(pl.Utf8).str.zfill(2)).alias("week_label")
        )
        .sort(["chart_date", "rank"])
    )


def summarize_unique_songs_by_agency(frame: pl.DataFrame, agency_column: str) -> pl.DataFrame:
    return (
        frame.group_by(agency_column)
        .agg(pl.col("song_key").n_unique().alias("unique_song_count"))
        .sort("unique_song_count", descending=True)
    )


def build_big_four_data(df: pl.DataFrame, config_dir: Path = DATA_DIR) -> dict:
    """Roll up the full CSV using the reviewed, explicit production label map."""
    config = json.loads((config_dir / "production_groups.json").read_text())
    normalize = lambda label: " ".join(label.casefold().split())
    lookup = {}
    for group, rule in config["groups"].items():
        for label in rule["labels"]:
            key = normalize(label)
            if key in lookup:
                raise ValueError(f"Duplicate production label mapping: {label}")
            lookup[key] = group
    songs = {group: set() for group in config["groups"]}
    breakdown = {group: {} for group in config["groups"]}
    unmatched = set()
    for row in df.iter_rows(named=True):
        credit = row["production_agency"]
        # Exact, case-insensitive tokens prevent substring matches to unrelated labels.
        groups = {lookup[normalize(token)] for token in credit.split(",") if normalize(token) in lookup}
        if not groups:
            unmatched.add(credit)
        key = (row["artist"], row["song_title"])
        for group in groups:
            songs[group].add(key)
            breakdown[group].setdefault(credit, set()).add(key)
    return {
        "reviewed_on": config["reviewed_on"],
        "policy": config["policy"],
        "groups": [
            {"group": group, "unique_song_count": len(songs[group]),
             "labels": [{"label": label, "unique_song_count": len(keys)}
                        for label, keys in sorted(breakdown[group].items())],
             "label_count_sum": sum(map(len, breakdown[group].values()))}
            for group in config["groups"]
        ],
        "unmatched_production_labels": sorted(unmatched),
    }


def build_distribution_groups(df: pl.DataFrame, config_dir: Path = DATA_DIR) -> dict:
    """Group recorded distributor credits; audit exclusions without changing the source."""
    config = json.loads((config_dir / "distribution_groups.json").read_text())
    normalize = lambda value: " ".join(value.casefold().split())
    lookup = {}
    for group, rule in config["groups"].items():
        for credit in rule["credits"]:
            key = normalize(credit)
            if key in lookup:
                raise ValueError(f"Duplicate distribution mapping: {credit}")
            lookup[key] = group
    groups = {group: {} for group in config["groups"]}
    excluded = {}
    for row in df.iter_rows(named=True):
        credit = row["distribution_agency"]
        group = lookup.get(normalize(credit))
        target = groups[group] if group else excluded
        target.setdefault(credit, set()).add((row["artist"], row["song_title"]))
    included_songs = set().union(*(songs for credits in groups.values() for songs in credits.values()))
    excluded_songs = set().union(*excluded.values())
    return {
        "reviewed_on": config["reviewed_on"], "policy": config["policy"],
        "groups": [{"group": group, "unique_song_count": len(set().union(*credits.values())),
                    "credits": [{"credit": credit, "unique_song_count": len(songs)} for credit, songs in sorted(credits.items())]}
                   for group, credits in groups.items()],
        "excluded_credits": [{"credit": credit, "unique_song_count": len(songs)} for credit, songs in sorted(excluded.items())],
        "included_unique_songs": len(included_songs),
        "excluded_only_unique_songs": len(excluded_songs - included_songs),
        "agreement_review": config["agreement_review"],
    }


def normalize_value(value):
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    return value


def frame_to_records(frame: pl.DataFrame) -> list[dict]:
    return [{key: normalize_value(value) for key, value in row.items()} for row in frame.iter_rows(named=True)]


def build_dataset_browser_data(df: pl.DataFrame) -> dict:
    browser_frame = (
        df.select(COLUMN_NAMES + ["chart_date", "week_label"])
        .sort(["chart_date", "rank"])
    )
    return {
        "columns": browser_frame.columns,
        "rows": frame_to_records(browser_frame),
    }


def build_static_chart_data(
    song_weeks: pl.DataFrame,
    top_10_total_weeks: pl.DataFrame,
    weeks_at_number_one: pl.DataFrame,
    top_production: pl.DataFrame,
    top_distribution: pl.DataFrame,
) -> dict:
    values = song_weeks["total_weeks_on_chart"].to_numpy()
    # Integer weeks: 1–25, 26–50, etc.; every song belongs to one bin.
    bins = np.arange(1, int(values.max()) + 26, 25)
    counts, bins = np.histogram(values, bins=bins)

    return {
        "distribution": {
            "bin_width": 25,
            "bars": [
                {"start": int(bins[i]), "end": int(bins[i + 1] - 1), "count": int(count)}
                for i, count in enumerate(counts)
            ],
            "mean": round(float(np.mean(values)), 2),
            "median": round(float(np.median(values)), 2),
            "std_dev": round(float(np.std(values)), 2),
        },
        "top_total_weeks": {
            "labels": top_10_total_weeks["label"].to_list(),
            "values": [int(value) for value in top_10_total_weeks["total_weeks_on_chart"].to_list()],
        },
        "weeks_at_number_one": {
            "labels": weeks_at_number_one["label"].to_list(),
            "values": [int(value) for value in weeks_at_number_one["weeks_at_number_one"].to_list()],
        },
        "agency_bars": {
            "production": frame_to_records(top_production),
            "distribution": frame_to_records(top_distribution),
        },

    }


def build_artist_explorer_data(df: pl.DataFrame) -> dict:
    mean_rank_frame = (
        df.group_by(["year", "week", "artist"])
        .agg(
            pl.col("rank").mean().round(2).alias("mean_rank"),
            pl.struct(["rank", "song_title", "album"]).sort_by("rank").alias("songs_in_chart"),
        )
        .sort(["artist", "year", "week"])
    )

    artist_year_map: dict[str, dict[str, list[dict]]] = {}
    for row in mean_rank_frame.iter_rows(named=True):
        artist_year_map.setdefault(row["artist"], {}).setdefault(str(row["year"]), []).append(
            {
                "week": int(row["week"]),
                "mean_rank": float(row["mean_rank"]),
                "songs": [
                    {
                        "rank": int(song["rank"]),
                        "song_title": song["song_title"],
                        "album": song["album"],
                    }
                    for song in row["songs_in_chart"]
                ],
            }
        )

    return {
        "years": sorted(int(year) for year in df["year"].unique().to_list()),
        "artists": sorted(artist_year_map),
        "artist_year_map": artist_year_map,
    }


def build_song_explorer_data(df: pl.DataFrame) -> dict:
    chart_frame = (
        df.select(["artist", "song_title", "chart_date", "rank", "week_label"])
        .unique()
        .sort(["artist", "song_title", "chart_date"])
        .with_columns(pl.col("chart_date").cast(pl.Utf8))
    )

    artist_to_songs = {
        row[0]: row[1]
        for row in (
            chart_frame.group_by("artist")
            .agg(pl.col("song_title").sort().unique())
            .sort("artist")
            .iter_rows()
        )
    }

    series_map: dict[str, list[dict]] = {}
    for subset in chart_frame.partition_by(["artist", "song_title"], maintain_order=True):
        artist = subset[0, "artist"]
        song_title = subset[0, "song_title"]
        key = f"{artist}|||{song_title}"
        series_map[key] = [
            {
                "date": row[0],
                "rank": int(row[1]),
                "week_label": row[2],
            }
            for row in subset.select(["chart_date", "rank", "week_label"]).iter_rows()
        ]

    return {
        "artists": sorted(artist_to_songs),
        "artist_to_songs": artist_to_songs,
        "series_map": series_map,
    }


def build_movement_tables(df: pl.DataFrame) -> dict:
    week_lookup = (
        df.select(["year", "week", "chart_date"])
        .unique()
        .sort("chart_date")
        .with_row_index("week_index")
    )

    movement_base = (
        df.join(week_lookup, on=["year", "week", "chart_date"], how="left")
        .sort(["song_key", "chart_date", "rank"], maintain_order=True)
        .with_columns(
            pl.col("rank").shift(1).over("song_key").alias("prev_rank"),
            pl.col("week_index").shift(1).over("song_key").alias("prev_week_index"),
        )
        .with_columns(
            (pl.col("week_index") - pl.col("prev_week_index")).alias("week_gap"),
            (pl.col("prev_rank") - pl.col("rank")).alias("rank_change"),
            (pl.lit(201) - pl.col("rank")).alias("entry_improvement"),
            ((pl.col("week_index") - pl.col("prev_week_index")) == 1).fill_null(False).alias("is_consecutive"),
            (pl.col("prev_week_index").is_null() | ((pl.col("week_index") - pl.col("prev_week_index")) > 1)).alias(
                "is_entry_or_return"
            ),
        )
    )

    consecutive_climbs = movement_base.filter(pl.col("is_consecutive") & (pl.col("rank_change") > 0))
    consecutive_drops = movement_base.filter(pl.col("is_consecutive") & (pl.col("rank_change") < 0)).with_columns(
        (-pl.col("rank_change")).alias("drop_size")
    )
    years = sorted(df["year"].unique().to_list())

    def top_movements(frame: pl.DataFrame, metric: str) -> list:
        return frame_to_records(
            frame.sort([metric, "year", "week", "rank", "song_key"], descending=[True, False, False, False, False])
            .select(["year", "week", "artist", "song_title", "album", "prev_rank", "rank", metric])
            .head(50)
        )

    def bundle(year: int | None = None) -> dict:
        return {
            name: top_movements(frame if year is None else frame.filter(pl.col("year") == year), metric)
            for name, frame, metric in [
                ("climbs", consecutive_climbs, "rank_change"),
                ("drops", consecutive_drops, "drop_size"),
            ]
        }

    return {"years": years, "overall": bundle(), "yearly": {str(year): bundle(year) for year in years}}


def agency_note(frame: pl.DataFrame, column: str, label: str, transition: str) -> str:
    records = frame_to_records(frame)
    if not records:
        return f"No {label.lower()} agencies are available."
    first = records[0]
    message = f"{label} is led by {first[column]} with {first['unique_song_count']} unique charting songs"
    if len(records) >= 3:
        message += f", {transition} {records[1][column]} and {records[2][column]}"
    return message + "."


def build_site_data(rankings_path: Path = DATA_PATH, output_path: Path = DATA_DIR / "site_data.json",
                    config_dir: Path = DATA_DIR) -> dict:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = load_data(Path(rankings_path))
    if df.is_empty():
        raise ValueError("The Atlas charts require at least one public ranking row.")

    song_weeks = (
        df.group_by(["artist", "song_title"])
        .agg(pl.col("chart_date").n_unique().alias("total_weeks_on_chart"))
        .sort("total_weeks_on_chart", descending=True)
    )

    top_10_total_weeks = (
        song_weeks.head(10)
        .with_columns((pl.col("song_title") + pl.lit(" | ") + pl.col("artist")).alias("label"))
        .sort("total_weeks_on_chart")
    )

    weeks_at_number_one = (
        df.filter(pl.col("rank") == 1)
        .group_by(["artist", "song_title"])
        .len()
        .rename({"len": "weeks_at_number_one"})
        .sort("weeks_at_number_one", descending=True)
        .head(10)
        .with_columns((pl.col("song_title") + pl.lit(" | ") + pl.col("artist")).alias("label"))
        .sort("weeks_at_number_one")
    )

    production_summary = summarize_unique_songs_by_agency(df, "production_agency")
    distribution_summary = summarize_unique_songs_by_agency(df, "distribution_agency")
    top_production = production_summary.head(10)
    top_distribution = distribution_summary.head(10)

    top_artist_weeks = (
        df.group_by("artist")
        .len()
        .rename({"len": "total_chart_entries"})
        .sort("total_chart_entries", descending=True)
        .head(12)
    )

    top_agency_overview = (
        production_summary.join(
            distribution_summary,
            left_on="production_agency",
            right_on="distribution_agency",
            how="full",
        )
        .rename({"production_agency": "agency"})
        .with_columns(pl.coalesce(["agency", "distribution_agency"]).alias("agency_name"))
        .select(["agency_name", "unique_song_count", "unique_song_count_right"])
        .rename({"unique_song_count": "production_unique_songs", "unique_song_count_right": "distribution_unique_songs"})
        .fill_null(0)
        .sort("production_unique_songs", descending=True)
        .head(8)
    )

    site_data = {
        "overview": {
            "source_file": "gold.rankings",
            "week_start": df[0, "week_label"],
            "week_end": df[-1, "week_label"],
            "rows": int(df.height),
            "date_start": str(df["chart_date"].min()),
            "date_end": str(df["chart_date"].max()),
            "unique_artists": int(df["artist"].n_unique()),
            "unique_songs": int(df["song_key"].n_unique()),
            "unique_releases": int(df.select(["artist", "song_title", "album"]).unique().height),
            "years_covered": sorted(int(year) for year in df["year"].unique().to_list()),
        },
        "charts": build_static_chart_data(
            song_weeks,
            top_10_total_weeks,
            weeks_at_number_one,
            top_production,
            top_distribution,
        ),
        "highlights": {
            "top_total_weeks": frame_to_records(
                top_10_total_weeks.select(["artist", "song_title", "total_weeks_on_chart"]).sort(
                    "total_weeks_on_chart", descending=True
                )
            ),
            "top_number_one": frame_to_records(
                weeks_at_number_one.select(["artist", "song_title", "weeks_at_number_one"]).sort(
                    "weeks_at_number_one", descending=True
                )
            ),
            "top_artist_weeks": frame_to_records(top_artist_weeks),
            "agency_overview": frame_to_records(top_agency_overview),
        },
        "big_four": build_big_four_data(df, config_dir),
        "distribution_big_four": build_distribution_groups(df, config_dir),
        "agency_notes": {
            "production": agency_note(top_production, "production_agency", "Production", "ahead of"),
            "distribution": agency_note(top_distribution, "distribution_agency", "Distribution", "followed by"),
        },
        "explorers": {
            "artist_mean_rank": build_artist_explorer_data(df),
            "song_rank_history": build_song_explorer_data(df),
        },
        "movement_tables": build_movement_tables(df),
        "dataset_browser": build_dataset_browser_data(df),
    }

    output_path.write_text(json.dumps(site_data, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return site_data


if __name__ == "__main__":
    result = build_site_data()
    print(f"Atlas chart data: {result['overview']['rows']:,} Gold ranking rows")
