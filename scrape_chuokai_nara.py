import hashlib
import json
import requests
from datetime import datetime
from xml.etree.ElementTree import Element, SubElement, ElementTree

BASE_URL = "https://www.chuokai-nara.or.jp/chuokai/"
API_URL = (
    "https://www.chuokai-nara.or.jp/"
    "chuokai/contents/kumiai/search_kumiai_news"
)

OUTPUT_FILE = "chuokai-nara.xml"
MAX_ITEMS = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": BASE_URL,
}


def is_target(item):
    if str(item.get("c_flag10")) != "1":
        return False

    return any(
        str(item.get(flag)) == "1"
        for flag in (
            "c_flag1",
            "c_flag2",
            "c_flag3",
        )
    )


def get_date(item):
    value = item.get("c_info3")

    if value:
        return str(value).strip()

    value = item.get("c_date1")

    if value:
        return str(value).strip()

    return ""


response = requests.post(
    API_URL,
    headers=HEADERS,
    data={"data": "news"},
    timeout=60,
)

response.raise_for_status()

# APIレスポンスにはUTF-8 BOMが付いている
text = response.content.decode("utf-8-sig")
data = json.loads(text)

items = []

for entry in data:
    if not is_target(entry):
        continue

    news_id = str(
        entry.get("news_id") or ""
    ).strip()

    title = str(
        entry.get("c_title1") or ""
    ).strip()

    date = get_date(entry)

    if not news_id or not title:
        continue

    url = (
        BASE_URL
        + "news.php/"
        + news_id
    )

    items.append({
        "id": news_id,
        "title": title,
        "date": date,
        "url": url,
    })

if not items:
    raise RuntimeError(
        "RSS対象を1件も取得できませんでした"
    )


def sort_key(item):
    value = item["date"]

    for fmt in (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(
                value,
                fmt,
            )
        except ValueError:
            pass

    return datetime.min


items.sort(
    key=sort_key,
    reverse=True,
)

# URL＋タイトルで重複除去
deduped = []
seen = set()

for entry in items:
    key = (
        entry["title"],
        entry["url"],
    )

    if key in seen:
        continue

    seen.add(key)
    deduped.append(entry)

    if len(deduped) >= MAX_ITEMS:
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
).text = "奈良県中小企業団体中央会 お知らせ"

SubElement(
    channel,
    "link",
).text = BASE_URL

SubElement(
    channel,
    "description",
).text = (
    "奈良県中小企業団体中央会、"
    "全国中央会・会員組合等、"
    "国・県・関係機関等からのお知らせ"
)

for entry in deduped:
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
        f"urn:chuokai-nara:{unique_id}"
    )

ElementTree(rss).write(
    OUTPUT_FILE,
    encoding="utf-8",
    xml_declaration=True,
)

print(
    OUTPUT_FILE,
    len(deduped),
)
