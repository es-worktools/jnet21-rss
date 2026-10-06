import re
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree

import requests
from bs4 import BeautifulSoup

SOURCE_URL = "https://www.town.shikabe.lg.jp/shigoto_sangyo/index.html"
OUTPUT_FILE = "municipality-0053-shikabe-news.xml"
CHANNEL_TITLE = "0053_北海道鹿部町"
ALLOWED_DOMAIN = "www.town.shikabe.lg.jp"
MAX_ITEMS = 30

HEADERS = {
    "User-Agent": "Mozilla/5.0",
}

DATE_PATTERNS = [
    re.compile(r"(20\\d{2})年\\s*(\\d{1,2})月\\s*(\\d{1,2})日"),
    re.compile(r"(20\\d{2})[./-](\\d{1,2})[./-](\\d{1,2})"),
]


def normalize(text):
    return re.sub(r"\\s+", " ", text or "").strip()


def find_date(text):
    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            return tuple(map(int, match.groups()))
    return None


response = requests.get(SOURCE_URL, headers=HEADERS, timeout=60)
response.raise_for_status()
response.encoding = response.apparent_encoding
soup = BeautifulSoup(response.text, "html.parser")

heading = None
for h2 in soup.find_all("h2"):
    if "新着情報" in normalize(h2.get_text(" ", strip=True)):
        heading = h2
        break

if heading is None:
    raise RuntimeError("New-information heading not found")

items = []
seen = set()

for sibling in heading.find_next_siblings():
    if sibling.name == "h2":
        break

    for anchor in sibling.find_all("a", href=True):
        title = normalize(anchor.get_text(" ", strip=True))
        title = re.sub(r"^NEW!\\s*", "", title, flags=re.IGNORECASE)
        if not title:
            continue

        url = urljoin(SOURCE_URL, anchor["href"])
        parsed = urlparse(url)

        if parsed.scheme not in {"http", "https"}:
            continue
        if parsed.netloc != ALLOWED_DOMAIN:
            continue
        if url in seen:
            continue

        block_text = normalize(sibling.get_text(" ", strip=True))
        date_tuple = find_date(block_text)

        seen.add(url)
        items.append((date_tuple, title, url))

items = items[:MAX_ITEMS]

rss = Element("rss", version="2.0")
channel = SubElement(rss, "channel")
SubElement(channel, "title").text = CHANNEL_TITLE
SubElement(channel, "link").text = SOURCE_URL
SubElement(channel, "description").text = f"{CHANNEL_TITLE} しごと・産業 新着情報 GitHub generated RSS"

jst = timezone(timedelta(hours=9))

for date_tuple, item_title, url in items:
    item = SubElement(channel, "item")
    SubElement(item, "title").text = item_title
    SubElement(item, "link").text = url
    SubElement(item, "guid").text = url

    if date_tuple:
        year, month, day = date_tuple
        SubElement(item, "pubDate").text = format_datetime(
            datetime(year, month, day, tzinfo=jst)
        )

ElementTree(rss).write(
    OUTPUT_FILE,
    encoding="utf-8",
    xml_declaration=True,
)

print(OUTPUT_FILE, len(items))
