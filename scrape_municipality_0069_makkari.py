import re
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree

import requests
from bs4 import BeautifulSoup

SOURCE_URL = "https://www.vill.makkari.lg.jp/news/"
OUTPUT_FILE = "municipality-0069-makkari.xml"
CHANNEL_TITLE = "0069_北海道真狩村"
ALLOWED_DOMAIN = "www.vill.makkari.lg.jp"
MAX_ITEMS = 30

HEADERS = {
    "User-Agent": "Mozilla/5.0",
}

DATE_PATTERNS = [
    re.compile(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日"),
    re.compile(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})"),
]

WEEKDAY_RE = re.compile(r"^[（(][月火水木金土日](?:曜日?)?[）)]\s*")
CATEGORY_RE = re.compile(r"^(お知らせ|行政情報|くらしの情報|観光・イベント|観光・遊び|健康・福祉|しごと・産業|町政)\s+")


def normalize(text):
    return re.sub(r"\s+", " ", text or "").strip()


def find_date(text):
    for pattern in DATE_PATTERNS:
        m = pattern.search(text)
        if m:
            return tuple(map(int, m.groups()))
    return None


response = requests.get(SOURCE_URL, headers=HEADERS, timeout=60)
response.raise_for_status()
response.encoding = response.apparent_encoding
soup = BeautifulSoup(response.text, "html.parser")

items = []
seen = set()

for anchor in soup.find_all("a", href=True):
    raw_title = normalize(anchor.get_text(" ", strip=True))
    if not raw_title or len(raw_title) < 3:
        continue

    date_tuple = find_date(raw_title)
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

    clean_title = raw_title
    for pattern in DATE_PATTERNS:
        clean_title = pattern.sub("", clean_title)
    clean_title = WEEKDAY_RE.sub("", clean_title)
    clean_title = normalize(clean_title)
    clean_title = CATEGORY_RE.sub("", clean_title)
    clean_title = re.sub(r"^(NEW\s*)+", "", clean_title, flags=re.IGNORECASE)
    clean_title = re.sub(r"^[\s・:：\-]+", "", clean_title).strip()
    clean_title = re.sub(r"\(\s*\)|（\s*）", "", clean_title).strip()

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
