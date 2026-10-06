from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree

import requests
from bs4 import BeautifulSoup

SOURCE_URL = "https://www.town.shikabe.lg.jp/shigoto_sangyo/index.html"
OUTPUT_FILE = "municipality-0053-shikabe.xml"
CHANNEL_TITLE = "0053_北海道鹿部町"
ALLOWED_DOMAIN = "www.town.shikabe.lg.jp"
TARGET_PREFIX = "/shigoto_sangyo/"
MAX_ITEMS = 40

HEADERS = {
    "User-Agent": "Mozilla/5.0",
}


def normalize_title(text):
    return " ".join((text or "").split()).strip()


response = requests.get(SOURCE_URL, headers=HEADERS, timeout=60)
response.raise_for_status()
response.encoding = response.apparent_encoding
soup = BeautifulSoup(response.text, "html.parser")

h1 = soup.find("h1")
scope = h1.parent if h1 and h1.parent else soup

items = []
seen = set()

for anchor in scope.find_all("a", href=True):
    title = normalize_title(anchor.get_text(" ", strip=True))
    if not title or len(title) < 3:
        continue

    url = urljoin(SOURCE_URL, anchor["href"])
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        continue
    if parsed.netloc != ALLOWED_DOMAIN:
        continue
    if not parsed.path.startswith(TARGET_PREFIX):
        continue
    if parsed.path.endswith("/index.html"):
        continue
    if url in seen:
        continue

    seen.add(url)
    items.append((title, url))

if not items:
    raise RuntimeError("No business/industry items found")

items = items[:MAX_ITEMS]

rss = Element("rss", version="2.0")
channel = SubElement(rss, "channel")
SubElement(channel, "title").text = CHANNEL_TITLE
SubElement(channel, "link").text = SOURCE_URL
SubElement(channel, "description").text = f"{CHANNEL_TITLE} GitHub generated RSS"

for item_title, url in items:
    item = SubElement(channel, "item")
    SubElement(item, "title").text = item_title
    SubElement(item, "link").text = url
    SubElement(item, "guid").text = url

ElementTree(rss).write(
    OUTPUT_FILE,
    encoding="utf-8",
    xml_declaration=True,
)

print(OUTPUT_FILE, len(items))
