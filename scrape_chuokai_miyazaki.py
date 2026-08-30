import re
import hashlib
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree

SOURCE_URL = "https://himuka.or.jp/news/"
OUTPUT_FILE = "chuokai-miyazaki.xml"
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

date_pattern = re.compile(
    r"20\d{2}年\d{1,2}月\d{1,2}日"
)

# このサイトでは、お知らせタイトルがh1で掲載されている
for heading in content.find_all("h1"):
    a = heading.find("a", href=True)

    if a is None:
        continue

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

    # 宮崎県中小企業団体中央会サイト内だけ
    if parsed.netloc not in {
        "himuka.or.jp",
        "www.himuka.or.jp",
    }:
        continue

    # お知らせ一覧自身は除外
    if parsed.path.rstrip("/") == "/news":
        continue

    # 周辺に掲載日があるものだけをお知らせ記事として採用
    block = heading
    found_date = False

    for _ in range(5):
        if block is None:
            break

        text = block.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()

        if date_pattern.search(text):
            found_date = True
            break

        block = block.parent

    if not found_date:
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
).text = "宮崎県中小企業団体中央会 お知らせ"

SubElement(
    channel,
    "link"
).text = SOURCE_URL

SubElement(
    channel,
    "description"
).text = "宮崎県中小企業団体中央会のお知らせ情報"

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
    ).text = f"urn:chuokai-miyazaki:{unique_id}"

ElementTree(rss).write(
    OUTPUT_FILE,
    encoding="utf-8",
    xml_declaration=True,
)

print(
    OUTPUT_FILE,
    len(items[:MAX_ITEMS])
)
