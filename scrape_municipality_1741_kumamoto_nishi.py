import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from xml.etree.ElementTree import Element, SubElement, ElementTree
from lxml import html

SOURCE_URL = 'https://www.city.kumamoto.jp/nishi/new_list.html'
OUTPUT_FILE = 'municipality-1741-kumamoto-nishi.xml'
CHANNEL_TITLE = '1741_熊本県西区'
JST = timezone(timedelta(hours=9))
MAX_ITEMS = 30

def fetch():
    for attempt in range(3):
        try:
            with urlopen(Request(SOURCE_URL, headers={"User-Agent": "Mozilla/5.0"}), timeout=40) as response:
                if urlparse(response.url).netloc != urlparse(SOURCE_URL).netloc:
                    raise RuntimeError("Unexpected source redirect")
                return response.read()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)

def parse(raw):
    doc = html.fromstring(raw)
    records = {}
    blocks = doc.xpath('//*[@id="list-time"]')
    if len(blocks) != 1:
        raise RuntimeError("Official chronological news block changed")
    for heading in blocks[0].xpath('.//dt[h2]'):
        stamp = re.sub(r"\s+", "", heading.text_content())
        match = re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})日", stamp)
        if not match:
            raise RuntimeError("Unexpected official date: " + stamp)
        published = datetime(*map(int, match.groups()), tzinfo=JST)
        if published > datetime.now(JST):
            continue
        sibling = heading.getnext()
        if sibling is None or sibling.tag != "dd":
            raise RuntimeError("Official date/article grouping changed")
        links = sibling.xpath('.//article//a[@href][span[contains(concat(" ", normalize-space(@class), " "), " textLink ")]]')
        if not links:
            raise RuntimeError("Official article links missing")
        for link in links:
            title = re.sub(r"\s+", " ", link.text_content()).strip()
            url = urljoin(SOURCE_URL, link.get("href"))
            if not title or urlparse(url).netloc != "www.city.kumamoto.jp" or urlparse(url).scheme not in ("https", "http"):
                raise RuntimeError("Invalid official article")
            records[url] = (published, title, url)
    if not records:
        raise RuntimeError("No dated official articles; existing RSS preserved")
    return sorted(records.values(), reverse=True)[:MAX_ITEMS]

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
