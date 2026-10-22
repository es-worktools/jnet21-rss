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

SOURCE_URL = 'https://vill.kitadaito.okinawa.jp/category/village/'
OUTPUT_FILE = 'municipality-1908-kitadaito.xml'
CHANNEL_TITLE = '1908_【GH】沖縄県北大東村 新着情報'
JST = timezone(timedelta(hours=9))
MAX_ITEMS = 30
SOURCE_URLS = ['https://vill.kitadaito.okinawa.jp/category/village/', 'https://vill.kitadaito.okinawa.jp/category/division/']
ROW_XPATH = '//a[contains(concat(" ", normalize-space(@class), " "), " doc_link ")]'
LINK_XPATH = '.'
TITLE_XPATH = './/span[@class="title"]'
DATE_XPATH = './/span[@class="update_date"]/text()'
DATE_FORMAT = '%Y.%m.%d'
ALLOW_EXTERNAL_LINKS = False


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
    if len(SOURCE_URLS) == 1:
        return fetch_url(SOURCE_URLS[0])
    return json.dumps([fetch_url(url).decode("utf-8-sig") for url in SOURCE_URLS], ensure_ascii=False).encode("utf-8")

def parse(raw):
    documents = json.loads(raw.decode("utf-8-sig")) if len(SOURCE_URLS) > 1 else [raw]
    records = {}
    for document in documents:
        tree = html.fromstring(document)
        rows = tree.xpath(ROW_XPATH)
        if not rows:
            raise RuntimeError("Official article list is empty; existing RSS preserved")
        for row in rows:
            anchors = row.xpath(LINK_XPATH)
            title_nodes = row.xpath(TITLE_XPATH)
            dates = row.xpath(DATE_XPATH)
            if len(anchors) != 1 or len(title_nodes) != 1 or len(dates) != 1:
                raise RuntimeError("Official article structure changed")
            title = re.sub(r"\s+", " ", title_nodes[0].text_content()).strip()
            url = urljoin(SOURCE_URL, anchors[0].get("href", ""))
            published = datetime.strptime(str(dates[0]).strip(), DATE_FORMAT).replace(tzinfo=JST)
            if not title or urlparse(url).scheme not in ("https", "http") or not urlparse(url).netloc:
                raise RuntimeError("Invalid official article")
            if not ALLOW_EXTERNAL_LINKS and urlparse(url).netloc != urlparse(SOURCE_URL).netloc:
                raise RuntimeError("Unexpected external article")
            if url not in records or published > records[url][0]:
                records[url] = (published, title, url)
    if not records:
        raise RuntimeError("No official articles; existing RSS preserved")
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
