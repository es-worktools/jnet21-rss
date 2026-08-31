import hashlib
import re
import requests
from urllib.parse import urljoin
from xml.etree.ElementTree import Element, SubElement, ElementTree

SOURCE_URL = "https://www.jsps.go.jp/"
JSON_URL = "https://www.jsps.go.jp/include/news/inform_ja.json"
OUTPUT_FILE = "jsps-recruit.xml"
MAX_ITEMS = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
}

response = requests.get(
    JSON_URL,
    headers=HEADERS,
    timeout=60,
)

response.raise_for_status()
data = response.json()

items = []
seen_urls = set()

for entry in data:
    # 募集案内のみ
    if entry.get("news_category") != "2":
        continue

    title = entry.get("title", "")
    title = re.sub(r"\s+", " ", title).strip()

    if not title:
        continue

    path = entry.get("site_url", "").strip()

    if not path:
        continue

    url = urljoin(SOURCE_URL, path)

    if url in seen_urls:
        continue

    seen_urls.add(url)

    items.append({
        "title": title,
        "url": url,
        "date": entry.get("news_date", ""),
    })

# 念のため新しい順に並べる
items.sort(
    key=lambda x: x["date"],
    reverse=True,
)

items = items[:MAX_ITEMS]

if not items:
    raise RuntimeError(
        "RSS対象を1件も取得できませんでした"
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
).text = "日本学術振興会 募集案内"

SubElement(
    channel,
    "link",
).text = SOURCE_URL

SubElement(
    channel,
    "description",
).text = "日本学術振興会の募集案内"

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
    ).text = entry["url"]

    unique_id = hashlib.sha256(
        (
            entry["title"]
            + "|"
            + entry["url"]
        ).encode("utf-8")
    ).hexdigest()

    SubElement(
        item,
        "guid",
    ).text = (
        f"urn:jsps-recruit:{unique_id}"
    )

ElementTree(rss).write(
    OUTPUT_FILE,
    encoding="utf-8",
    xml_declaration=True,
)

print(
    OUTPUT_FILE,
    len(items),
)
