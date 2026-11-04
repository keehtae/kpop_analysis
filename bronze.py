"""Scrape weekly Circle Chart digital, Social Chart 3.0, and retail album data.
Save each chart to a separate bronze table in data/Final_Project.duckdb.
"""

import time
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path

import duckdb
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright


BASE_URL = "https://circlechart.kr"
DIGITAL_URL = f"{BASE_URL}/page_chart/onoff.circle?serviceGbn=ALL"
DATE_SELECT_SELECTOR = (
    "xpath=/html/body/div/main[2]/div/div/aside[4]/section/div[2]/label/select"
)
DETAIL_ROWS_SELECTOR = "xpath=/html/body/div/main[2]/div/div/aside[5]/table/tbody/tr"
DETAIL_FIELDS = {
    "score": "xpath=td[4]/span",
    "production": "xpath=td[5]/div[1]/span",
    "distribution": "xpath=td[5]/div[2]/span",
}
FIELDNAMES = {
    "digital": [
        "year", "time", "rank", "song_title", "artist", "album",
        "score", "production", "distribution",
    ],
    "social": [
        "year", "time", "rank", "artist", "score", "highest_score", "percent_change",
    ],
    "retail": ["year", "time", "rank", "album", "artist", "sales", "distribution"],
}
MAX_RETRIES_PER_WEEK = 5
RETRY_DELAY_SECONDS = 2
API_ROWS_PER_WEEK = 50


@dataclass(frozen=True)
class WeekTarget:
    year: int
    week: int
    value: str


def iter_week_values(start_year, end_year, start_week, end_week, max_week=53):
    for year in range(start_year, end_year + 1):
        first = start_week if year == start_year else 1
        last = end_week if year == end_year else max_week
        for week in range(first, last + 1):
            yield year, week


def text_or_empty(locator):
    return locator.first.inner_text().strip() if locator.count() else ""


def scrape_digital_week(page, target):
    select = page.locator(DATE_SELECT_SELECTOR)
    option = select.locator(f"option[value='{target.value}']")
    if not option.count():
        return []

    week = option.first.inner_text().strip()[-3:-1]
    select.select_option(target.value)
    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except PlaywrightTimeoutError:
        pass
    page.locator("span.text-2xl").first.wait_for(timeout=10_000)

    rows = []
    rank_nodes = page.locator("span.text-2xl")
    detail_rows = page.locator(DETAIL_ROWS_SELECTOR)
    for i in range(rank_nodes.count()):
        rank_node = rank_nodes.nth(i)
        row_root = rank_node.locator(
            "xpath=ancestor::*[.//div[contains(@class,'ml-6')]][1]"
        )
        meta = text_or_empty(row_root.locator("div.text-sm.text-gray-400.font-bold"))
        artist, _, album = meta.partition("|")
        rows.append({
            "year": str(target.year),
            "time": week,
            "rank": rank_node.inner_text().strip(),
            "song_title": text_or_empty(row_root.locator("div.font-bold.mb-2")),
            "artist": artist.strip(),
            "album": album.strip(),
            **{
                field: text_or_empty(detail_rows.nth(i).locator(selector))
                for field, selector in DETAIL_FIELDS.items()
            },
        })
    return rows


def request_json(request, endpoint, form=None):
    response = request.get(endpoint) if form is None else request.post(endpoint, form=form)
    if not response.ok:
        raise RuntimeError(f"Request to {endpoint} failed with HTTP {response.status}.")
    payload = response.json()
    if payload.get("ResultStatus") != "OK":
        raise RuntimeError(f"Request to {endpoint} did not return ResultStatus=OK.")
    return payload


def display_year_for_week(week_start, week):
    year = int(week_start[:4])
    month = int(week_start[4:6])
    if month == 12 and week == 1:
        return year + 1
    if month == 1 and week >= 52:
        return year - 1
    return year


def build_week_lookup(request, chart):
    if chart == "social":
        payload = request_json(request, "/data/api/chart_func/social/v3/datelist?date_type=week")
    else:
        payload = request_json(request, "/data/api/chart_func/retail/datelist", {"termGbn": "week"})

    lookup = {}
    for row in payload["List"].values():
        if chart == "social":
            value = str(row["period_key"])
            year, week = int(value[:4]), int(value[4:6])
        else:
            value = row["WeekStart"]
            week = int(row["WeekNum"])
            year = display_year_for_week(value, week)
        lookup[(year, week)] = WeekTarget(year, week, value)
    return lookup


def resolve_week_targets(lookup, chart, start_year, end_year, start_week, end_week):
    if chart == "social":
        if (start_year, start_week) < (2025, 31):
            print(f"Clamping start from {start_year}-W{start_week:02d} to 2025-W31.")
            start_year, start_week = 2025, 31
        if end_year is None or end_week is None:
            end_year, end_week = max(lookup)

    if (end_year, end_week) < (start_year, start_week):
        raise RuntimeError("End week must be the same as or after the start week.")

    targets, missing = [], []
    for key in iter_week_values(start_year, end_year, start_week, end_week):
        if key in lookup:
            targets.append(lookup[key])
        else:
            missing.append(f"{key[0]}-W{key[1]:02d}")
    if missing:
        print(f"Skipping unavailable {chart} weeks: {', '.join(missing)}")
    if not targets:
        raise RuntimeError(f"No matching {chart} chart weeks were found.")
    return targets


def normalize_score(value):
    return "" if value in (None, "") else str(int(float(value)))


def scrape_api_week(request, chart, target):
    if chart == "social":
        payload = request_json(
            request, f"/data/api/chart/social/v3?date_type=week&period_key={target.value}"
        )
        if payload.get("Message") or payload.get("TotalCount", 0) == 0:
            reason = payload.get("Message", "No data returned for this week.")
            print(f"Skipping social {target.year}-W{target.week:02d}: {reason}")
            return []
    else:
        payload = request_json(
            request, "/data/api/chart/retail_list",
            {"termGbn": "week", "yyyymmdd": target.value},
        )

    raw_rows = [row for _, row in sorted(payload["List"].items(), key=lambda item: int(item[0]))]
    if len(raw_rows) != API_ROWS_PER_WEEK:
        raise RuntimeError(
            f"Expected {API_ROWS_PER_WEEK} rows for {chart} {target.year}-W{target.week:02d}, "
            f"got {len(raw_rows)}."
        )

    rows = []
    for row in raw_rows:
        if chart == "social":
            fields = {
                "rank": str(row["rank"]).strip(),
                "artist": str(row["artist_name"]).strip(),
                "score": normalize_score(row.get("score")),
                "highest_score": normalize_score(row.get("cumulative_score")),
                "percent_change": str(row.get("diff_score_percent", "")).strip(),
            }
        else:
            fields = {
                field: str(row[key]).strip()
                for field, key in {
                    "rank": "RankInt", "album": "Album", "artist": "Artist",
                    "sales": "rowSum", "distribution": "De_company_name",
                }.items()
            }
        rows.append({"year": str(target.year), "time": f"{target.week:02d}", **fields})
    return rows


@contextmanager
def open_source(playwright, chart):
    if chart == "digital":
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(DIGITAL_URL, wait_until="domcontentloaded", timeout=30_000)
            yield page
        finally:
            browser.close()
    else:
        request = playwright.request.new_context(base_url=BASE_URL)
        try:
            yield request
        finally:
            request.dispose()


def write_week(connection, table, fields, target, rows):
    if not rows:
        return
    values = [[row[field] for field in fields] for row in rows]
    columns = ", ".join(f'"{field}"' for field in fields)
    placeholders = ", ".join("?" for _ in fields)
    connection.execute("BEGIN TRANSACTION")
    try:
        connection.execute(
            f'DELETE FROM {table} WHERE "year" = ? AND "time" = ?',
            [str(target.year), f"{target.week:02d}"],
        )
        connection.executemany(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", values)
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise


def write_weeks(playwright, connection, chart, table, targets):
    with ExitStack() as sources:
        source = None
        for target in targets:
            retry_count = 0
            while True:
                try:
                    if source is None:
                        source = sources.enter_context(open_source(playwright, chart))
                    rows = (
                        scrape_digital_week(source, target) if chart == "digital"
                        else scrape_api_week(source, chart, target)
                    )
                    write_week(connection, table, FIELDNAMES[chart], target, rows)
                    if rows:
                        print(f"Wrote {chart} {target.year}-W{target.week:02d}")
                    break
                except Exception as exc:
                    retry_count += 1
                    print(f"Error for {chart} {target.year}-W{target.week:02d} (attempt {retry_count}): {exc}")
                    sources.close()
                    source = None
                    if MAX_RETRIES_PER_WEEK is not None and retry_count > MAX_RETRIES_PER_WEEK:
                        raise RuntimeError(
                            f"Failed to scrape {chart} {target.year}-W{target.week:02d} "
                            f"after {MAX_RETRIES_PER_WEEK} retries."
                        ) from exc
                    time.sleep(RETRY_DELAY_SECONDS)


def scrape_chart(playwright, connection, chart, table_name, start_year, end_year, start_week, end_week):
    table = f'bronze."{table_name}"'
    columns = ", ".join(f'"{field}" VARCHAR' for field in FIELDNAMES[chart])
    connection.execute(f"CREATE TABLE IF NOT EXISTS {table} ({columns})")

    if chart == "digital":
        targets = [
            WeekTarget(year, week, f"{year}{week:02d}")
            for year, week in iter_week_values(start_year, end_year, start_week, end_week, 52)
        ]
    else:
        with open_source(playwright, chart) as request:
            lookup = build_week_lookup(request, chart)
        targets = resolve_week_targets(lookup, chart, start_year, end_year, start_week, end_week)

    write_weeks(playwright, connection, chart, table, targets)


def main():
    database_path = Path(__file__).resolve().parent / "data" / "Final_Project.duckdb"
    database_path.parent.mkdir(exist_ok=True)
    with duckdb.connect(str(database_path)) as connection, sync_playwright() as playwright:
        connection.execute("CREATE SCHEMA IF NOT EXISTS bronze")
        rankings_table = "rankings" #Update name
        digital_range = (2020, 2026, 1, 36) #Change accordingly
        scrape_chart(playwright, connection, "digital", rankings_table, *digital_range)
        scrape_chart(playwright, connection, "social", "social_score", 2025, 2026, 31, 36)
        scrape_chart(playwright, connection, "retail", "album_sales", 2020, 2026, 1, 36)


if __name__ == "__main__":
    main()
