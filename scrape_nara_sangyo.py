import re
import hashlib
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree

SOURCE_URL = "https://www.nara-sangyoshinko.or.jp/news.html"
OUTPUT_FILE = "nara-sangyo.xml"
MAX_ITEMS = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

response = requests.get(
    SOURCE_URL,
    headers=HEADERS,
    timeout=60,
)
response.raise_for_status()

response.encoding = response.apparent_encoding
soup = BeautifulSoup(response.text, "html.parser")

content = soup.find("main")

if content is None:
    content = soup

items = []
seen_urls = set()

for a in content.find_all("a", href=True):
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

    # 奈良県地域産業振興センターサイト内だけ
    if parsed.netloc not in {
        "www.nara-sangyoshinko.or.jp",
        "nara-sangyoshinko.or.jp",
    }:
        continue

    # 一覧ページ自身を除外
    if parsed.path.endswith("/news.html"):
        continue

    # 固定ナビゲーション等を除外
    if title in {
        "ホーム",
        "財団について",
        "交通アクセス",
        "お問い合わせ",
        "お知らせ",
        "イベント＆セミナー開催",
        "出版物一覧",
        "サイトマップ",
    }:
        continue

    # URL単位で重複除去
    if url in seen_urls:
        continue

    # タイトルが短すぎるリンクは除外
    if len(title) < 8:
        continue

    seen_urls.add(url)
    items.append((title, url))

if not items:
    raise RuntimeError("RSS対象を1件も取得できませんでした")

rss = Element("rss", version="2.0")
channel = SubElement(rss, "channel")

SubElement(
    channel,
    "title"
).text = "奈良県地域産業振興センター お知らせ"

SubElement(
    channel,
    "link"
).text = SOURCE_URL

SubElement(
    channel,
    "description"
).text = "奈良県地域産業振興センターのお知らせ情報"

for title, url in items[:MAX_ITEMS]:
    item = SubElement(channel, "item")

    SubElement(
        item,
        "title"
    ).text = title

    SubElement(
        item,
        "link"
    ).text = url

    unique_id = hashlib.sha256(
        f"{title}|{url}".encode("utf-8")
    ).hexdigest()

    SubElement(
        item,
        "guid"
    ).text = f"urn:nara-sangyo:{unique_id}"

ElementTree(rss).write(
    OUTPUT_FILE,
    encoding="utf-8",
    xml_declaration=True,
)

print(
    OUTPUT_FILE,
    len(items[:MAX_ITEMS])
)
