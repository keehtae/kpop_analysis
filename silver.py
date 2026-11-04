"""Filter bronze rankings to the artists listed in artists.csv.
Save the matching rows to silver.rankings in data/Final_Project.duckdb.
"""

from pathlib import Path

import duckdb


def build_rankings(connection, artists_path):
    connection.execute("CREATE SCHEMA IF NOT EXISTS silver")
    connection.execute(
        """
        CREATE OR REPLACE TABLE silver.rankings AS
        SELECT *
        FROM bronze.rankings
        WHERE artist IN (
            SELECT artist FROM read_csv(?, header = true, all_varchar = true)
        )
        """,
        [str(artists_path)],
    )
    count = connection.execute("SELECT COUNT(*) FROM silver.rankings").fetchone()[0]
    print(f"Wrote {count} rows to silver.rankings")


def main():
    base_dir = Path(__file__).resolve().parent
    database_path = base_dir / "data" / "Final_Project.duckdb"
    if not database_path.is_file():
        raise FileNotFoundError(f"Run bronze.py first to create {database_path}")
    with duckdb.connect(str(database_path)) as connection:
        build_rankings(connection, base_dir / "artists.csv")


if __name__ == "__main__":
    main()
