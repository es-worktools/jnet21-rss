import re
import hashlib
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree

SOURCE_URL = "https://yorozu-fukuoka.go.jp/planned-seminars/"
OUTPUT_FILE = "yorozu-fukuoka-seminar.xml"
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

# 対面セミナー本文部分を優先
content = soup.find("article")

if content is None:
    content = soup.find("main")

if content is None:
    content = soup

items = []
seen_urls = set()

exclude_titles = {
    "博多本部",
    "久留米よろず",
    "飯塚よろず",
    "北九州よろず",
    "県内各地の窓口",
}

for a in content.find_all("a", href=True):
    title = a.get_text(" ", strip=True)
    title = re.sub(r"\s+", " ", title).strip()

    if not title:
        continue

    if title in exclude_titles:
        continue

    # 「8月開催分はこちら」などの月移動リンクを除外
    if "開催分はこちら" in title:
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

    # 福岡県よろず支援拠点サイト内だけ
    if parsed.netloc != "yorozu-fukuoka.go.jp":
        continue

    # 一覧ページ自身は除外
    if parsed.path.rstrip("/") == "/planned-seminars":
        continue

    # セミナー詳細は基本的に /douga-ai のような
    # ルート直下の個別ページ
    path = parsed.path.rstrip("/")

    if not re.match(r"^/[^/]+$", path):
        continue

    # URL単位で重複除去
    if url in seen_urls:
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
).text = "福岡県よろず支援拠点 対面セミナー"

SubElement(
    channel,
    "link"
).text = SOURCE_URL

SubElement(
    channel,
    "description"
).text = "福岡県よろず支援拠点の対面セミナー情報"

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
    ).text = f"urn:yorozu-fukuoka-seminar:{unique_id}"

ElementTree(rss).write(
    OUTPUT_FILE,
    encoding="utf-8",
    xml_declaration=True,
)

print(
    OUTPUT_FILE,
    len(items[:MAX_ITEMS])
)
