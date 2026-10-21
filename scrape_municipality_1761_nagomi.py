import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from xml.etree.ElementTree import Element, SubElement, ElementTree
from lxml import html

SOURCE_URL = 'https://www.town.nagomi.lg.jp/news/'
OUTPUT_FILE = 'municipality-1761-nagomi.xml'
CHANNEL_TITLE = '1761_熊本県和水町'
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
    doc = html.fromstring(raw.decode("utf-8-sig"))
    records = {}
    for link in doc.xpath('//main//div[@class="s-info-list"]/ul/li/a[@href]'):
        dates = link.xpath('./div[@class="date"]')
        titles = link.xpath('./div[@class="title"]/p')
        if len(dates) != 1 or len(titles) != 1:
            raise RuntimeError("Official news row changed")
        stamp = (dates[0].text or "").strip()
        match = re.fullmatch(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", stamp)
        if not match:
            raise RuntimeError("Unexpected official date: " + stamp)
        published = datetime(*map(int, match.groups()), tzinfo=JST)
        if published > datetime.now(JST):
            continue
        title = re.sub(r"\s+", " ", titles[0].text_content()).strip()
        url = urljoin(SOURCE_URL, link.get("href"))
        if not title or urlparse(url).scheme not in ("https", "http") or not urlparse(url).netloc:
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
