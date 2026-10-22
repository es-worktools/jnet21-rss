import re
import json
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from xml.etree.ElementTree import Element, SubElement, ElementTree
from lxml import html

SOURCE_URL = 'https://www.city.minamisatsuma.lg.jp/top-news.html'
OUTPUT_FILE = 'municipality-1845-minamisatsuma.xml'
CHANNEL_TITLE = '1845_鹿児島県南さつま市'
JST = timezone(timedelta(hours=9))
MAX_ITEMS = 30
ROW_XPATH = '//ul[contains(concat(" ", normalize-space(@class), " "), " list-news ")]/li[.//time]'
LINK_XPATH = './/span[contains(concat(" ", normalize-space(@class), " "), " news-title ")]/a[@href]'
DATE_XPATH = './/time/@datetime'
DATE_FORMAT = "%Y-%m-%d"

def fetch_url(url):
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=40) as response:
                if urlparse(response.url).netloc != urlparse(SOURCE_URL).netloc:
                    raise RuntimeError("Unexpected source redirect")
                return response.read()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)

def fetch():
    return fetch_url(SOURCE_URL)

def parse(raw):
    tree = html.fromstring(raw)
    rows = tree.xpath(ROW_XPATH)
    records = {}
    for row in rows:
        anchors = row.xpath(LINK_XPATH)
        dates = row.xpath(DATE_XPATH)
        if len(anchors) != 1 or len(dates) != 1:
            raise RuntimeError("Official news row structure changed")
        anchor = anchors[0]
        title = re.sub(r"\s+", " ", anchor.text_content()).strip()
        url = urljoin(SOURCE_URL, anchor.get("href", ""))
        date_text = str(dates[0]).strip()
        published = datetime.strptime(date_text, DATE_FORMAT).replace(tzinfo=JST)
        if not title or urlparse(url).netloc != urlparse(SOURCE_URL).netloc or urlparse(url).scheme not in ("http", "https"):
            raise RuntimeError("Invalid official news article")
        if url not in records:
            records[url] = (published, title, url)
    if not records:
        raise RuntimeError("No official news articles; existing RSS preserved")
    return sorted(records.values(), key=lambda row: row[0], reverse=True)[:MAX_ITEMS]

def main():
    records = parse(fetch())
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = CHANNEL_TITLE
    SubElement(channel, "link").text = SOURCE_URL
    SubElement(channel, "description").text = CHANNEL_TITLE + " 公式新着情報（GitHub生成RSS）"
    for published, title, url in records:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = title
        SubElement(item, "link").text = url
        SubElement(item, "guid", isPermaLink="true").text = url
        SubElement(item, "pubDate").text = format_datetime(published)
    tmp = Path(OUTPUT_FILE + ".tmp")
    ElementTree(rss).write(tmp, encoding="utf-8", xml_declaration=True)
    tmp.replace(OUTPUT_FILE)
    print(f"{OUTPUT_FILE}: {len(records)} articles")

if __name__ == "__main__":
    main()
