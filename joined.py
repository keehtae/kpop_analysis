"""Join Essentia Summary features to rankings using the supplied matching rules.

Called by silver.py; may also be run directly after the Silver rankings exist.
Only confident matches enter silver.essentia_and_rankings. Review candidates,
unavailable songs and the removed-sheet audit get separate quarantine tables.
Input workbooks and saved approvals are read only; no Excel output is produced.
"""

import argparse
import csv
import json
import math
import re
import sys
from numbers import Real
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from itertools import islice, product
from pathlib import Path

import duckdb
from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parent
DEFAULT_ESSENTIA_ROOT = Path.home() / "Capstone test"
FIELDS = ("song", "artist", "album")
CHART_COLUMNS = ("year", "week", "rank", *FIELDS, "popularity_score", "label", "distributor")
CJK = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ一-龯ぁ-ヿ]")
VERSION = re.compile(
    r"\b(?:english|japanese|chinese|korean|remix|instrumental|acoustic|live|"
    r"remaster(?:ed)?|rerecord(?:ed|ing)?|sped|slowed|twin)\b", re.I
)
CONTENT_MARKER = re.compile(
    r"\s*[\[(]\s*(explicit|clean|edited|censored|uncensored)"
    r"(?:\s+(?:ver(?:sion)?\.?|edit(?:ion)?))?\s*[\])]", re.I
)
CONTENT_SUFFIX = re.compile(
    r"\s+-\s+(explicit|clean|edited|censored|uncensored)"
    r"(?:\s+(?:ver(?:sion)?\.?|edit(?:ion)?))?$", re.I
)

# Full chart identity -> exact, verified local recording. Paths are relative to
# the music library so the connections do not depend on a particular user home.
VERIFIED_RECORDING_CONNECTIONS = (
    ("신세계 (New World)", "온앤오프 (ONF)", "로드 투 킹덤 FINAL",
     "Compilations/Road to Kingdom FINAL - EP/05 New World.m4a"),
    ("무대로 (Dj Vu; 舞代路)", "NCT DREAM", "NCT RESONANCE Pt. 1 - The 2nd Album",
     "NCT/NCT RESONANCE, Pt. 1 - The 2nd Album/07 Déjà Vu.m4a"),
    ("Darl+ing", "세븐틴", "Darl+ing",
     "SEVENTEEN/Face the Sun (Extended Version)/01 Darl+Ing.m4a"),
    ("DON QUIXOTE", "세븐틴", "4th Album `Face the Sun`",
     "SEVENTEEN/Face the Sun (Extended Version)/03 Don Quixote.m4a"),
    ("Domino", "세븐틴", "4th Album `Face the Sun`",
     "SEVENTEEN/Face the Sun (Extended Version)/05 Domino.m4a"),
    ("March", "세븐틴", "4th Album `Face the Sun`",
     "SEVENTEEN/Face the Sun (Extended Version)/04 March.m4a"),
    ("Shadow", "세븐틴", "4th Album `Face the Sun`",
     "SEVENTEEN/Face the Sun (Extended Version)/06 Shadow.m4a"),
    ("노래해", "세븐틴", "4th Album `Face the Sun`",
     "SEVENTEEN/Face the Sun (Extended Version)/07 'Bout You.m4a"),
    ("IF you leave me", "세븐틴", "4th Album `Face the Sun`",
     "SEVENTEEN/Face the Sun (Extended Version)/08 IF you leave me.m4a"),
    ("Ash", "세븐틴", "4th Album `Face the Sun`",
     "SEVENTEEN/Face the Sun (Extended Version)/09 Ash.m4a"),
    ("괜찮아", "몬스타엑스", "REASON",
     "MONSTA X/REASON - EP/06 IT'S ALRIGHT.m4a"),
    ("달랐을까", "PLAVE", "나의 해리에게 OST Part.4",
     "Compilations/Dear Hyeri (Original Soundtrack)/04 What If.m4a"),
    ("다시 만난 세계 (Into The New World)", "소녀시대", "다시 만난 세계",
     "Girls' Generation/Into the New World - EP/01 Into the New World.m4a"),
    ("오늘만 I LOVE YOU", "BOYNEXTDOOR", "오늘만 I LOVE YOU",
     "BOYNEXTDOOR/No Genre/06 IF I SAY, I LOVE YOU.m4a"),
    ("Bad Influence (Prod. by Pharrell Williams)", "세븐틴", "5th Album `HAPPY BURSTDAY`",
     "SEVENTEEN/HAPPY BURSTDAY/17 Bad Influence (Prod. by Pharrell Williams).m4a"),
    ("N the Front", "몬스타엑스", "THE X",
     "MONSTA X/THE X (Deluxe Version)/02 N the Front.m4a"),
    ("그럼에도, 우린", "씨야 (SeeYa)", "그럼에도, 우린",
     "SeeYa/Still Here, Still Us - Single/01 Still Here, Still Us.m4a"),
    ("기억해줘요", "BOYNEXTDOOR", "HOME",
     "BOYNEXTDOOR/HOME_ DELUXE/09 Forever You.m4a"),
    # User-confirmed paths supplied on 2026-11-19.
    ("Kill It", "aespa", "Whiplash - The 5th Mini Album",
     "aespa/Whiplash - The 5th Mini Album - EP/02 Kill It.m4a"),
    ("Flights, Not Feelings", "aespa", "Whiplash - The 5th Mini Album",
     "aespa/Whiplash - The 5th Mini Album - EP/03 Flights, Not Feelings.m4a"),
    ("Pink Hoodie", "aespa", "Whiplash - The 5th Mini Album",
     "aespa/Whiplash - The 5th Mini Album - EP/04 Pink Hoodie.m4a"),
    ("Atlantis", "샤이니 (SHINee)", "Atlantis - The 7th Album Repackage",
     "SHINee/Atlantis - The 7th Album Repackage/01 Atlantis.m4a"),
    ("View", "샤이니 (SHINee)", "Odd - The 4th Album",
     "SHINee/Odd - The 4th Album/03 View.m4a"),
    ("HARD", "샤이니 (SHINee)", "HARD - The 8th Album",
     "SHINee/HARD - The 8th Album/01 HARD.m4a"),
    ("JUICE", "샤이니 (SHINee)", "HARD - The 8th Album",
     "SHINee/HARD - The 8th Album/02 JUICE.m4a"),
    ("Satellite", "샤이니 (SHINee)", "HARD - The 8th Album",
     "SHINee/HARD - The 8th Album/04 Satellite.m4a"),
    ("My My", "세븐틴", "7th Mini Album `헹가래`",
     "SEVENTEEN/Heng_garæ - EP/04 My My.m4a"),
    ("좋겠다", "세븐틴", "7th Mini Album `헹가래`",
     "SEVENTEEN/Heng_garæ - EP/03 I Wish.m4a"),
    ("어른 아이", "세븐틴", "7th Mini Album `헹가래`",
     "SEVENTEEN/Heng_garæ - EP/05 Kidult.m4a"),
    ("같이 가요", "세븐틴", "7th Mini Album `헹가래`",
     "SEVENTEEN/Heng_garæ - EP/06 Together.m4a"),
    ("겨우", "세븐틴", "Special Album `; [Semicolon]`",
     "SEVENTEEN/; (Semicolon) - EP/06 All My Love.m4a"),
    ("도레미", "세븐틴", "Special Album `; [Semicolon]`",
     "SEVENTEEN/; (Semicolon) - EP/02 Do Re Mi.m4a"),
    ("HEY BUDDY", "세븐틴", "Special Album `; [Semicolon]`",
     "SEVENTEEN/; (Semicolon) - EP/03 HEY BUDDY.m4a"),
    ("마음에 불을 지펴", "세븐틴", "Special Album `; [Semicolon]`",
     "SEVENTEEN/; (Semicolon) - EP/04 Light a Flame.m4a"),
    ("AH! LOVE", "세븐틴", "Special Album `; [Semicolon]`",
     "SEVENTEEN/; (Semicolon) - EP/05 AH! LOVE.m4a"),
    ("Heaven`s Cloud", "세븐틴", "8th Mini Album `Your Choice`",
     "SEVENTEEN/Your Choice/01 Heaven's Cloud.m4a"),
    ("Anyone", "세븐틴", "8th Mini Album `Your Choice`",
     "SEVENTEEN/Your Choice/03 Anyone.m4a"),
    ("같은 꿈, 같은 맘, 같은 밤", "세븐틴", "8th Mini Album `Your Choice`",
     "SEVENTEEN/Your Choice/06 Same Dream, Same Mind, Same Night.m4a"),
    ("GAM3 BO1", "세븐틴", "8th Mini Album `Your Choice`",
     "SEVENTEEN/Your Choice/04 GAM3 BO1.m4a"),
    ("Wave", "세븐틴", "8th Mini Album `Your Choice`",
     "SEVENTEEN/Your Choice/05 Wave.m4a"),
    ("소용돌이", "세븐틴", "9th Mini Album `Attacca`",
     "SEVENTEEN/Attacca/01 To you.m4a"),
    ("Crush", "세븐틴", "9th Mini Album `Attacca`",
     "SEVENTEEN/Attacca/03 Crush.m4a"),
    ("매일 그대라서 행복하다", "세븐틴", "9th Mini Album `Attacca`",
     "SEVENTEEN/Attacca/05 Imperfect love.m4a"),
    ("그리워하는 것까지", "세븐틴", "9th Mini Album `Attacca`",
     "SEVENTEEN/Attacca/06 I can't run away.m4a"),
    ("PANG!", "세븐틴", "9th Mini Album `Attacca`",
     "SEVENTEEN/Attacca/04 PANG!.m4a"),
    ("2 MINUS 1 (Digital Only)", "세븐틴", "9th Mini Album `Attacca`",
     "SEVENTEEN/Attacca/07 2 MINUS 1 (Bonus Track).m4a"),
    ("돌고 돌아", "세븐틴", "4th Album Repackage `SECTOR 17`",
     "SEVENTEEN/SECTOR 17/01 Circles.m4a"),
    ("CHEERS", "세븐틴", "4th Album Repackage `SECTOR 17`",
     "SEVENTEEN/SECTOR 17/04 CHEERS.m4a"),
    ("먼지", "세븐틴", "10th Mini Album `FML`",
     "SEVENTEEN/FML/05 Dust.m4a"),
    ("April shower", "세븐틴", "10th Mini Album `FML`",
     "SEVENTEEN/FML/06 April shower.m4a"),
    ("Fire", "세븐틴", "10th Mini Album `FML`",
     "SEVENTEEN/FML/03 Fire.m4a"),
    ("I Don`t Understand But I Luv U", "세븐틴", "10th Mini Album `FML`",
     "SEVENTEEN/FML/04 I Don't Understand But I Luv U.m4a"),
    ("Diamond Days", "세븐틴", "11th Mini Album `SEVENTEENTH HEAVEN`",
     "SEVENTEEN/SEVENTEENTH HEAVEN/03 Diamond Days.m4a"),
    ("Monster", "세븐틴", "11th Mini Album `SEVENTEENTH HEAVEN`",
     "SEVENTEEN/SEVENTEENTH HEAVEN/05 Monster.m4a"),
    ("Back 2 Back", "세븐틴", "11th Mini Album `SEVENTEENTH HEAVEN`",
     "SEVENTEEN/SEVENTEENTH HEAVEN/04 Back 2 Back.m4a"),
    ("하품", "세븐틴", "11th Mini Album `SEVENTEENTH HEAVEN`",
     "SEVENTEEN/SEVENTEENTH HEAVEN/06 Yawn.m4a"),
    ("Headliner", "세븐틴", "11th Mini Album `SEVENTEENTH HEAVEN`",
     "SEVENTEEN/SEVENTEENTH HEAVEN/07 Headliner.m4a"),
    ("2YA2YAO!", "슈퍼주니어 (Super Junior)", "TIMELESS - The 9th Album Repackage",
     "SUPER JUNIOR/TIMELESS - The 9th Album Repackage - EP/01 2YA2YAO!.m4a"),
    ("House Party", "슈퍼주니어 (Super Junior)", "The Renaissance - The 10th Album",
     "SUPER JUNIOR/The Renaissance - The 10th Album/02 House Party.m4a"),
    ("Mango", "슈퍼주니어 (Super Junior)", "The Road : Keep on Going - The 11th Album Vol.1",
     "SUPER JUNIOR/The Road _ Keep on Going - The 11th Album Vol.1 - EP/01 Mango.m4a"),
    ("Express Mode", "슈퍼주니어 (Super Junior)", "Super Junior25 - The 12th Album",
     "SUPER JUNIOR/Super Junior25 - The 12th Album/01 Express Mode.m4a"),
    ("구두", "씨야 (SeeYa)", "See You Again",
     "SeeYa/Scent of a Woman/02 Shoes.m4a"),
    ("여인의 향기", "씨야 (SeeYa)", "See You Again",
     "SeeYa/Scent of a Woman/01 Scent of a Woman.m4a"),
    ("The Stranger", "온앤오프 (ONF)", "ONF:MY IDENTITY",
     "ONF/ONF_MY IDENTITY - EP/01 The Stranger.m4a"),
    ("Day By Day", "티아라 (T-ara)", "Day By Day",
     "T-ara/DAY BY DAY - EP/01 DAY BY DAY.m4a"),
)


# Explicit user selections from the joined workbook before the 2026-11-19 edit.
REMOVED_SONGS = (
    ("featured", 86, "Bet You Wanna (Feat. Cardi B)", "BLACKPINK", "THE ALBUM"),
    ("featured", 182, "Pool Party (Feat. 이찬 of DKB)", "브레이브걸스 (Brave Girls)", "Summer Queen"),
    ("featured", 195, "MOTION (feat. Juicy J)", "CORTIS (코르티스)", "MOTION"),
    ("featured", 810, "Damage (HOSHI Solo) (feat. Timbaland)", "세븐틴", "5th Album `HAPPY BURSTDAY`"),
    ("featured", 833, "LOVE, MONEY, FAME (feat. DJ Khaled)", "세븐틴", "12th Mini Album `SPILL THE FEELS`"),
    ("featured", 906, "Happy Fools (feat. Coi Leray)", "투모로우바이투게더", "이름의 장: TEMPTATION"),
    ("featured", 991, "WDA (Whole Different Animal) (Feat. G-DRAGON)", "aespa", "WDA (Whole Different Animal)"),
    ("featured", 1065, "Mono (Feat. skaiwater)", "i-dle (아이들)", "Mono"),
    ("prod", 1063, "Last Dance (Prod. GroovyRoom)", "i-dle (아이들)", "Last Dance (Prod. GroovyRoom)"),
    ("prod", 819, "Bad Influence (Prod. by Pharrell Williams)", "세븐틴", "5th Album `HAPPY BURSTDAY`"),
    ("Removed Artists", 2, "혹시 니 생각이 바뀌면", "2am", "혹시 니 생각이 바뀌면"),
)
REMOVED_ARTISTS_NOTE = "Artists and their songs removed because they are not KPop groups that dance on stage and sing."

def content_rating(value):
    labels = {m.group(1).casefold() for pattern in (CONTENT_MARKER, CONTENT_SUFFIX)
              for m in pattern.finditer(str(value or ""))}
    if labels & {"explicit", "uncensored"}:
        return "explicit"
    return "clean" if labels else None


def content_base(value):
    """Remove only explicit/clean edition markers, never other version words."""
    return CONTENT_SUFFIX.sub("", CONTENT_MARKER.sub("", str(value or ""))).strip()


def content_identity(record):
    return identity(content_base(record["song"]), record["artist"], content_base(record["album"]))


def content_review_reason(requested, available, store_rating=None):
    wanted, actual = content_rating(requested["song"]), content_rating(available["song"])
    if wanted != actual and (wanted or actual):
        return (f"Explicit/clean version review: chart track is {wanted or 'not edition-labeled'}; "
                f"available track is {actual or 'not edition-labeled (possibly the clean version)'}. "
                "Available Essentia features are included; verify the recording edition")
    store = str(store_rating or "").casefold()
    if (wanted == "explicit" and store in {"clean", "notexplicit", "no"}) or (
            wanted == "clean" and store in {"explicit", "yes"}):
        return "Explicit/clean version review: requested track edition conflicts with store track-rating metadata"
    if store in {"explicit", "yes"} and any(
            content_rating(record["album"]) == "clean" for record in (requested, available)):
        return "Explicit/clean version review: explicit track-rating metadata conflicts with a clean album edition"
    return None


def normalize(value):
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = re.sub(r"\bver\.?\b", "version", text)
    return "".join(c for c in text if c.isalnum())


def aliases(value, field):
    """Formatting/bilingual aliases only; preserve recording-version words."""
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    if field == "album":
        text = re.sub(r"\s+-\s+(?:EP|Single)$", "", text, flags=re.I)
    result = {normalize(text)} - {""}
    if field in {"song", "artist"}:
        outside = re.sub(r"\([^()]*\)", "", text).strip()
        inside = re.findall(r"\(([^()]*)\)", text)
        # A single opposing-script parenthesis is an alias, not 'feat.' or a version.
        if outside and len(inside) == 1 and not VERSION.search(text):
            part = inside[0]
            opposite = (bool(CJK.search(outside)) and not re.search(r"[a-zA-Z]", outside)
                        and bool(re.search(r"[a-zA-Z]", part)) and not CJK.search(part)) or (
                bool(re.search(r"[a-zA-Z]", outside)) and not CJK.search(outside)
                and bool(CJK.search(part)) and not re.search(r"[a-zA-Z]", part))
            if opposite:
                result.update((normalize(outside), normalize(part)))
    return result - {""}


def identity(song, artist, album):
    return {"song": str(song or "").strip(), "artist": str(artist or "").strip(),
            "album": str(album or "").strip()}


def keys(record, fields=FIELDS):
    return product(*(sorted(aliases(record[field], field)) for field in fields))


def index_records(records, fields=FIELDS):
    index = defaultdict(set)
    for number, record in enumerate(records):
        for key in keys(record, fields):
            index[key].add(number)
    return index


def lookup(index, record, fields=FIELDS):
    return set().union(*(index.get(key, set()) for key in keys(record, fields)))


def compatible_titles(left, right):
    """An English title mismatch or version mismatch needs human review."""
    if set(VERSION.findall(left.casefold())) != set(VERSION.findall(right.casefold())):
        return False
    return bool(aliases(left, "song") & aliases(right, "song")) or bool(CJK.search(left))


def version_base(title):
    """A version-stripped title is for review suggestions only."""
    return normalize(re.sub(r"\([^()]*\)", lambda m: "" if VERSION.search(m[0]) else m[0], title))


def read_chart(path):
    """Read the original headed/headerless CSV through the same chart pivot."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        first = next(reader, None)
        if first is None:
            raise ValueError(f"Chart CSV is empty: {path}")
        headed = normalize(first[0]) in {"year", "년도", "연도"}
        if headed:
            headers = [normalize(v) for v in first]
            name_options = {"song": ("song", "title", "songtitle"),
                            "artist": ("artist", "artists"), "album": ("album",),
                            "week": ("week", "time"), "popularity_score": ("popularityscore", "score")}
            positions = {}
            for field in CHART_COLUMNS[:7]:
                options = name_options.get(field, (normalize(field),))
                positions[field] = next((headers.index(v) for v in options if v in headers), None)
                if positions[field] is None:
                    raise ValueError(f"Chart CSV is missing column: {field}")
        else:
            positions = dict(zip(CHART_COLUMNS, range(9)))

        def records():
            if not headed:
                yield first
            yield from reader

        def chart_records():
            for line, values in enumerate(records(), 2 if headed else 1):
                if not any(v.strip() for v in values):
                    continue
                if len(values) <= max(positions[k] for k in CHART_COLUMNS[:7]):
                    raise ValueError(f"Chart CSV line {line}: expected year, week, rank, song, artist, album, score")
                yield {k: values[positions[k]] for k in CHART_COLUMNS[:7]}

        return pivot_chart(chart_records())


def read_rankings(connection):
    """Adapt Silver's chart column names without exporting an intermediate CSV."""
    rows = connection.execute(
        'SELECT year, time, rank, song_title, artist, album, score FROM silver.rankings '
        'ORDER BY try_cast(year AS INTEGER), try_cast(time AS INTEGER), '
        'try_cast(rank AS INTEGER), song_title, artist, album, score'
    ).fetchall()
    return pivot_chart(dict(zip(CHART_COLUMNS[:7], row)) for row in rows)


def pivot_chart(records):
    """Pivot weekly scores, preserving zero, blanks and conflicting values."""
    songs = {}
    periods = set()
    row_count = 0
    identical_duplicates = 0
    for line, record in enumerate(records, 1):
        data = {k: str(record[k]).strip() if record[k] is not None else "" for k in CHART_COLUMNS[:7]}
        try:
            year, week, rank = (int(data[k]) for k in ("year", "week", "rank"))
            if year < 100:
                year += 2000
            if not (2000 <= year <= 2099 and 1 <= week <= 53 and rank >= 1):
                raise ValueError("year, week or rank out of range")
            text = data["popularity_score"].replace(",", "")
            score = float(text) if text else None
            if score is not None:
                if not math.isfinite(score) or score < 0:
                    raise ValueError("invalid popularity score")
                score = int(score) if score.is_integer() else score
        except ValueError as exc:
            raise ValueError(f"Chart row {line}: {exc}") from exc
        record = identity(*(data[k] for k in FIELDS))
        if not all(record.values()):
            raise ValueError(f"Chart row {line}: missing song, artist or album")
        key = tuple(normalize(record[k]) for k in FIELDS)
        if not all(key):
            raise ValueError(f"Chart row {line}: song identity normalizes to an empty key")
        if key not in songs:
            songs[key] = {**record, "scores": {}, "conflicts": {}}
        song = songs[key]
        period = f"{year % 100:02d}_{week:02d}"
        if period in song["scores"]:
            if song["scores"][period] != score:
                song["conflicts"].setdefault(period, {song["scores"][period]}).add(score)
            else:
                identical_duplicates += 1
        else:
            song["scores"][period] = score
        periods.add(period)
        row_count += 1

    return list(songs.values()), sorted(periods), row_count, identical_duplicates


def read_excel(path, sheet_name=None, required_headers=None):
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook[sheet_name] if sheet_name else workbook.active
        iterator = enumerate(sheet.iter_rows(values_only=True), 1)
        if required_headers:
            header_row, headers = next(((line, values) for line, values in islice(iterator, 20)
                                        if required_headers.issubset(set(values))), (0, ()))
        else:
            header_row, headers = next(iterator, (0, ()))
        headers = list(headers)
        while headers and headers[-1] is None:
            headers.pop()
        if not headers or any(not isinstance(v, str) or not v.strip() for v in headers):
            raise ValueError(f"Missing or blank workbook headers: {path}")
        if len(set(headers)) != len(headers):
            raise ValueError(f"Duplicate workbook headers: {path}")
        return list(headers), [{**dict(zip(headers, values)), "_excel_row": line}
                               for line, values in iterator
                               if any(v is not None for v in values)]
    finally:
        workbook.close()


def find_matches(chart, summary, mappings):
    """Build evidence edges, then enforce a one-chart-song/one-Essentia-row join."""
    chart_index = index_records(chart)
    audio_index = index_records(summary)
    # Each edge retains both accepted evidence and reasons for caution.
    edges = defaultdict(lambda: defaultdict(lambda: {"strong": set(), "weak": set(), "content_review": set()}))

    def add(c, s, strong, reason, content_review=False):
        edges[c][s]["strong" if strong else "weak"].add(reason)
        if content_review:
            edges[c][s]["content_review"].add(reason)

    for s, row in enumerate(summary):
        for c in lookup(chart_index, row):
            add(c, s, True, "song + artist + album")
        reference = identity(*(row.get(f"reference_{k}") for k in ("title", "artist", "album")))
        if all(reference.values()):
            trusted = row.get("match_status") in {"matched", "manual_include"}
            trusted = trusted and compatible_titles(reference["song"], row["song"])
            for c in lookup(chart_index, reference):
                add(c, s, trusted, "Essentia reference metadata" if trusted else
                    "Reference metadata requires verification of source match/title/version")
    for mapping in mappings:
        requested = identity(*(mapping.get(f"Requested {k}") for k in ("title", "artist", "album")))
        matched = identity(*(mapping.get(f"Matched {k}") for k in ("title", "artist", "album")))
        status = str(mapping.get("Status") or "").strip().upper()
        if not all(requested.values()) or not all(matched.values()):
            continue
        strong = status == "OK" and compatible_titles(requested["song"], matched["song"])
        reason = ("iTunes OK bridge" if strong else f"iTunes {status or 'missing status'} bridge: verify title/version")
        if not strong and mapping.get("Notes"):
            reason += ": " + str(mapping["Notes"])
        for c in lookup(chart_index, requested):
            for s in lookup(audio_index, matched):
                rating_reason = content_review_reason(chart[c], summary[s], mapping.get("Explicit"))
                album_label_differs = (content_rating(requested["album"]) != content_rating(summary[s]["album"]))
                rating_known = str(mapping.get("Explicit") or "").casefold() in {"notexplicit", "explicit", "yes", "no", "clean"}
                if rating_reason:
                    add(c, s, False, rating_reason, content_review=True)
                elif album_label_differs and not rating_known:
                    add(c, s, False, "Album explicit/clean label differs; track rating is unknown. Verify the available edition")
                else:
                    add(c, s, strong, reason + ("; album content label differs, track rating checked" if album_label_differs else ""))

    # A clean/explicit counterpart remains useful even without a purchase bridge.
    # These relaxed triples are review suggestions, not global aliases.
    content_audio = [content_identity(row) for row in summary]
    content_index = index_records(content_audio)
    for c, record in enumerate(chart):
        base = content_identity(record)
        for s in lookup(content_index, base):
            row = summary[s]
            if all(record[k] == base[k] and row[k] == content_audio[s][k] for k in ("song", "album")):
                continue
            rating_reason = content_review_reason(record, row)
            add(c, s, False, rating_reason or
                "Album explicit/clean label differs; verify track rating and recording edition",
                content_review=bool(rating_reason))

    # A plausible edition substitution cannot be promoted by another OK bridge.
    for candidates in edges.values():
        for evidence in candidates.values():
            if evidence["content_review"]:
                evidence["weak"].update(evidence["strong"])
                evidence["strong"].clear()

    claimed = {s for candidates in edges.values() for s, e in candidates.items() if e["strong"]}
    # Partial/fuzzy evidence can suggest review candidates, never accept them.
    pair_indexes = {fields: index_records(summary, fields) for fields in
                    (("song", "artist"), ("song", "album"), ("artist", "album"), ("artist",))}
    for c, record in enumerate(chart):
        if any(e["strong"] for e in edges[c].values()):
            continue
        for fields, idx in pair_indexes.items():
            for s in lookup(idx, record, fields):
                row = summary[s]
                title_equal = bool(aliases(record["song"], "song") & aliases(row["song"], "song"))
                title_ratio = max((SequenceMatcher(None, a, b).ratio()
                                   for a in aliases(record["song"], "song")
                                   for b in aliases(row["song"], "song")), default=0)
                translated = bool(CJK.search(record["song"])) != bool(CJK.search(row["song"]))
                version_variant = version_base(record["song"]) == version_base(row["song"])
                if s in claimed and not title_equal and not version_variant and title_ratio < .88:
                    # A row already identified as a different chart song is not a
                    # translation candidate merely because it shares an album.
                    continue
                if fields == ("artist",) and (title_ratio < .88 or min(len(normalize(record["song"])), len(normalize(row["song"]))) < 5):
                    continue
                if fields == ("artist",) and s in edges[c]:
                    continue
                if fields == ("artist", "album") and not (title_equal or translated or version_variant or title_ratio >= .65):
                    continue
                reason = {
                    ("song", "artist"): "Song and artist match; verify different album names and recording/language version",
                    ("song", "album"): "Song and album match; verify artist names and recording version",
                    ("artist", "album"): "Artist and album match; verify title translation and recording version",
                    ("artist",): "Similar title for this artist; verify title, album and recording version",
                }[fields]
                add(c, s, False, reason)

    # Checked connectors add evidence for these precise pairs only. The normal
    # uniqueness/conflict rules below still govern acceptance.
    chart_rows = {tuple(normalize(row[k]) for k in FIELDS): c for c, row in enumerate(chart)}
    for song, artist, album, suffix in VERIFIED_RECORDING_CONNECTIONS:
        c = chart_rows.get(tuple(normalize(value) for value in (song, artist, album)))
        if c is None:
            continue
        for s, row in enumerate(summary):
            if (str(row.get("file_path") or "").endswith("/" + suffix)
                    and str(row.get("status", "success")).casefold() == "success"):
                reason = content_review_reason(chart[c], row)
                if set(VERSION.findall(song.casefold())) != set(VERSION.findall(row["song"].casefold())):
                    reason = "Verified connector has changed recording-version metadata; verify the version"
                add(c, s, not reason, reason or "Verified recording connector", content_review=bool(reason))

    strong_by_summary = defaultdict(set)
    for c, candidates in edges.items():
        for s, evidence in candidates.items():
            if evidence["strong"]:
                strong_by_summary[s].add(c)
    for c, candidates in edges.items():
        for s, evidence in candidates.items():
            if strong_by_summary[s] and c not in strong_by_summary[s]:
                evidence["weak"].add("Candidate is already matched to another chart identity; verify album and language/version")
    accepted, review, unavailable = {}, {}, []
    for c, record in enumerate(chart):
        candidates = edges[c]
        strong = [s for s, evidence in candidates.items() if evidence["strong"]]
        if (not record["conflicts"] and len(strong) == 1
                and len(strong_by_summary[strong[0]]) == 1):
            s = strong[0]
            accepted[c] = (s, "; ".join(sorted(candidates[s]["strong"])))
        elif candidates or record["conflicts"]:
            reasons = []
            if record["conflicts"]:
                reasons.append("Conflicting popularity scores in " + ", ".join(sorted(record["conflicts"])))
            if len(strong) > 1:
                reasons.append("Multiple Essentia rows match this chart song")
            if any(len(strong_by_summary[s]) > 1 for s in strong):
                reasons.append("One Essentia row matches multiple chart songs")
            review[c] = (candidates, reasons)
        else:
            unavailable.append(c)
    return accepted, review, unavailable


def build_tables(chart, periods, headers, summary, accepted, review, unavailable):
    provenance = ["chart_song", "chart_artist", "chart_album", "join_method"]
    joined_headers = provenance + headers + periods
    if len(set(joined_headers)) != len(joined_headers):
        raise ValueError("Output column names collide with existing Essentia columns")
    joined_rows = []
    for c, (s, method) in sorted(accepted.items(), key=lambda item: item[1][0]):
        row = chart[c]
        joined_rows.append([*(row[k] for k in FIELDS), method,
                            *(summary[s].get(k) for k in headers), *(row["scores"].get(p) for p in periods)])
    review_headers = ["chart_song", "chart_artist", "chart_album", "review_reason", "candidate_summary_row",
                      "conflicting_chart_scores"] + headers + periods
    review_rows = []
    for c, (candidates, reasons) in review.items():
        record = chart[c]
        for s in sorted(candidates) if candidates else [None]:
            evidence = candidates[s] if s is not None else {"strong": set(), "weak": set()}
            reason = "; ".join(sorted(set(reasons) | evidence["strong"] | evidence["weak"]))
            # Conflicting weeks stay blank instead of selecting an arbitrary score.
            review_rows.append([*(record[k] for k in FIELDS), reason,
                                summary[s]["_excel_row"] if s is not None else None,
                                json.dumps({p: sorted(v, key=lambda x: (x is None, x or 0))
                                            for p, v in sorted(record["conflicts"].items())}) if record["conflicts"] else None,
                                *(summary[s].get(k) if s is not None else None for k in headers),
                                *(None if p in record["conflicts"] else record["scores"].get(p) for p in periods)])
    return [("joined", joined_headers, joined_rows), ("review", review_headers, review_rows),
            ("unavailable", list(FIELDS), [[chart[c][k] for k in FIELDS] for c in unavailable])]


def deduplicate_joined(tables, preferred=()):
    """Keep one song/artist row, retaining weekly history and original row numbers."""
    name, headers, rows = tables[0]
    song_col, artist_col, album_col = (headers.index("chart_" + field) for field in FIELDS)
    weeks = [i for i, header in enumerate(headers) if re.fullmatch(r"\d{2}_\d{2}", header)]
    groups = defaultdict(list)
    for row_number, row in enumerate(rows, 2):
        groups[(normalize(row[song_col]), normalize(row[artist_col]))].append((row_number, row))
    joined_rows, duplicate_rows = [], []
    preferred = set(preferred)
    for members in groups.values():
        chosen = [(n, row) for n, row in members if tuple(normalize(row[i]) for i in
                  (song_col, artist_col, album_col)) in preferred]
        if len(chosen) > 1:
            raise ValueError("Multiple preferred album identities were approved for the same song")
        primary_number, primary = (chosen or members)[0]
        kept = list(primary)
        notes = defaultdict(list)
        if len(members) > 1:
            for number, row in members:
                if number == primary_number:
                    continue
                for i in weeks:
                    if kept[i] is not None and row[i] is not None and kept[i] != row[i]:
                        if not chosen or primary[i] is None:
                            raise ValueError(f"Duplicate song {kept[song_col]!r} by {kept[artist_col]!r} "
                                             f"has conflicting popularity scores in {headers[i]}")
                        notes[number].append(f"{headers[i]}: {row[i]} -> {kept[i]} (approved album)")
                    if kept[i] is None:
                        kept[i] = row[i]
            duplicate_rows.extend([number, row[song_col], row[artist_col], row[album_col],
                                   "kept" if number == primary_number else "removed",
                                   "; ".join(notes[number]) or None] for number, row in members)
        joined_rows.append(kept)
    duplicate_rows.sort(key=lambda row: row[0])
    return ([(name, headers, joined_rows), *tables[1:],
             ("duplicates", ["row_number", "chart_song", "chart_artist", "chart_album", "action", "score_notes"], duplicate_rows)],
            len(rows) - len(joined_rows))


def build_removed_tab(tables):
    """Keep explicit exclusions out of active tabs and create four compact audits."""
    removed_keys = {tuple(normalize(v) for v in entry[2:]) for entry in REMOVED_SONGS}
    active = []
    for name, headers, rows in tables[:3]:
        columns = [headers.index(("" if name == "unavailable" else "chart_") + field) for field in FIELDS]
        rows = [row for row in rows if tuple(normalize(row[i]) for i in columns) not in removed_keys]
        active.append((name, headers, rows))
    _, headers, rows = tables[-1]
    sections = [("Duplicates", headers, rows,
                 "Row numbers refer to joined before deduplication. An approved album takes precedence in overlapping weeks; replaced scores are recorded here.")]
    for category in ("featured", "prod", "Removed Artists"):
        entries = [[number, song, artist, album] for group, number, song, artist, album in REMOVED_SONGS
                   if group == category]
        note = REMOVED_ARTISTS_NOTE if category == "Removed Artists" else "Row numbers refer to the original joined rows selected for removal."
        sections.append((category, ["row_number", "chart_song", "chart_artist", "chart_album"], entries, note))
    return [*active, ("removed", None, sections)]


def find_full_summary(directories):
    """Select a full-summary export, including the non-timestamped name."""
    candidates = {path for directory in directories
                  for pattern in ("all_songs_summary.xlsx", "all_songs_summary_*.xlsx")
                  for path in directory.glob(pattern) if path.is_file()}
    dated = [path for path in candidates if re.fullmatch(
        r"all_songs_summary_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(?:_\d{6})?\.xlsx", path.name)]
    # Opening/saving an old export must not make it newer than a later output.
    return max(dated, key=lambda path: path.name) if dated else (
        max(candidates, key=lambda path: path.stat().st_mtime_ns) if candidates else None)


def chart_key(record, prefix=""):
    return tuple(normalize(record[prefix + field]) for field in FIELDS)


def audio_path(value):
    return str(Path(value).expanduser().resolve())


def load_approvals(path):
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("approvals"), list):
        raise ValueError(f"Invalid approval file: {path}")
    decisions = data["approvals"]
    seen_chart = set()
    for record in decisions:
        required = [*("chart_" + field for field in FIELDS), *FIELDS, "file_path"]
        if not isinstance(record, dict) or any(not isinstance(record.get(k), str) or not record[k].strip()
                                               for k in required):
            raise ValueError(f"Approval is missing chart/audio identity fields: {path}")
        key, file = chart_key(record, "chart_"), audio_path(record["file_path"])
        if key in seen_chart:
            raise ValueError(f"Duplicate chart song in approval file: {path}")
        seen_chart.add(key)
    validate_shared_recordings(decisions)
    return decisions


def validate_shared_recordings(decisions):
    """Approved album identities may share a recording only for the same song/artist."""
    uses = {}
    for row in decisions:
        file, group = audio_path(row["file_path"]), chart_key(row, "chart_")[:2]
        if file in uses and uses[file] != group:
            raise ValueError("A recording was approved for different songs/artists; resolve the conflicting approvals")
        uses[file] = group


def approval_targets(chart, summary, decisions):
    """Bind persistent decisions to the current source rows, checking identities."""
    charts = {chart_key(row): c for c, row in enumerate(chart)}
    audio = defaultdict(list)
    for s, row in enumerate(summary):
        audio[audio_path(row["file_path"])].append(s)
    targets, stale = {}, []
    for record in decisions:
        c = charts.get(chart_key(record, "chart_"))
        candidates = audio.get(audio_path(record["file_path"]), [])
        candidates = [s for s in candidates if chart_key(summary[s]) == chart_key(record)]
        if c is None or len(candidates) != 1 or chart[c]["conflicts"]:
            stale.append(record["chart_song"])
        else:
            targets[c] = (candidates[0], record)
    return targets, stale


def apply_approvals(chart, summary, accepted, review, unavailable, decisions):
    targets, stale = approval_targets(chart, summary, decisions)
    reserved = {s: c for c, (s, _) in targets.items()}
    for c, (s, _) in list(accepted.items()):
        if c not in targets and s in reserved:
            if chart_key(chart[c])[:2] == chart_key(chart[reserved[s]])[:2]:
                continue  # Same song on another album; collapse after the join.
            del accepted[c]
            reason = "Recording reserved for another chart identity by a saved manual approval"
            review[c] = ({s: {"strong": set(), "weak": {reason}}}, [reason])
    for c, (s, record) in targets.items():
        method = ("Manual recording path connection" if record.get("connection_source") == "terminal"
                  else "Manual review approval")
        if "explicit/clean" in str(record.get("review_reason", "")).casefold():
            method += "; explicit/clean edition accepted"
        accepted[c] = (s, method)
        review.pop(c, None)
    unavailable[:] = [c for c in unavailable if c not in targets]
    return len(targets), stale


def quote_identifier(name):
    return '"' + name.replace('"', '""') + '"'


def write_table(connection, schema, name, headers, rows):
    """Bulk-load column arrays, including typed columns when there are no rows."""
    if len({header.casefold() for header in headers}) != len(headers):
        raise ValueError(f"Duplicate DuckDB columns in {schema}.{name}")
    parameters, expressions = [], []
    for index, header in enumerate(headers):
        values = [row[index] for row in rows]
        present = [value for value in values if value is not None]
        if present and all(isinstance(value, bool) for value in present):
            column_type = "BOOLEAN"
        elif present and all(isinstance(value, int) for value in present):
            column_type = "BIGINT"
        elif present and all(isinstance(value, Real) for value in present):
            column_type = "DOUBLE"
        elif re.fullmatch(r"\d{2}_\d{2}", header):
            column_type = "DOUBLE"
        elif header in {"row_number", "candidate_summary_row"}:
            column_type = "BIGINT"
        else:
            column_type = "VARCHAR"
            values = [str(value) if value is not None else None for value in values]
        expressions.append(f"unnest(?::{column_type}[]) AS {quote_identifier(header)}")
        parameters.append(values)
    connection.execute(
        f"CREATE OR REPLACE TABLE {quote_identifier(schema)}.{quote_identifier(name)} AS SELECT "
        + ", ".join(expressions), parameters,
    )


def resolve_inputs(essentia_root=None, summary_path=None, itunes_paths=None, approvals_file=None):
    source_root = Path(essentia_root or DEFAULT_ESSENTIA_ROOT).expanduser()
    summary_path = (Path(summary_path).expanduser() if summary_path else
                    find_full_summary((ROOT / "data", ROOT / "v2_results", source_root / "v2_results")))
    if summary_path is None:
        raise ValueError("Full Essentia summary not found. Use --summary PATH or --essentia-root DIRECTORY.")
    if itunes_paths is None:
        itunes_paths = [*sorted(ROOT.glob("batch*_itunes_matches.xlsx")),
                        *sorted((source_root / "combined_data").glob("batch*_itunes_matches.xlsx")),
                        *sorted((source_root / "Songs").glob("batch*_itunes_matches.xlsx")),
                        *sorted(source_root.glob("batch*_itunes_matches.xlsx")),
                        *sorted((source_root / "outputs").glob("batch*_itunes*/batch*_itunes_matches.xlsx"))]
    itunes_paths = list(dict.fromkeys(Path(path).expanduser().resolve() for path in itunes_paths))
    if approvals_file is None:
        local = ROOT / "joined_review_approvals.json"
        approvals_file = local if local.is_file() else source_root / "combined_data/joined_review_approvals.json"
    else:
        approvals_file = Path(approvals_file).expanduser()
        if not approvals_file.is_file():
            raise ValueError(f"Approval file not found: {approvals_file}")
    for path in (summary_path, *itunes_paths):
        if not path.is_file():
            raise ValueError(f"Input file not found: {path}")
    return summary_path, itunes_paths, approvals_file


def run_joined(connection, *, essentia_root=None, summary_path=None, itunes_paths=None,
               approvals_file=None, chart_path=None):
    """Rebuild the four join tables inside the caller's transaction."""
    summary_path, itunes_paths, approvals_file = resolve_inputs(
        essentia_root, summary_path, itunes_paths, approvals_file,
    )
    chart, periods, chart_rows, duplicates = (
        read_chart(Path(chart_path).expanduser()) if chart_path else read_rankings(connection)
    )
    headers, raw_summary = read_excel(summary_path, "Summary")
    if not {*FIELDS, "file_path"}.issubset(headers):
        raise ValueError("Essentia Summary must contain song, artist, album and file_path columns")
    summary = []
    for row in raw_summary:
        if "status" in headers and str(row["status"]).strip().casefold() != "success":
            continue
        if not all(row.get(key) for key in (*FIELDS, "file_path")):
            raise ValueError(f"Essentia row {row['_excel_row']} is missing song, artist, album or file_path")
        summary.append(row)
    required = {f"{prefix} {field}" for prefix in ("Requested", "Matched")
                for field in ("title", "artist", "album")} | {"Status"}
    mappings = []
    for path in itunes_paths:
        _, batch = read_excel(path, "Songs", required_headers=required)
        mappings.extend(batch)
    accepted, review, unavailable = find_matches(chart, summary, mappings)
    decisions = load_approvals(approvals_file)
    applied, stale = apply_approvals(chart, summary, accepted, review, unavailable, decisions)
    assert len(accepted) + len(review) + len(unavailable) == len(chart)
    uses = defaultdict(set)
    for c, (s, _) in accepted.items():
        uses[s].add(chart_key(chart[c])[:2])
    assert all(len(groups) == 1 for groups in uses.values())
    tables = build_tables(chart, periods, headers, summary, accepted, review, unavailable)
    preferred = {chart_key(row, "chart_") for row in decisions if row.get("preferred_chart_identity")}
    tables, removed_duplicates = deduplicate_joined(tables, preferred)
    assert len(tables[0][2]) + removed_duplicates == len(accepted)
    tables = build_removed_tab(tables)
    for schema in ("silver", "quarantine"):
        connection.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    counts = {}
    for tab, columns, rows in tables[:3]:
        schema, name = ("silver", "essentia_and_rankings") if tab == "joined" else ("quarantine", f"joined_{tab}")
        write_table(connection, schema, name, columns, rows)
        counts[f"{schema}.{name}"] = len(rows)
    # The Excel removed tab contains four independently headed audit sections.
    # Keep their union in one relational table and retain section and audit action.
    removed_headers = ["category", "row_number", "chart_song", "chart_artist", "chart_album",
                       "action", "score_notes", "note"]
    removed_rows = []
    for category, columns, rows, note in tables[3][2]:
        for values in rows:
            record = dict(zip(columns, values))
            record.update(category=category, note=note)
            removed_rows.append([record.get(column) for column in removed_headers])
    write_table(connection, "quarantine", "joined_removed", removed_headers, removed_rows)
    counts["quarantine.joined_removed"] = len(removed_rows)
    print(f"Essentia summary: {summary_path}")
    print(f"Join source: {chart_path or 'silver.rankings'}; {chart_rows:,} weekly rows; {len(periods)} weeks")
    print(f"Saved join approvals applied: {applied}; stale/out-of-scope approvals: {len(stale)}; "
          f"identical chart scores collapsed: {duplicates}")
    return counts


def add_join_arguments(parser):
    parser.add_argument("--essentia-root", type=Path, help=f"Essentia project directory (default: {DEFAULT_ESSENTIA_ROOT})")
    parser.add_argument("--summary", type=Path, help="Full Essentia XLSX with a Summary sheet")
    parser.add_argument("--itunes", type=Path, nargs="+", help="Specific iTunes mapping workbooks")
    parser.add_argument("--approvals-file", type=Path, help="Existing saved join approvals JSON (read only)")
    parser.add_argument("--chart", type=Path, help="Override silver.rankings with the original chart CSV")


def join_options(args):
    return dict(essentia_root=args.essentia_root, summary_path=args.summary, itunes_paths=args.itunes,
                approvals_file=args.approvals_file, chart_path=args.chart)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "data/Final_Project.duckdb")
    add_join_arguments(parser)
    args = parser.parse_args(argv)
    if not args.database.is_file():
        parser.error(f"Run bronze.py and silver.py first to create {args.database}")
    with duckdb.connect(str(args.database)) as connection:
        connection.execute("BEGIN TRANSACTION")
        try:
            counts = run_joined(connection, **join_options(args))
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
    for table, count in counts.items():
        print(f"{table}: {count:,} rows")


if __name__ == "__main__":
    sys.exit(main())

