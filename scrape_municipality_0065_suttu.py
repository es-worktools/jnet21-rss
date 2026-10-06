import re
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree

import requests
from bs4 import BeautifulSoup

SOURCE_URL = "https://www.town.suttu.lg.jp/"
OUTPUT_FILE = "municipality-0065-suttu.xml"
CHANNEL_TITLE = "0065_北海道寿都町"
ALLOWED_DOMAIN = "www.town.suttu.lg.jp"
MAX_ITEMS = 30

HEADERS = {
    "User-Agent": "Mozilla/5.0",
}

DATE_PATTERNS = [
    re.compile(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日"),
    re.compile(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})"),
]


def normalize(text):
    return re.sub(r"\s+", " ", text or "").strip()


def find_date(text):
    for pattern in DATE_PATTERNS:
        m = pattern.search(text)
        if m:
            return tuple(map(int, m.groups()))
    return None


def extract_date(anchor):
    own = normalize(anchor.get_text(" ", strip=True))
    date_tuple = find_date(own)
    if date_tuple:
        return date_tuple

    node = anchor
    for _ in range(4):
        node = getattr(node, "parent", None)
        if node is None:
            break

        text = normalize(node.get_text(" ", strip=True))
        if len(text) <= 600:
            date_tuple = find_date(text)
            if date_tuple:
                return date_tuple

        sibling = node.find_previous_sibling()
        checked = 0
        while sibling is not None and checked < 3:
            text = normalize(sibling.get_text(" ", strip=True))
            if text and len(text) <= 250:
                date_tuple = find_date(text)
                if date_tuple:
                    return date_tuple
                checked += 1
            sibling = sibling.find_previous_sibling()

    return None


response = requests.get(SOURCE_URL, headers=HEADERS, timeout=60)
response.raise_for_status()
response.encoding = response.apparent_encoding
soup = BeautifulSoup(response.text, "html.parser")

items = []
seen = set()

for anchor in soup.find_all("a", href=True):
    title = normalize(anchor.get_text(" ", strip=True))
    if not title or len(title) < 3:
        continue

    date_tuple = extract_date(anchor)
    if not date_tuple:
        continue

    url = urljoin(SOURCE_URL, anchor["href"])
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        continue
    if parsed.netloc != ALLOWED_DOMAIN:
        continue
    if url in seen:
        continue

    clean_title = title
    for pattern in DATE_PATTERNS:
        clean_title = pattern.sub("", clean_title)
    clean_title = re.sub(r"^[\s（()）・:：\-]+", "", clean_title)
    if not clean_title:
        continue

    seen.add(url)
    items.append((date_tuple, clean_title, url))

items.sort(key=lambda x: x[0], reverse=True)
items = items[:MAX_ITEMS]

if not items:
    raise RuntimeError("No dated items found")

rss = Element("rss", version="2.0")
channel = SubElement(rss, "channel")
SubElement(channel, "title").text = CHANNEL_TITLE
SubElement(channel, "link").text = SOURCE_URL
SubElement(channel, "description").text = f"{CHANNEL_TITLE} GitHub generated RSS"

jst = timezone(timedelta(hours=9))

for (year, month, day), item_title, url in items:
    item = SubElement(channel, "item")
    SubElement(item, "title").text = item_title
    SubElement(item, "link").text = url
    SubElement(item, "guid").text = url
    SubElement(item, "pubDate").text = format_datetime(
        datetime(year, month, day, tzinfo=jst)
    )

ElementTree(rss).write(
    OUTPUT_FILE,
    encoding="utf-8",
    xml_declaration=True,
)

print(OUTPUT_FILE, len(items))
