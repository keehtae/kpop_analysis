"""Exercise the join against small workbooks and an isolated DuckDB database."""

import json
import tempfile
import unittest
from pathlib import Path

import duckdb
from openpyxl import Workbook

from gold import run_gold
from joined import run_joined
from silver import run_silver


class JoinedPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.connection = duckdb.connect()
        self.addCleanup(self.connection.close)
        self.connection.execute("CREATE SCHEMA bronze")
        self.connection.execute(
            "CREATE TABLE bronze.rankings (year VARCHAR, time VARCHAR, rank VARCHAR, "
            "song_title VARCHAR, artist VARCHAR, album VARCHAR, score VARCHAR)"
        )
        for table in ("social_score", "album_sales"):
            self.connection.execute(f"CREATE TABLE bronze.{table} AS SELECT 'Band' AS artist")
        self.artists = self.root / "artists.csv"
        self.artists.write_text('artist\nBand\ni-dle (아이들)\n', encoding="utf-8")
        self.summary = self.root / "summary.xlsx"
        self.approvals = self.root / "approvals.json"
        self.approvals.write_text('{"version": 1, "approvals": []}')

    def write_summary(self, records):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Summary"
        self.headers = ["filename", "artist", "album", "song", "file_path", "status", "duration_sec"]
        sheet.append(self.headers)
        for record in records:
            sheet.append(record)
        workbook.save(self.summary)
        workbook.close()

    def record(self, song, album, filename, artist="Band", status="success"):
        return [filename, artist, album, song, str(self.root / filename), status, 180.5]

    def insert_rankings(self, records):
        self.connection.executemany("INSERT INTO bronze.rankings VALUES (?, ?, ?, ?, ?, ?, ?)", records)

    def silver(self):
        run_silver(
            self.connection, self.artists, Path(__file__).resolve().parents[1] / "quality_rules.yml",
            essentia_root=self.root, summary_path=self.summary, itunes_paths=[], approvals_file=self.approvals,
        )

    def test_silver_join_quarantine_and_gold(self):
        self.write_summary([
            self.record("Exact", "One", "exact.m4a"),
            self.record("Replay", "Release A", "a.m4a"),
            self.record("Replay", "Release B", "b.m4a"),
            self.record("Conflict", "Two", "conflict.m4a"),
            self.record("Version", "Three", "version.m4a"),
            self.record("Failed", "Four", "failed.m4a", status="failed"),
            self.record("Last Dance (Prod. GroovyRoom)", "Last Dance (Prod. GroovyRoom)",
                        "removed.m4a", artist="i-dle (아이들)"),
            self.record("Local Title", "Local Album", "manual.m4a"),
        ])
        self.insert_rankings([
            ("2020", "01", "1", "Exact", "Band", "One", "0"),
            ("2020", "02", "1", "Exact", "Band", "One", ""),
            ("2020", "01", "2", "Replay", "Band", "Release A", "5"),
            ("2020", "02", "2", "Replay", "Band", "Release B", "6"),
            ("2020", "01", "3", "Conflict", "Band", "Two", "7"),
            ("2020", "01", "3", "Conflict", "Band", "Two", "8"),
            ("2020", "01", "4", "Version (Live)", "Band", "Three", "9"),
            ("2020", "01", "5", "Absent", "Band", "Missing", "10"),
            ("2020", "01", "6", "Failed", "Band", "Four", "11"),
            ("2020", "01", "7", "Last Dance (Prod. GroovyRoom)", "i-dle (아이들)",
             "Last Dance (Prod. GroovyRoom)", "12"),
            ("2020", "01", "8", "Chart Title", "Band", "Chart Album", "13"),
        ])
        decision = dict(chart_song="Chart Title", chart_artist="Band", chart_album="Chart Album",
                        song="Local Title", artist="Band", album="Local Album",
                        file_path=str(self.root / "manual.m4a"), review_reason="Checked by user")
        self.approvals.write_text(json.dumps({"version": 1, "approvals": [decision]}))
        before = (self.summary.read_bytes(), self.approvals.read_bytes())
        self.silver()
        self.assertEqual(before, (self.summary.read_bytes(), self.approvals.read_bytes()))
        self.assertEqual(self.connection.execute(
            'SELECT chart_song, "20_01", "20_02" FROM silver.essentia_and_rankings ORDER BY chart_song'
        ).fetchall(), [("Chart Title", 13, None), ("Exact", 0, None), ("Replay", 5, 6)])
        reviews = self.connection.execute(
            'SELECT chart_song, review_reason, "20_01" FROM quarantine.joined_review ORDER BY chart_song'
        ).fetchall()
        self.assertEqual([row[0] for row in reviews], ["Conflict", "Version (Live)"])
        self.assertIn("Conflicting popularity scores", reviews[0][1])
        self.assertIsNone(reviews[0][2])
        self.assertEqual(self.connection.execute(
            "SELECT song FROM quarantine.joined_unavailable ORDER BY song"
        ).fetchall(), [("Absent",), ("Failed",)])
        self.assertEqual(self.connection.execute(
            "SELECT action FROM quarantine.joined_removed WHERE category = 'Duplicates' ORDER BY row_number"
        ).fetchall(), [("kept",), ("removed",)])
        self.assertEqual(self.connection.execute(
            "SELECT category FROM quarantine.joined_removed WHERE chart_song = 'Last Dance (Prod. GroovyRoom)'"
        ).fetchone(), ("prod",))
        silver_columns = [column[0] for column in self.connection.execute(
            "DESCRIBE silver.essentia_and_rankings"
        ).fetchall()]
        self.assertEqual(run_gold(self.connection), 3)
        gold_columns = [column[0] for column in self.connection.execute(
            "DESCRIBE gold.essentia_and_rankings"
        ).fetchall()]
        self.assertEqual(gold_columns, silver_columns[silver_columns.index("filename") + 1:])
        self.assertEqual(self.connection.execute(
            'SELECT song, duration_sec, "20_01", "20_02" FROM gold.essentia_and_rankings ORDER BY song'
        ).fetchall(), [("Exact", 180.5, 0, None), ("Local Title", 180.5, 13, None), ("Replay", 180.5, 5, 6)])
        # An unsuccessful join must roll back the artist-table rebuild too.
        self.connection.execute("UPDATE bronze.rankings SET artist = 'Unlisted'")
        self.summary.write_bytes(b"not a workbook")
        with self.assertRaises(Exception):
            self.silver()
        self.assertEqual(self.connection.execute("SELECT count(*) FROM silver.rankings").fetchone()[0], 10)
        self.assertEqual(self.connection.execute("SELECT count(*) FROM silver.essentia_and_rankings").fetchone()[0], 3)

    def test_production_credits_are_quarantined_before_matching(self):
        credited = ["To Me From Me (Prod. TABLO)", "Bad Influence (Prod. by Pharrell Williams)",
                    "SOS (Prod. Marshmello)", "A Song (Produced by Someone)"]
        ordinary = ["Prodigy", "Production Line"]
        titles = credited + ordinary
        self.write_summary([self.record(title, "Album", f"{i}.m4a") for i, title in enumerate(titles)])
        self.insert_rankings([
            ("2020", "01", str(i + 1), title, "Band", "Album", "1") for i, title in enumerate(titles)
        ])
        self.silver()
        self.assertEqual(self.connection.execute(
            "SELECT song_title, quality_flag FROM quarantine.rankings ORDER BY song_title"
        ).fetchall(), [(title, "production_credit") for title in sorted(credited)])
        for table in ("silver.rankings", "silver.essentia_and_rankings"):
            column = "song_title" if table.endswith(".rankings") else "chart_song"
            self.assertEqual(self.connection.execute(
                f"SELECT {column} FROM {table} ORDER BY {column}"
            ).fetchall(), [(title,) for title in sorted(ordinary)])
        self.assertEqual(self.connection.execute(
            "SELECT count(*) FROM quarantine.joined_unavailable"
        ).fetchone()[0], 0)

    def test_empty_rankings_replace_old_results_with_empty_tables(self):
        self.write_summary([self.record("Exact", "One", "exact.m4a")])
        self.insert_rankings([("2020", "01", "1", "Exact", "Band", "One", "1")])
        self.silver()
        self.connection.execute("DELETE FROM bronze.rankings")
        self.silver()
        for table in ("silver.essentia_and_rankings", "quarantine.joined_review", "quarantine.joined_unavailable"):
            self.assertEqual(self.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0], 0)
        self.assertEqual(run_gold(self.connection), 0)

    def test_original_headerless_csv_keeps_first_song_and_week_53(self):
        self.write_summary([self.record("Exact", "One", "exact.m4a")])
        chart = self.root / "chart.csv"
        chart.write_text("20,53,1,Exact,Band,One,0,label,distributor\n")
        counts = run_joined(self.connection, summary_path=self.summary, itunes_paths=[],
                            approvals_file=self.approvals, essentia_root=self.root, chart_path=chart)
        self.assertEqual(counts["silver.essentia_and_rankings"], 1)
        self.assertEqual(self.connection.execute(
            'SELECT "20_53" FROM silver.essentia_and_rankings'
        ).fetchone(), (0,))


if __name__ == "__main__":
    unittest.main()
