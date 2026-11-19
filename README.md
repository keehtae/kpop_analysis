# kpop_analysis

Run the layers in order:

```sh
python3 bronze.py
python3 silver.py
python3 gold.py
```

The database is `data/Final_Project.duckdb`. Dependencies are `duckdb`,
`playwright` (Bronze), `PyYAML` and `openpyxl` (Silver).

`silver.py` rebuilds the artist-filtered chart tables, then calls
`joined.run_joined()` using `silver.rankings`. The join preserves the supplied
script's matching rules, verified recording links, saved review approvals,
weekly score pivot, duplicate handling and explicit removals. Blank scores stay
NULL and zero scores stay zero. Failed Essentia analyses do not become matches.

Titles with producer credits (`Prod.` or `Produced by`, case insensitive) are
flagged `production_credit` in `quarantine.rankings` before joining. These songs
are excluded from Silver, Gold and the join's unavailable list. This checks the
song title, not the chart's ordinary production-company column.

The join writes these tables:

| Table | Contents |
| --- | --- |
| `silver.essentia_and_rankings` | Final `joined` tab columns and rows |
| `quarantine.joined_review` | Review candidates with reasons, features and weekly scores |
| `quarantine.joined_unavailable` | Unavailable song, artist and album |
| `quarantine.joined_removed` | All four removed-tab sections, identified by `category`; preserves duplicate `action`, row numbers, score notes and section notes |
| `gold.essentia_and_rankings` | Silver joined rows with `chart_song` through `filename` removed, inclusively |

There is no shared `quarantine.joined` table or extra status column: each
quarantine table identifies its own review state. The removed audit includes
both kept and removed duplicate entries, as in the original workbook.

The latest timestamped full Essentia summary is selected from `data/`,
`v2_results/`, or `~/Capstone test/v2_results/`. By default, mapping workbooks and
existing review approvals are read from the Essentia project at
`~/Capstone test`. Input workbooks and approvals are never modified.

Override the source locations as needed:

```sh
python3 silver.py --essentia-root "/path/to/Essentia project"
python3 silver.py --summary /path/to/all_songs_summary.xlsx --itunes /path/to/batch1_data_itunes_matches.xlsx --approvals-file /path/to/joined_review_approvals.json
```

To reproduce the chart population of the original workbook instead of using
the filtered `silver.rankings`, supply `--chart /path/to/artists_cleaned.csv`.
To rebuild only the join tables after Silver rankings already exist, run
`python3 joined.py` with the same source options. Rerun `python3 gold.py` after
each Silver refresh to update Gold. Table replacements within each layer are
transactional, so a failed build keeps the previous tables.
