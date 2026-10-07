import re
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

SOURCES = ['https://www.town.ozora.hokkaido.jp/']
SOURCE_URL = 'https://www.town.ozora.hokkaido.jp/'
OUTPUT_FILE = 'municipality-0146-ozora.xml'
CHANNEL_TITLE = '0146_北海道大空町'
ALLOWED_DOMAIN = urlparse(SOURCE_URL).netloc
MAX_ITEMS = 30
JST = timezone(timedelta(hours=9))
DATE_RE = re.compile(r"(20\d{2})(?:年|[./-])\s*(\d{1,2})(?:月|[./-])\s*(\d{1,2})")


def normalize(text):
    return re.sub(r"\s+", " ", text or "").strip()


def fetch(url):
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    retry = Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    response = session.get(url, timeout=60)
    response.raise_for_status()
    if urlparse(response.url).netloc != ALLOWED_DOMAIN:
        raise RuntimeError("Unexpected redirect domain")
    response.encoding = "utf-8"
    return response


def add(items, title, href, date_text, base_url):
    title = normalize(title)
    date_match = DATE_RE.search(date_text)
    if not title or not date_match:
        raise RuntimeError("Article is missing its title or date")
    if "T" in date_text:
        date = datetime.fromisoformat(date_text.replace("Z", "+00:00"))
        if date.tzinfo is None:
            raise RuntimeError("Official timestamp has no timezone")
        date = date.astimezone(JST)
        if date > datetime.now(JST):
            return
    else:
        date = datetime(*map(int, date_match.groups()), tzinfo=JST)
        if date.date() > datetime.now(JST).date():
            return
    url = urljoin(base_url, href)
    if urlparse(url).scheme not in {"http", "https"} or urlparse(url).netloc != ALLOWED_DOMAIN:
        raise RuntimeError("Unexpected article URL")
    if url not in items or items[url][0] < date:
        items[url] = (date, title, url)


def parse_source(response, source_url, items):
    soup = BeautifulSoup(response.text, "html.parser")
    blocks = soup.select(".pageListDynBlock[data-url]")
    blocks = [b for b in blocks if b["data-url"].endswith("/index.update.json")]
    if not blocks:
        raise RuntimeError("Official dynamic news endpoint not found")
    endpoint = urljoin(source_url, blocks[0]["data-url"])
    data = fetch(endpoint).json()
    if not isinstance(data, list) or not data:
        raise RuntimeError("Official update JSON is empty or changed")
    seen = set()
    for row in data:
        required = {"page_no", "page_name", "url", "publish_datetime", "is_category_index", "is_keitai_page"}
        if not isinstance(row, dict) or not required.issubset(row):
            raise RuntimeError("Official update JSON schema changed")
        if row["is_category_index"] or row["is_keitai_page"] or row["page_no"] in seen:
            continue
        add(items, row["page_name"], row["url"], row["publish_datetime"], endpoint)
        seen.add(row["page_no"])


def main():
    items = {}
    for url in SOURCES:
        parse_source(fetch(url), url, items)
    if not items:
        raise RuntimeError("No dated articles found; existing RSS preserved")
    rows = sorted(items.values(), key=lambda row: row[0], reverse=True)[:MAX_ITEMS]
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
    # Only replace the feed after all source lists have parsed successfully.
    temp = Path(OUTPUT_FILE + ".tmp")
    ElementTree(rss).write(temp, encoding="utf-8", xml_declaration=True)
    temp.replace(OUTPUT_FILE)
    print(OUTPUT_FILE, len(rows))


if __name__ == "__main__":
    main()

