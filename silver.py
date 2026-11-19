"""Check bronze artist data, join Essentia features and rebuild Silver/quarantine.
Keep reviewed artist corrections in the database for later runs.
"""

import argparse
from pathlib import Path

import duckdb

from joined import add_join_arguments, join_options, run_joined
from quality import apply_quality_rules, load_rules


TABLES = ("rankings", "social_score", "album_sales")


def review_row(connection, action, review, artist=None):
    table, row_id = review
    if table not in TABLES:
        raise ValueError(f"Unknown table: {table}")
    if action == "revoke":
        removed = connection.execute(
            "DELETE FROM quarantine.approvals WHERE table_name = ? AND quarantine_id = ? RETURNING quarantine_id",
            [table, row_id],
        ).fetchone()
        if removed is None:
            raise ValueError("No matching approval was found.")
        return

    if connection.execute("SELECT 1 FROM artist_list WHERE artist = ?", [artist]).fetchone() is None:
        raise ValueError("The approved artist must be listed exactly in artists.csv.")
    if connection.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = 'quarantine' AND table_name = ?",
        [table],
    ).fetchone() is None:
        raise ValueError("Run silver.py first to build the quarantine tables.")
    if connection.execute(
        f'SELECT 1 FROM quarantine."{table}" WHERE quarantine_id = ?', [row_id]
    ).fetchone() is None:
        raise ValueError("No matching quarantined row was found.")
    if connection.execute(
        f'SELECT 1 FROM bronze."{table}" source WHERE sha256(to_json(source)) = ?', [row_id]
    ).fetchone() is None:
        raise ValueError("The bronze row has changed or disappeared. Rerun silver.py before reviewing it.")
    connection.execute(
        "INSERT OR REPLACE INTO quarantine.approvals (table_name, quarantine_id, artist) VALUES (?, ?, ?)",
        [table, row_id, artist],
    )


def build_table(connection, table, rules):
    columns = [row[0] for row in connection.execute(f'DESCRIBE bronze."{table}"').fetchall()]
    title = "coalesce(source.song_title, '')" if "song_title" in columns else "''"
    connection.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE source_rows AS
        SELECT source.*, sha256(to_json(source)) AS quarantine_id, {title} AS _title
        FROM bronze."{table}" source
        """
    )
    apply_quality_rules(connection, rules)
    connection.execute(
        """
        CREATE OR REPLACE TEMP TABLE reviewed_rows AS
        SELECT flagged.* REPLACE (coalesce(approvals.artist, flagged.artist) AS artist),
               approvals.quarantine_id IS NOT NULL AS _approved
        FROM flagged_rows flagged
        LEFT JOIN quarantine.approvals approvals
          ON approvals.table_name = ? AND approvals.quarantine_id = flagged.quarantine_id
         AND approvals.artist IN (SELECT artist FROM artist_list)
        """,
        [table],
    )
    connection.execute(
        f"""
        CREATE OR REPLACE TABLE silver."{table}" AS
        SELECT * EXCLUDE (quarantine_id, _title, quality_flag, _approved)
        FROM reviewed_rows WHERE quality_flag IS NULL OR _approved
        """
    )
    connection.execute(
        f"""
        CREATE OR REPLACE TABLE quarantine."{table}" AS
        SELECT * EXCLUDE (_title, _approved)
        FROM reviewed_rows WHERE quality_flag IS NOT NULL AND NOT _approved
        """
    )
    return tuple(
        connection.execute(f'SELECT count(*) FROM {schema}."{table}"').fetchone()[0]
        for schema in ("silver", "quarantine")
    )


def run_silver(connection, artists_path, rules_path, approve=None, artist=None, revoke=None,
               **joined_options):
    rules = load_rules(rules_path)
    connection.execute("BEGIN TRANSACTION")
    try:
        connection.execute(
            "CREATE OR REPLACE TEMP TABLE artist_list AS "
            "SELECT DISTINCT artist FROM read_csv(?, header = true, all_varchar = true) "
            "WHERE artist IS NOT NULL AND trim(artist) != ''",
            [str(artists_path)],
        )
        if connection.execute("SELECT count(*) FROM artist_list").fetchone()[0] == 0:
            raise ValueError("artists.csv must contain at least one artist.")
        for schema in ("silver", "quarantine"):
            connection.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS quarantine.approvals (
                table_name VARCHAR,
                quarantine_id VARCHAR,
                artist VARCHAR NOT NULL,
                approved_at TIMESTAMP DEFAULT current_timestamp,
                PRIMARY KEY (table_name, quarantine_id)
            )
            """
        )
        if approve:
            review_row(connection, "approve", approve, artist)
        if revoke:
            review_row(connection, "revoke", revoke)
        counts = {table: build_table(connection, table, rules) for table in TABLES}
        joined_counts = run_joined(connection, **joined_options)
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    for table, (valid, quarantined) in counts.items():
        print(f"{table}: {valid} silver, {quarantined} quarantine")
    for table, count in joined_counts.items():
        print(f"{table}: {count:,} rows")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    reviews = parser.add_mutually_exclusive_group()
    reviews.add_argument("--approve", nargs=2, metavar=("TABLE", "ID"), help="Approve one quarantined row.")
    reviews.add_argument("--revoke", nargs=2, metavar=("TABLE", "ID"), help="Revoke one saved approval.")
    parser.add_argument("--artist", help="Exact artist from artists.csv for the approved row.")
    add_join_arguments(parser)
    args = parser.parse_args(argv)
    if bool(args.approve) != (args.artist is not None):
        parser.error("Use --approve TABLE ID together with --artist NAME.")
    base_dir = Path(__file__).resolve().parent
    database_path = base_dir / "data" / "Final_Project.duckdb"
    if not database_path.is_file():
        raise FileNotFoundError(f"Run bronze.py first to create {database_path}")
    with duckdb.connect(str(database_path)) as connection:
        try:
            run_silver(
                connection, base_dir / "artists.csv", base_dir / "quality_rules.yml",
                args.approve, args.artist, args.revoke,
                **join_options(args),
            )
        except ValueError as exc:
            parser.error(str(exc))


if __name__ == "__main__":
    main()
