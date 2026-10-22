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

SOURCE_URL = 'https://www.city.tokyo-nakano.lg.jp/allNewsList.html'
OUTPUT_FILE = 'municipality-1929-nakano.xml'
CHANNEL_TITLE = '1929_【GH】東京都中野区 新着情報'
JST = timezone(timedelta(hours=9))
MAX_ITEMS = 30

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
    tree = html.fromstring(raw.decode("utf-8-sig"))
    rows = tree.xpath('//div[contains(concat(" ", normalize-space(@class), " "), " allNewsList-wp ")]//ul[contains(concat(" ", normalize-space(@class), " "), " info-list ")]/li')
    records = {}
    for row in rows:
        dates = row.xpath('./span[contains(concat(" ", normalize-space(@class), " "), " date ")]')
        anchors = row.xpath('./span/a[@href]')
        if len(dates) != 1 or len(anchors) != 1:
            raise RuntimeError("Official news row structure changed")
        match = re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})日", dates[0].text_content().strip())
        if not match:
            raise RuntimeError("Official news date missing")
        published = datetime(*map(int, match.groups()), tzinfo=JST)
        title = re.sub(r"\s+", " ", anchors[0].text_content()).strip()
        url = urljoin(SOURCE_URL, anchors[0].get("href"))
        if not title or urlparse(url).scheme not in ("https", "http") or urlparse(url).netloc != urlparse(SOURCE_URL).netloc:
            raise RuntimeError("Invalid official article")
        if url not in records or published > records[url][0]:
            records[url] = (published, title, url)
    if not records:
        raise RuntimeError("No dated official articles; existing RSS preserved")
    return sorted(records.values(), key=lambda item: item[0], reverse=True)[:MAX_ITEMS]

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
