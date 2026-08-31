import ast
import hashlib
import re
import requests
from urllib.parse import urljoin
from xml.etree.ElementTree import Element, SubElement, ElementTree

BASE_URL = "https://www.icnet.or.jp/"

SOURCES = [
    {
        "name": "石川県中央会から",
        "url": (
            "https://www.icnet.or.jp/"
            "iensystem/iendbjs.cgi"
            "?mode=jss&cate=infoicnet&opt=nosty"
        ),
    },
    {
        "name": "行政・関係機関から",
        "url": (
            "https://www.icnet.or.jp/"
            "iensystem/iendbjs.cgi"
            "?mode=jss&cate=infoinsti&opt=nosty"
        ),
    },
]

OUTPUT_FILE = "chuokai-ishikawa.xml"
MAX_ITEMS = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": BASE_URL,
}


def normalize_link(raw_link):
    raw_link = raw_link.strip()

    # 先頭の表示制御コードを除去
    if raw_link.startswith("se+"):
        raw_link = raw_link[3:]
    elif raw_link.startswith("bl+"):
        raw_link = raw_link[3:]

    return urljoin(BASE_URL, raw_link)


def parse_source(source):
    response = requests.get(
        source["url"],
        headers=HEADERS,
        timeout=60,
    )
    response.raise_for_status()
    response.encoding = response.apparent_encoding

    items = []

    pattern = re.compile(
        r"d\[i\]=(\[.*?\]);"
    )

    for match in pattern.finditer(response.text):
        raw_array = match.group(1)

        try:
            values = ast.literal_eval(raw_array)
        except Exception:
            continue

        if len(values) < 7:
            continue

        item_id = str(values[0]).strip()
        published = str(values[1]).strip()
        title = str(values[5]).strip()
        raw_link = str(values[6]).strip()

        title = re.sub(r"\s+", " ", title)

        if not title or not raw_link:
            continue

        url = normalize_link(raw_link)

        items.append({
            "id": item_id,
            "date": published,
            "title": title,
            "url": url,
            "source": source["name"],
        })

    return items


all_items = []

for source in SOURCES:
    all_items.extend(
        parse_source(source)
    )

if not all_items:
    raise RuntimeError(
        "RSS対象を1件も取得できませんでした"
    )

# 掲載日の新しい順
all_items.sort(
    key=lambda x: (
        x["date"],
        x["id"],
    ),
    reverse=True,
)

# URL＋タイトルで重複除去
items = []
seen = set()

for entry in all_items:
    key = (
        entry["title"],
        entry["url"],
    )

    if key in seen:
        continue

    seen.add(key)
    items.append(entry)

    if len(items) >= MAX_ITEMS:
        break

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
).text = "石川県中小企業団体中央会 お知らせ"

SubElement(
    channel,
    "link",
).text = BASE_URL

SubElement(
    channel,
    "description",
).text = (
    "石川県中小企業団体中央会および"
    "行政・関係機関からのお知らせ"
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
    ).text = entry["url"]

    unique_id = hashlib.sha256(
        (
            entry["id"]
            + "|"
            + entry["title"]
            + "|"
            + entry["url"]
        ).encode("utf-8")
    ).hexdigest()

    SubElement(
        item,
        "guid",
    ).text = (
        f"urn:chuokai-ishikawa:{unique_id}"
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
