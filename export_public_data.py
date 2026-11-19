"""Export only the two Gold tables for GitHub Pages, omitting local paths.

Run directly, or use: python3 gold.py --export-public
Change public_export.json to hide additional columns from future exports.
The database and its internal tables are never copied into the website.
"""

import argparse
from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
import re
import tempfile

import duckdb


ROOT = Path(__file__).resolve().parent
PUBLIC_TABLES = ("gold.rankings", "gold.essentia_and_rankings")
LOCAL_PATH = re.compile(
    r"(?:file://)?(?:/(?:Users|home|private|tmp|var|Volumes|mnt)/|[A-Za-z]:[\\/]|\\\\)"
    r"[^\r\n\"'<>]*"
)


def quote_identifier(value):
    return '"' + value.replace('"', '""') + '"'


def public_value(value):
    if isinstance(value, str):
        return LOCAL_PATH.sub("[local path omitted]", value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def export_public_data(connection, output_dir=None, config_path=None):
    output_dir = Path(output_dir or ROOT / "docs/data")
    config_path = Path(config_path or ROOT / "public_export.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if set(config) != {"exclude_columns"} or not isinstance(config["exclude_columns"], dict):
        raise ValueError("Public export config must contain an exclude_columns mapping.")
    exclusions = config["exclude_columns"]
    if set(exclusions) != set(PUBLIC_TABLES):
        raise ValueError("Public export config must list exactly the two approved Gold tables.")
    if any(not isinstance(items, list) or any(not isinstance(item, str) for item in items)
           for items in exclusions.values()):
        raise ValueError("Each exclude_columns entry must be a list of column names.")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    manifest = {"format_version": 1, "tables": []}
    # Prepare both files before replacing any existing public export.
    with tempfile.TemporaryDirectory(prefix="public-export-", dir=output_dir.parent) as temporary:
        staging = Path(temporary)
        for table in PUBLIC_TABLES:
            schema, name = table.split(".")
            columns = [row[0] for row in connection.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = ? AND table_name = ? ORDER BY ordinal_position",
                [schema, name],
            ).fetchall()]
            if not columns:
                raise ValueError(f"Missing {table}. Run silver.py and gold.py first.")
            unknown = set(exclusions[table]) - set(columns)
            if unknown:
                raise ValueError(f"Unknown excluded columns for {table}: {', '.join(sorted(unknown))}")
            # Local filesystem path columns are always excluded, even if the
            # editable config is accidentally changed to include them.
            omitted = [column for column in columns if column in exclusions[table]
                       or column.casefold() in {"path", "paths", "filepath", "localpath"}
                       or column.casefold().endswith(("_path", "_paths"))]
            included = [column for column in columns if column not in omitted]
            if not included:
                raise ValueError(f"No public columns remain for {table}.")
            projection = ", ".join(quote_identifier(column) for column in included)
            records = connection.execute(
                f"SELECT {projection} FROM {quote_identifier(schema)}.{quote_identifier(name)} ORDER BY ALL"
            ).fetchall()
            filename = f"{name}.json"
            payload = {"table": table, "columns": included,
                       "rows": [[public_value(value) for value in row] for row in records]}
            (staging / filename).write_text(
                json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            manifest["tables"].append({"table": table, "file": filename, "row_count": len(records),
                                       "column_count": len(included), "excluded_columns": omitted})
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        for item in manifest["tables"]:
            (staging / item["file"]).replace(output_dir / item["file"])
        (staging / "manifest.json").replace(output_dir / "manifest.json")
    for item in manifest["tables"]:
        print(f"Public {item['table']}: {item['row_count']:,} rows, {item['column_count']} columns")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "data/Final_Project.duckdb")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/data")
    parser.add_argument("--config", type=Path, default=ROOT / "public_export.json")
    args = parser.parse_args(argv)
    if not args.database.is_file():
        parser.error(f"Database not found: {args.database}")
    try:
        with duckdb.connect(str(args.database), read_only=True) as connection:
            export_public_data(connection, args.output, args.config)
    except (ValueError, duckdb.Error) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
