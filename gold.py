"""Rebuild gold.essentia_and_rankings, dropping chart_song through filename.

The range is inclusive and follows the Silver table's column order.
Run after silver.py: python3 gold.py
"""

import argparse
from pathlib import Path

import duckdb


def run_gold(connection):
    columns = [row[0] for row in connection.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'silver' AND table_name = 'essentia_and_rankings' "
        "ORDER BY ordinal_position"
    ).fetchall()]
    if not columns:
        raise ValueError("Run silver.py first to build silver.essentia_and_rankings.")
    if "chart_song" not in columns or "filename" not in columns:
        raise ValueError("Silver's essentia_and_rankings must contain chart_song and filename.")
    first, last = columns.index("chart_song"), columns.index("filename")
    if first > last:
        raise ValueError("chart_song must precede filename in Silver's column order.")
    retained = columns[:first] + columns[last + 1:]
    if not retained:
        raise ValueError("Dropping chart_song through filename would leave no Gold columns.")
    projection = ", ".join('"' + column.replace('"', '""') + '"' for column in retained)
    connection.execute("BEGIN TRANSACTION")
    try:
        connection.execute("CREATE SCHEMA IF NOT EXISTS gold")
        connection.execute(
            f"CREATE OR REPLACE TABLE gold.essentia_and_rankings AS "
            f"SELECT {projection} FROM silver.essentia_and_rankings"
        )
        count = connection.execute("SELECT count(*) FROM gold.essentia_and_rankings").fetchone()[0]
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    print(f"gold.essentia_and_rankings: {count:,} rows; dropped {', '.join(columns[first:last + 1])}")
    return count


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path,
                        default=Path(__file__).resolve().parent / "data/Final_Project.duckdb")
    args = parser.parse_args(argv)
    if not args.database.is_file():
        parser.error(f"Run silver.py first to create {args.database}")
    with duckdb.connect(str(args.database)) as connection:
        try:
            run_gold(connection)
        except ValueError as exc:
            parser.error(str(exc))


if __name__ == "__main__":
    main()
