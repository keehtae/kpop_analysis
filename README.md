# kpop_analysis

Run the layers in order:

```sh
python3 bronze.py
python3 silver.py
python3 gold.py
```

The database is `data/Final_Project.duckdb`. Dependencies are `duckdb`,
`playwright` (Bronze), `PyYAML` and `openpyxl` (Silver), and `numpy` and `polars`
for the public website's chart-data build.

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
| `gold.rankings` | Unchanged copy of `silver.rankings` |

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

## GitHub Pages

The website lives in `docs/`. Its data comes only from `gold.rankings` and
`gold.essentia_and_rankings`. The DuckDB file, Bronze, Silver, quarantine and
input workbooks are not copied into that folder or uploaded by the Pages workflow.
Every file in the deployed website, including its JSON datasets, is public.
The website is a copy of the original K-pop Data Atlas: Home, Exploratory,
Models, Music and Methodology. The HTML pages, CSS, JavaScript, audio-feature
dictionary and agency mapping files were copied without content or styling
changes. The original local website folder is unchanged and is not required
to run or update this copy.

`build_site_data.py` retains the original chart calculations and builds their
expected `site_data.json` structure from the public `gold.rankings` export.
It maps `time` to `week`, `production` to `production_agency`, and `distribution`
to `distribution_agency`. The copied pages retain their original written content,
including references to the original CSV; displayed chart results use Gold data.

### Refresh the public data

Close any open DuckDB connection, then run:

```sh
python3 silver.py
python3 gold.py --export-public
```

To export already-built Gold tables without rebuilding them:

```sh
python3 export_public_data.py
```

These commands produce four files to commit:

- `docs/data/rankings.json`
- `docs/data/essentia_and_rankings.json`
- `docs/data/manifest.json`
- `docs/data/site_data.json` (the copied Atlas charts, derived from public rankings)

The two dataset files contain `columns` and `rows`; each row is an array in
column order. All Gold columns are included except local filesystem path
columns. NULL and numeric zero are preserved. Local paths embedded in text,
such as an error message, are redacted. The manifest gives each dataset's
row/column counts and omitted columns, without including the database location.

To hide additional columns later, add their exact names to the corresponding
list in `public_export.json`, rerun the exporter, and commit the refreshed files.
Removing a column in a later release does not erase earlier Git history or
copies that visitors already downloaded. Local path columns are always omitted,
even if removed from the configuration's exclusion list.

The Atlas charts require all nine original ranking columns. If you exclude one
of those columns, the public export stops with an error rather than publishing
an incomplete chart dataset. To rebuild only the Atlas chart data from already
exported rankings, run `python3 build_site_data.py`.

### Enable GitHub Pages

1. Review the contents of `docs/data/`. Only commit data you intend to make public.
2. Commit and push the new website, public export settings and code to `main`.
3. In the GitHub repository, open **Settings → Pages** and set **Build and
   deployment → Source → GitHub Actions**.
4. Open **Actions → Publish GitHub Pages → Run workflow**, select `main`, and
   run it. Later pushes changing `docs/` deploy automatically.
5. Open the deployment URL from the workflow. For this repository, the expected
   default URL is `https://keehtae.github.io/kpop_analysis/`.

The workflow uploads **only `docs/`**, using `actions/upload-pages-artifact`.
It uses the normal GitHub Actions token and does not need a personal access token.
Gold exports are generated locally and committed; Actions does not need access
to your database or Essentia files.

GitHub Pages works with public repositories on GitHub Free. Publishing from a
private repository requires a supported paid plan; the published site is normally
public even when its source repository is private. Keeping the repository private
does not require publishing its database or internal tables.

The old root-level `Final_Project.duckdb` file is already tracked in Git (it is
currently empty). The expanded `.gitignore` prevents new database files from being
added but does not untrack files already committed. To stop tracking the old file
while keeping the local copy, run:

```sh
git rm --cached Final_Project.duckdb
```

Do not add the repository root as the Pages artifact. Files already committed to
a public repository remain accessible from Git history even if not deployed.

### Preview locally

```sh
python3 -m http.server 8000 --directory docs
```

Open `http://localhost:8000`. Use the HTTP server instead of opening `index.html`
directly, so the browser can fetch the JSON datasets.

GitHub references: [About Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages),
[publishing source](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site),
and [custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
