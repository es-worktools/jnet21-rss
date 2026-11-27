import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from email.utils import format_datetime
import hashlib
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from time import sleep
import unicodedata
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup, ParserRejectedMarkup


BASE_URL = "https://www.tohoku.meti.go.jp/"
RECENT_URL = urljoin(BASE_URL, "ml_tohoku_news_past_rss.html")
ARCHIVE_INDEX = urljoin(BASE_URL, "koho/koshin/archive.html")
OUTPUT_FILE = Path("tohoku-meti-event.xml")
JST = timezone(timedelta(hours=9))
MONITOR_NS = "urn:jnet21:tohoku-meti-event:monitor"
MONITOR = f"{{{MONITOR_NS}}}"
ET.register_namespace("monitor", MONITOR_NS)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Referer": BASE_URL,
}

SOURCE_URLS = [
    "https://www.tohoku.meti.go.jp/s_joho/index_joho.html",
    "https://www.tohoku.meti.go.jp/s_cyusyo/index_cyusyo.html",
    "https://www.tohoku.meti.go.jp/s_kokusai/index_kokusai.html",
    "https://www.tohoku.meti.go.jp/s_sangi_jinza/index_sanjin.html",
    "https://www.tohoku.meti.go.jp/s_shogyo/index_syogyo.html",
    "https://www.tohoku.meti.go.jp/s_shinki/index_venc.html",
    "https://www.tohoku.meti.go.jp/s_shigen_ene/syo_energy.html",
    "https://www.tohoku.meti.go.jp/kikaku/index_meetup.html",
]

EVENT_WORDS = re.compile(
    r"セミナー|説明会|相談会|フォーラム|イベント|講座|研修|シンポジウム|交流会|勉強会|"
    r"ワークショップ|発表会|表彰式|見学会|Meetup|ミートアップ|講演会|展示会|商談会",
    re.IGNORECASE,
)
INVITATION = re.compile(
    r"開催(?:します|のお知らせ|の御案内|のご案内|について|予定|と参加者)|開講(?:します|されます|のご案内)|"
    r"実施(?:します|のお知らせ|のご案内)|参加(?:者|企業|事業者).{0,20}(?:募集|公募)|"
    r"参加(?:申込|受付)|受講者.{0,15}募集|申込(?:受付|期限)"
)
EXCLUDED = re.compile(
    r"採用(?:試験|情報|説明会|案内|選考|募集)|(?:選考|経験者|職員|新卒|公務員)採用|官庁訪問|"
    r"国家公務員|インターンシップ(?:の募集|参加者募集)|"
    r"開催(?:しました|されました|報告|結果|実績)|実施(?:しました|報告|結果)|"
    r"(?:アーカイブ|収録)動画.{0,18}(?:配信|公開)|開催を中止|勉強会を設置|"
    r"登壇(?:者|企業)を決定|表彰(?:者|受賞者)を決定"
)
NAVIGATION = re.compile(r"^(?:各種)?(?:セミナー|イベント|説明会|相談会|研修)(?:等|等情報|一覧|情報)?$")
JAPANESE_DATE = r"([0-9]{4})年\s*([0-9]{1,2})月\s*([0-9]{1,2})日"
FIELD_DATE = re.compile(r"\[\s*" + JAPANESE_DATE + r"\s*(公開|掲載|更新)?\s*\]")
ARCHIVE_FRAGMENT = re.compile(
    r"""loadHtml\(\s*['"]#news_menulist['"]\s*,\s*['"](/ml_tohoku_news_[0-9]{4}\.html)['"]\s*\)"""
)
RECENT_MINIMUM = 16
FIELD_MINIMUM = 8

# One-time recovery review. Date-only deadlines are treated as end of day in Japan.
# With no published cutoff, the known start time is the latest eligible instant.
REVIEWED_THROUGH = date(2026, 11, 27)
BACKFILL_UNTIL = {
    "/2026/261125_2.html": "2026-12-15T17:00",
    "/2026/261119.html": "2026-12-02T00:00",
    "/2026/261113.html": "2026-12-11T17:00",
    "/2026/261116.html": "2027-01-20T17:00",
    "/2026/261113_2.html": "2026-12-04T17:00",
    "/2026/261112.html": "2026-12-08T17:00",
    "/2026/261112_2.html": "2026-11-30T17:00",
    "/2026/261110.html": "2026-11-30T13:00",
    "/2026/261110_2.html": "2026-12-02T18:00",
    "/2026/261106_2.html": "2026-11-28T00:00",
    "/2026/261022001.html": "2026-12-14T13:00",
}


@dataclass(frozen=True)
class Event:
    title: str
    url: str | None
    published: date | None
    category: str = ""
    listed: date | None = None


def page(url):
    for delay in (0, 2, 4):
        if delay:
            sleep(delay)
        response = requests.get(url, headers=HEADERS, timeout=(10, 25))
        if response.status_code not in {202, 502, 503, 504}:
            break
    response.raise_for_status()
    if (response.status_code != 200 or urlsplit(response.url).netloc != urlsplit(BASE_URL).netloc
            or "text/html" not in response.headers.get("Content-Type", "").lower()):
        raise ValueError(f"Unexpected response for {url}: HTTP {response.status_code} {response.url}")
    return BeautifulSoup(response.content, "html.parser", from_encoding="utf-8")


def article_url(href, source):
    if not href or href.startswith("#"):
        return None
    parts = urlsplit(urljoin(source, href.strip()))
    if (parts.scheme not in {"https", "http"} or parts.netloc.lower() != urlsplit(BASE_URL).netloc
            or not parts.path.lower().endswith((".html", ".htm"))):
        return None
    query = urlencode([
        (key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
    ])
    return urlunsplit(("https", parts.netloc.lower(), parts.path, query, parts.fragment))


def url_key(url):
    parts = urlsplit(url)
    return parts._replace(fragment=unquote(parts.fragment)).geturl()


def title_key(title):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", title)).casefold()


def tag_text(tag):
    return " ".join(tag.get_text(" ", strip=True).split())


def match_date(match):
    return date(*(int(part) for part in match.groups()[:3]))


def topic_rows(soup, source, today):
    tags = soup.find_all("dt")
    if not tags:
        raise ValueError(f"No dated rows in {source}")

    rows = []
    for tag in tags:
        found = re.fullmatch(JAPANESE_DATE, tag_text(tag))
        if not found:
            raise ValueError(f"Invalid topic date in {source}: {tag_text(tag)}")
        day = match_date(found)
        block = tag.find_next_sibling()
        if day > today or block is None or block.name != "dd":
            raise ValueError(f"Unexpected date or missing article block in {source}: {day}")
        links = block.select("ul > li")
        if not links:
            raise ValueError(f"No articles under {day} in {source}")
        for li in links:
            icon = li.find("img", recursive=False)
            anchor = li.find("a", recursive=False)
            if not icon or not icon.get("alt") or not anchor or not anchor.get("href") or not tag_text(anchor):
                raise ValueError(f"Incomplete article under {day} in {source}")
            # The day on an update notice is the update date, not the first publication.
            title = tag_text(anchor)
            published = None if "更新しました" in title else day
            rows.append(Event(title, article_url(anchor["href"], source), published, icon["alt"], day))
    return sorted(rows, key=lambda row: row.listed, reverse=True)


def field_events(soup, source, today):
    content = soup.select_one("#__main_contents, #contents_left")
    if content is None:
        raise ValueError(f"Missing field content in {source}")
    anchors = content.select("a[href]")
    events = []
    for anchor in anchors:
        url = article_url(anchor["href"], source)
        if not url or url == source or url in SOURCE_URLS:
            continue
        li = anchor.find_parent("li")
        date_label = FIELD_DATE.search(unicodedata.normalize("NFKC", tag_text(li or anchor)))
        listed = match_date(date_label) if date_label else None
        title = FIELD_DATE.sub("", unicodedata.normalize("NFKC", tag_text(anchor))).strip()
        if listed and listed > today:
            if is_event(Event(title, url, None), from_field=True):
                raise ValueError(f"Future field publication in {source}: {listed}")
            continue
        published = listed if date_label and date_label[4] != "更新" and "更新しました" not in title else None
        event = Event(title, url, published, listed=listed)
        if is_event(event, from_field=True):
            events.append(event)
    return len(anchors), events


def is_event(event, *, from_field=False):
    title = unicodedata.normalize("NFKC", event.title)
    if not event.url or not title or NAVIGATION.fullmatch(title) or EXCLUDED.search(title):
        return False
    if event.category == "イベント":
        return True
    if not EVENT_WORDS.search(title):
        return False
    if INVITATION.search(title):
        return True
    # Unlabelled field notices need an article link and an event-specific title.
    # Public notices such as study-group establishment need evidence of an invitation.
    return from_field and "/topics/" in urlsplit(event.url).path and len(title) >= 15


def read_annual(today, fetch):
    index = fetch(ARCHIVE_INDEX)
    paths = set(ARCHIVE_FRAGMENT.findall(str(index)))
    if len(paths) != 1:
        raise ValueError(f"Expected one official annual topic reference in {ARCHIVE_INDEX}: {paths}")
    url = urljoin(ARCHIVE_INDEX, paths.pop())
    rows = topic_rows(fetch(url), url, today)
    print(f"Annual topics: {len(rows)} rows from {url}")
    return rows


def check_coverage(source, count, minimum, previous):
    if count < minimum or (previous is not None and count * 2 < previous):
        raise ValueError(f"Source coverage dropped: {source} ({previous} -> {count}, minimum {minimum})")
    print(f"Source coverage: {source} {count} rows/links")


def event_guid(key):
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return f"urn:tohoku-meti-event:{digest}"


def atomic_write(path, data):
    with NamedTemporaryFile(dir=path.parent, delete=False) as temp:
        temp_path = Path(temp.name)
        try:
            temp.write(data)
            temp.close()
            temp_path.replace(path)
        finally:
            temp_path.unlink(missing_ok=True)


def generate(output, now, fetch=page):
    today = now.astimezone(JST).date()
    original = output.read_bytes()
    root = ET.fromstring(original)
    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        raise ValueError("Existing feed is not RSS")
    old_items = channel.findall("item")
    old_guids = {item.findtext("guid") for item in old_items}
    if (not old_items or len(old_guids) != len(old_items) or not all(old_guids)
            or not all(item.findtext("title") and item.findtext("link") for item in old_items)):
        raise ValueError("Existing feed is empty or has invalid items")

    state = channel.find(f"{MONITOR}sources")
    first_run = state is None
    previous = {} if first_run else {
        row.attrib["url"]: row.attrib for row in state.findall(f"{MONITOR}source")
    }
    outages = {} if first_run else {
        row.attrib["url"]: date.fromisoformat(row.attrib["since"])
        for row in state.findall(f"{MONITOR}unavailable")
    }
    suppressed = set() if first_run else {
        row.attrib["guid"] for row in state.findall(f"{MONITOR}baseline")
    }
    coverage = {}
    recent = topic_rows(fetch(RECENT_URL), RECENT_URL, today)
    latest = recent[0].listed
    if not first_run and latest < date.fromisoformat(state.attrib["latest"]):
        raise ValueError(f"Recent topics regressed to {latest}")
    previous_recent = previous.get(RECENT_URL)
    check_coverage(RECENT_URL, len(recent), RECENT_MINIMUM,
                   int(previous_recent["count"]) if previous_recent else None)
    coverage[RECENT_URL] = {"url": RECENT_URL, "count": str(len(recent))}
    recent_events = [row for row in recent if is_event(row)]
    if not recent_events:
        print("Recent topics: valid listing with 0 event announcements")

    def read_field(url):
        last_good = previous.get(url)
        try:
            count, events = field_events(fetch(url), url, today)
            check_coverage(url, count, FIELD_MINIMUM, int(last_good["count"]) if last_good else None)
        except (requests.RequestException, ParserRejectedMarkup, ValueError) as error:
            message = f"Field source unavailable: {url}: {error}"
            if first_run:
                raise ValueError(message) from error
            print(f"WARNING {message}")
            return None
        return count, events

    with ThreadPoolExecutor(max_workers=4) as executor:
        fields = list(executor.map(read_field, SOURCE_URLS))
    field_only = []
    undated_on_recovery = []
    for url, result in zip(SOURCE_URLS, fields):
        last_good = previous.get(url, {})
        if result is None:
            if last_good:
                coverage[url] = last_good
            outages.setdefault(url, today)
            continue

        count, events = result
        baseline = {"url": url, "count": str(count)}
        floor = date.fromisoformat(last_good["from"]) if "from" in last_good else None
        if since := outages.pop(url, None):
            # Keep the catch-up within the recent topics window, with one day
            # of overlap for entries added before the first failing check.
            floor = max(floor or date.min, recent[-1].listed, since - timedelta(days=1))
            undated_on_recovery.extend(row for row in events if row.listed is None)
            events = [row for row in events if row.listed is not None]
            print(f"Field source recovered: {url} (dated catch-up from {floor})")
        if floor:
            baseline["from"] = floor.isoformat()
            events = [row for row in events if row.listed is None or row.listed >= floor]
        coverage[url] = baseline
        field_only.extend(events)

    active_paths = {
        path for path, deadline in BACKFILL_UNTIL.items()
        if now < datetime.fromisoformat(deadline).replace(tzinfo=JST)
    }
    # Read the current official year reference only for the one-time recovery.
    annual_events = []
    missing = active_paths - {urlsplit(row.url).path for row in recent_events}
    if first_run and missing:
        annual_events = [
            row for row in read_annual(today, fetch) if is_event(row) and urlsplit(row.url).path in missing
        ]
        missing -= {urlsplit(row.url).path for row in annual_events}
        if missing:
            raise ValueError(f"Missing reviewed backfill candidates: {sorted(missing)}")

    existing = {}
    base_and_title = {}
    for item in old_items:
        link = item.findtext("link")
        key = url_key(article_url(link, BASE_URL) or link)
        existing[key] = item
        base_and_title.setdefault((key.split("#")[0], title_key(item.findtext("title"))), set()).add(key)

    # Prefer recent topics, then the annual archive, then field-only links.
    candidates = recent_events + annual_events + field_only
    # An anchored and unanchored link with the same title can be an alias.
    for row in candidates + undated_on_recovery:
        key = url_key(row.url)
        base_and_title.setdefault((key.split("#")[0], title_key(row.title)), set()).add(key)

    def identity(row):
        key = url_key(row.url)
        aliases = base_and_title[(key.split("#")[0], title_key(row.title))]
        if len(aliases) == 2 and key.split("#")[0] in aliases:
            # Prefer the existing identity, or the deeper link for a new item.
            key = next((url for url in sorted(aliases) if url in existing), max(aliases, key=len))
            return key, aliases
        return key, {key}

    handled = set()
    added = []
    for row in candidates:
        key, aliases = identity(row)
        if key in handled or key in existing:
            continue
        guid = event_guid(key)
        approved = first_run and urlsplit(row.url).path in active_paths
        if not approved and row.listed and row.listed <= REVIEWED_THROUGH:
            continue
        if not approved and row.listed is None:
            if first_run:
                suppressed.update(event_guid(alias) for alias in aliases)
            if any(event_guid(alias) in suppressed for alias in aliases):
                continue

        handled.add(key)
        item = ET.Element("item")
        ET.SubElement(item, "title").text = row.title
        ET.SubElement(item, "link").text = key if key != url_key(row.url) else row.url
        ET.SubElement(item, "guid", isPermaLink="false").text = guid
        if row.published:
            ET.SubElement(item, "pubDate").text = format_datetime(datetime.combine(row.published, time(), JST))
        added.append((row.published or date.min, item))
        print(f"ADD {row.published or '-'} {row.category or 'field'} {row.url} {row.title}")

    # Undated links first seen on recovery may be old; remember their identities
    # so an unchanged snapshot cannot publish them on the next scheduled run.
    for row in undated_on_recovery:
        key, aliases = identity(row)
        if key not in handled and key not in existing:
            suppressed.update(event_guid(alias) for alias in aliases)

    if state is not None:
        channel.remove(state)
    state = ET.SubElement(channel, f"{MONITOR}sources", latest=latest.isoformat())
    for baseline in coverage.values():
        ET.SubElement(state, f"{MONITOR}source", baseline)
    for url, since in sorted(outages.items()):
        ET.SubElement(state, f"{MONITOR}unavailable", url=url, since=since.isoformat())
    for guid in sorted(suppressed):
        ET.SubElement(state, f"{MONITOR}baseline", guid=guid)
    for _, item in reversed(sorted(added, key=lambda entry: entry[0], reverse=True)):
        channel.insert(3, item)

    result_items = channel.findall("item")
    result_guids = {item.findtext("guid") for item in result_items}
    if len(result_guids) != len(result_items) or not old_guids <= result_guids:
        raise ValueError("Existing GUIDs missing or duplicate GUIDs detected")
    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    if data != original:
        atomic_write(output, data)
    print(f"{output}: {len(old_items)} preserved, {len(added)} added, {len(result_items)} total")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT_FILE)
    args = parser.parse_args()
    generate(args.output, datetime.now(JST))
