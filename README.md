# kpop_analysis

Run the layers in order:

```sh
python3 -m pipeline.Bronze.bronze
python3 -m pipeline.Silver.silver
python3 -m pipeline.Gold.gold
```

The database is `data/Final_Project.duckdb`. Dependencies are `duckdb`,
`playwright` (Bronze), `PyYAML` and `openpyxl` (Silver), and the packages in
`clustering/requirements.txt` for the public website's chart-data build.

This repository follows medallion architecture to retrieve, clean, and 
prepare the data for analysis.

`silver.py` rebuilds the artist-filtered chart tables, then calls
`joined.run_joined()` using `silver.rankings`. `joined()` combines the data 
from Melon and the audio outputs from essentia by widening the data. This
combined output is saved in `gold.essentia_and_rankings` within the database
and is also viewable in this repository.

The join writes these tables:

| Table | Contents |
| --- | --- |
| `silver.essentia_and_rankings` | Final `joined` tab columns and rows |
| `quarantine.joined_review` | Review candidates with reasons, features and weekly scores |
| `quarantine.joined_unavailable` | Unavailable song, artist and album |
| `quarantine.joined_removed` | All four removed-tab sections, identified by `category`; preserves duplicate `action`, row numbers, score notes and section notes |
| `gold.essentia_and_rankings` | Silver joined rows with `chart_song` through `filename` removed, inclusively |
| `gold.rankings` | Unchanged copy of `silver.rankings` |

## GitHub Pages

The website lives in `docs/`. Its data comes only from `gold.rankings` and
`gold.essentia_and_rankings`. The DuckDB file, Bronze, Silver, quarantine and
input workbooks are not copied into that folder or uploaded by the Pages workflow.
Every file in the deployed website, including its JSON datasets, is public.

### Refresh the public data

Close any open DuckDB connection, then run:

```sh
python3 -m pipeline.Silver.silver
python3 -m pipeline.Gold.gold --export-public
```

To export already-built Gold tables without rebuilding them:

```sh
python3 export_public_data.py
