import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from xml.etree.ElementTree import Element, SubElement, ElementTree
from lxml import html

SOURCE_URL = 'https://www.town.minamioguni.lg.jp/news/'
OUTPUT_FILE = 'municipality-1764-minamioguni.xml'
CHANNEL_TITLE = '1764_熊本県南小国町'
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
    for page in range(3):
        if url in seen:
            raise RuntimeError("Pagination loop")
        seen.add(url)
        doc = html.fromstring(fetch_url(url).decode("utf-8-sig"))

        next_links = doc.xpath('//a[normalize-space(text())="次のページ"]')
        wrapper.append(doc)
        if not next_links:
            break
        next_url = urljoin(url, next_links[0].get("href"))
        if urlparse(next_url).netloc != urlparse(SOURCE_URL).netloc:
            raise RuntimeError("Unexpected pagination host")
        url = next_url
    return html.tostring(wrapper, encoding="utf-8")

def parse(raw):
    doc = html.fromstring(raw.decode("utf-8-sig"))
    records = {}
    for heading in doc.xpath('//span[@class="news__title"]'):
        links = heading.xpath('./a[@href]')
        dates = heading.getparent().xpath('./span[@class="news__date"]')
        if len(links) != 1 or len(dates) != 1:
            raise RuntimeError("Official news row changed")
        link = links[0]
        stamp = dates[0].text_content().strip()
        match = re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})日", stamp)
        if not match:
            raise RuntimeError("Unexpected official date: " + stamp)
        published = datetime(*map(int, match.groups()), tzinfo=JST)
        if published > datetime.now(JST):
            continue
        title = re.sub(r"\s+", " ", link.text_content()).strip()
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
