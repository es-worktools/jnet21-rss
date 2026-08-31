import hashlib
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree

SOURCE_URL = "https://www.gpc-gifu.or.jp/topics/topics.asp"
OUTPUT_FILE = "gifu-sangyo.xml"
MAX_ITEMS = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
}

response = requests.get(
    SOURCE_URL,
    headers=HEADERS,
    timeout=60,
)

response.raise_for_status()
response.encoding = response.apparent_encoding

soup = BeautifulSoup(response.text, "html.parser")

items = []
seen_urls = set()

for a in soup.find_all("a", href=True):
    title = a.get_text(" ", strip=True)
    title = re.sub(r"\s+", " ", title).strip()

    if not title:
        continue

    href = a.get("href", "").strip()

    if not href:
        continue

    if href.startswith("#"):
        continue

    if href.startswith("javascript:"):
        continue

    url = urljoin(SOURCE_URL, href)
    parsed = urlparse(url)

    if parsed.netloc not in {
        "www.gpc-gifu.or.jp",
        "gpc-gifu.or.jp",
    }:
        continue

    # 一覧・ナビゲーション等を除外
    if parsed.path.endswith("/topics/topics.asp"):
        continue

    if parsed.path.endswith("/topics/back_number.asp"):
        continue

    if title in {
        "ホーム",
        "お問い合わせ",
        "アクセス",
        "サイトマップ",
        "メールマガジン",
        "トピックス",
        "一覧",
    }:
        continue

    if len(title) < 8:
        continue

    # トピックス詳細ページを優先
    if "/topics/" not in parsed.path:
        continue

    if url in seen_urls:
        continue

    seen_urls.add(url)
    items.append((title, url))

if not items:
    raise RuntimeError(
        "RSS対象を1件も取得できませんでした"
    )

rss = Element("rss", version="2.0")
channel = SubElement(rss, "channel")

SubElement(
    channel,
    "title",
).text = "岐阜県産業経済振興センター トピックス"

SubElement(
    channel,
    "link",
).text = SOURCE_URL

SubElement(
    channel,
    "description",
).text = "岐阜県産業経済振興センターのトピックス情報"

for title, url in items[:MAX_ITEMS]:
    item = SubElement(channel, "item")

    SubElement(
        item,
        "title",
    ).text = title

    SubElement(
        item,
        "link",
    ).text = url

    unique_id = hashlib.sha256(
        f"{title}|{url}".encode("utf-8")
    ).hexdigest()

    SubElement(
        item,
        "guid",
    ).text = f"urn:gifu-sangyo:{unique_id}"

ElementTree(rss).write(
    OUTPUT_FILE,
    encoding="utf-8",
    xml_declaration=True,
)

print(
    OUTPUT_FILE,
    len(items[:MAX_ITEMS]),
)
