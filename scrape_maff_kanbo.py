import requests
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import Element, SubElement, ElementTree

SOURCE_RSS = "https://www.maff.go.jp/rss.xml"
BASE_URL = "https://www.maff.go.jp/j/kanbo/"
OUTPUT_FILE = "maff-kanbo.xml"
MAX_ITEMS = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    )
}

response = requests.get(
    SOURCE_RSS,
    headers=HEADERS,
    timeout=60,
)

response.raise_for_status()

root = ET.fromstring(response.content)

source_items = root.findall(".//item")

items = []

for source_item in source_items:
    title = (
        source_item.findtext("title", "")
        or ""
    ).strip()

    link = (
        source_item.findtext("link", "")
        or ""
    ).strip()

    pub_date = (
        source_item.findtext("pubDate", "")
        or ""
    ).strip()

    description = (
        source_item.findtext("description", "")
        or ""
    ).strip()

    # 農林水産省「基本政策」系の報道発表のみ
    if "/j/press/kanbo/" not in link:
        continue

    if not title or not link:
        continue

    items.append({
        "title": title,
        "link": link,
        "pub_date": pub_date,
        "description": description,
    })

    if len(items) >= MAX_ITEMS:
        break


if not items:
    raise RuntimeError(
        "基本政策の報道発表を1件も取得できませんでした"
    )


rss = Element(
    "rss",
    version="2.0",
)

channel = SubElement(
    rss,
    "channel",
)

SubElement(
    channel,
    "title",
).text = "農林水産省 基本政策"

SubElement(
    channel,
    "link",
).text = BASE_URL

SubElement(
    channel,
    "description",
).text = (
    "農林水産省「基本政策」に関する報道発表"
)

for entry in items:
    item = SubElement(
        channel,
        "item",
    )

    SubElement(
        item,
        "title",
    ).text = entry["title"]

    SubElement(
        item,
        "link",
    ).text = entry["link"]

    guid = SubElement(
        item,
        "guid",
    )
    guid.set("isPermaLink", "true")
    guid.text = entry["link"]

    if entry["pub_date"]:
        SubElement(
            item,
            "pubDate",
        ).text = entry["pub_date"]

    if entry["description"]:
        SubElement(
            item,
            "description",
        ).text = entry["description"]


ElementTree(rss).write(
    OUTPUT_FILE,
    encoding="utf-8",
    xml_declaration=True,
)

print(
    OUTPUT_FILE,
    len(items),
)
