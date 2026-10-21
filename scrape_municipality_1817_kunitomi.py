import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from xml.etree.ElementTree import Element, SubElement, ElementTree
from lxml import html

SOURCE_URL = 'https://www.town.kunitomi.miyazaki.jp/main/info/'
OUTPUT_FILE = 'municipality-1817-kunitomi.xml'
CHANNEL_TITLE = '1817_宮崎県国富町'
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
    wrapper = html.Element("div")
    url = SOURCE_URL
    seen = set()
    for page in range(1, 4):
        if url in seen:
            raise RuntimeError("Pagination loop")
        seen.add(url)
        doc = html.fromstring(fetch_url(url).decode("utf-8-sig"))
        for link in doc.xpath('//div[@class="newsList"]//a[@href]'):
            link.set("href", link.get("href").strip())
        if not doc.xpath('//div[@class="newsList"]/ul/li/dl'):
            raise RuntimeError("Official news page empty or changed")
        next_links = doc.xpath('//a[@href="index_' + str(page + 1) + '.html"]')
        wrapper.append(doc)
        if not next_links:
            break
        url = urljoin(url, next_links[0].get("href"))
        if urlparse(url).netloc != urlparse(SOURCE_URL).netloc:
            raise RuntimeError("Unexpected pagination host")
    return html.tostring(wrapper, encoding="utf-8")

def parse(raw):
    doc = html.fromstring(raw.decode("utf-8-sig"))
    records = {}
    for row in doc.xpath('//div[@class="newsList"]/ul/li/dl'):
        dates = row.xpath('./dt[not(@class)]')
        links = row.xpath('./dd/a[@href]')
        if len(dates) != 1 or len(links) != 1:
            raise RuntimeError("Official news row changed")
        stamp = re.sub(r"\s+", "", dates[0].text_content())
        match = re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})日", stamp)
        if not match:
            raise RuntimeError("Unexpected official date: " + stamp)
        published = datetime(*map(int, match.groups()), tzinfo=JST)
        link = links[0]
        title = re.sub(r"\s+", " ", link.text_content()).strip()
        url = urljoin(SOURCE_URL, link.get("href").strip())
        if not title or urlparse(url).netloc != urlparse(SOURCE_URL).netloc or urlparse(url).scheme not in ("https", "http"):
            raise RuntimeError("Invalid official article")
        url = url.replace("http://www.town.kunitomi.miyazaki.jp/", "https://www.town.kunitomi.miyazaki.jp/", 1)
        if url not in records or published > records[url][0]:
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
