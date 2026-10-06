from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree

import requests
from bs4 import BeautifulSoup

SOURCE_URL = "https://www.city.nemuro.hokkaido.jp/lifeinfo/kakuka/suisankeizaibu/shoukoukankou/new/index.html"
OUTPUT_FILE = "municipality-0033-nemuro.xml"
CHANNEL_TITLE = "0033_北海道根室市"
ALLOWED_DOMAIN = "www.city.nemuro.hokkaido.jp"
TARGET_PATH = "/lifeinfo/kakuka/suisankeizaibu/shoukoukankou/"
MAX_ITEMS = 30

HEADERS = {
    "User-Agent": "Mozilla/5.0",
}


def normalize_title(text):
    return " ".join((text or "").split()).strip()


response = requests.get(SOURCE_URL, headers=HEADERS, timeout=60)
response.raise_for_status()
response.encoding = response.apparent_encoding
soup = BeautifulSoup(response.text, "html.parser")

heading = soup.find("h1")
start = heading if heading else soup

items = []
seen = set()

for anchor in start.find_all_next("a", href=True):
    title = normalize_title(anchor.get_text(" ", strip=True))
    if not title or len(title) < 3:
        continue

    url = urljoin(SOURCE_URL, anchor["href"])
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        continue
    if parsed.netloc != ALLOWED_DOMAIN:
        continue
    if TARGET_PATH not in parsed.path:
        continue
    if parsed.path.endswith("/new/index.html"):
        continue
    if parsed.path.rstrip("/").endswith("/shoukoukankou"):
        continue
    if url in seen:
        continue

    seen.add(url)
    items.append((title, url))

    if len(items) >= MAX_ITEMS:
        break

if not items:
    raise RuntimeError("No business-news items found")

rss = Element("rss", version="2.0")
channel = SubElement(rss, "channel")
SubElement(channel, "title").text = CHANNEL_TITLE
SubElement(channel, "link").text = SOURCE_URL
SubElement(channel, "description").text = f"{CHANNEL_TITLE} GitHub generated RSS"

for title, url in items:
    item = SubElement(channel, "item")
    SubElement(item, "title").text = title
    SubElement(item, "link").text = url
    SubElement(item, "guid").text = url

ElementTree(rss).write(
    OUTPUT_FILE,
    encoding="utf-8",
    xml_declaration=True,
)

print(OUTPUT_FILE, len(items))
