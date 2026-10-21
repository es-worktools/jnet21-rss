import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from xml.etree.ElementTree import Element, SubElement, ElementTree
from lxml import html

SOURCE_URL = 'https://official.shinkamigoto.net/newslist.php?bn=2'
OUTPUT_FILE = 'municipality-1737-shinkamigoto.xml'
CHANNEL_TITLE = '1737_長崎県新上五島町'
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
    rows = doc.xpath('//li[contains(concat(" ",normalize-space(@class)," ")," tablist_noimage ")]')
    for row in rows:
        dates = row.xpath('.//div[contains(concat(" ",normalize-space(@class)," ")," tab_sub ")]')
        links = row.xpath('./div[contains(concat(" ",normalize-space(@class)," ")," tab_title ")]/h2/a[@href]')
        if len(dates) != 1 or len(links) != 1:
            raise RuntimeError("Official news row structure changed")
        stamp = re.sub(r"\s+", "", dates[0].text_content())
        match = re.match(r"(令和(?:元|\d+)|\d{4})年(\d{1,2})月(\d{1,2})日", stamp)
        if not match:
            raise RuntimeError("Unexpected official date: " + stamp)
        year, month, day = match.groups()
        year = 2019 if year == "令和元" else 2018 + int(year[2:]) if year.startswith("令和") else int(year)
        published = datetime(year, int(month), int(day), tzinfo=JST)
        if published > datetime.now(JST):
            continue
        title = re.sub(r"\s+", " ", links[0].text_content()).strip()
        url = urljoin(SOURCE_URL, links[0].get("href"))
        if not title or urlparse(url).netloc != "official.shinkamigoto.net" or urlparse(url).scheme != "https":
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
