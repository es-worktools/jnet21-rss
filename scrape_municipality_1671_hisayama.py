import json, re, time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
from urllib.request import Request, build_opener, HTTPCookieProcessor
from http.cookiejar import CookieJar
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree, parse
from pathlib import Path
from lxml import html

SOURCE_URL = 'https://www.town.hisayama.fukuoka.jp/info_list.html'
DATA_URL = 'https://www.town.hisayama.fukuoka.jp/index.update.json'
OUTPUT_FILE = 'municipality-1671-hisayama.xml'
CHANNEL_TITLE = '1671_福岡県久山町'
ALLOWED_DOMAIN = urlparse(SOURCE_URL).netloc
MAX_ITEMS = 30
JST = timezone(timedelta(hours=9))
OPENER = build_opener(HTTPCookieProcessor(CookieJar()))

def normalize(text):
    return re.sub(r"\s+", " ", (text or "").replace("\u00ad", "")).strip()

def fetch(url):
    for attempt in range(4):
        try:
            request = Request(url, headers={"User-Agent":"Mozilla/5.0", "Accept":"application/json,text/html;q=0.9,*/*;q=0.8", "Referer":SOURCE_URL})
            with OPENER.open(request, timeout=60) as response:
                if urlparse(response.url).netloc != ALLOWED_DOMAIN:
                    raise RuntimeError("Unexpected redirect domain")
                return response.read().decode("utf-8-sig")
        except Exception:
            if attempt == 3: raise
            time.sleep(2 ** attempt)

def one(node, xpath):
    nodes = node.xpath(xpath)
    if len(nodes) != 1: raise RuntimeError("Official news structure changed: " + xpath)
    return nodes[0]

def official_date(text):
    match = re.fullmatch(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日", normalize(text))
    if not match: raise RuntimeError("Official date missing: " + text)
    return datetime(*map(int, match.groups()), tzinfo=JST)

def parse_source(text, now, cutoff):
    data = json.loads(text)
    if not isinstance(data, list) or not data:
        raise RuntimeError("Official news JSON missing")

    items = {}
    deferred_urls = set()
    deferred_count = 0
    for row in data:
        if row["is_category_index"] or row["is_keitai_page"]:
            continue
        date = datetime.fromisoformat(row["publish_datetime"])
        if date.utcoffset() is None:
            raise RuntimeError(f"Official date has no timezone: {row['url']!r}")
        if date < cutoff:
            continue

        title = normalize(row["page_name"])
        href = row["url"]
        if not title or not href:
            raise RuntimeError("Missing article title or URL")
        url = urljoin(SOURCE_URL, href)
        parsed_url = urlparse(url)
        if parsed_url.scheme not in {"http", "https"} or parsed_url.netloc != ALLOWED_DOMAIN:
            raise RuntimeError("Unexpected article URL: " + url)

        if date > now:
            print(f"Deferred (future publication date {date.isoformat()}): {title} | {url}")
            deferred_urls.add(url)
            deferred_count += 1
            continue
        items.setdefault(url, (date, title, url))

    print(f"Deferred rows: {deferred_count}")
    return items, deferred_urls


def check_previous_count(output, count, cutoff, deferred_urls):
    if not output.exists():
        return
    previous = parse(output).findall("./channel/item")
    # The existing 90-day window and newly deferred URLs can legitimately lower the count.
    expected = sum(
        parsedate_to_datetime(item.findtext("pubDate")) >= cutoff
        for item in previous
        if item.findtext("link") not in deferred_urls
    )
    if count < expected:
        raise RuntimeError(
            f"Unexpected item count decrease: {count} < {expected} "
            "eligible previous items; existing RSS preserved"
        )


def main():
    if DATA_URL != SOURCE_URL:
        fetch(SOURCE_URL)
    data = fetch(DATA_URL)
    now = datetime.now(JST)
    cutoff = now - timedelta(days=90)
    items, deferred_urls = parse_source(data, now, cutoff)
    if not items:
        raise RuntimeError("No articles found; existing RSS preserved")

    # Sort by publication date, keeping the source order for equal dates.
    rows = sorted(items.values(), key=lambda row: row[0], reverse=True)[:MAX_ITEMS]
    output = Path(OUTPUT_FILE)
    check_previous_count(output, len(rows), cutoff, deferred_urls)
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = CHANNEL_TITLE
    SubElement(channel, "link").text = SOURCE_URL
    SubElement(channel, "description").text = CHANNEL_TITLE + " GitHub generated RSS"
    for date, title, url in rows:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = title
        SubElement(item, "link").text = url
        SubElement(item, "guid", isPermaLink="true").text = url
        SubElement(item, "pubDate").text = format_datetime(date)
    temp = Path(OUTPUT_FILE + ".tmp")
    ElementTree(rss).write(temp, encoding="utf-8", xml_declaration=True)
    temp.replace(output)
    print(OUTPUT_FILE, len(rows))

if __name__ == "__main__": main()
