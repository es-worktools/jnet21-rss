import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from xml.etree.ElementTree import Element, SubElement, ElementTree
from lxml import html

SOURCE_URL = "https://www.city.takeo.lg.jp/information/" + str(datetime.now(timezone(timedelta(hours=9))).year) + "/"
OUTPUT_FILE = "municipality-1702-takeo.xml"
CHANNEL_TITLE = "1702_佐賀県武雄市"
JST = timezone(timedelta(hours=9))
MAX_ITEMS = 30

def fetch():
    for attempt in range(3):
        try:
            req = Request(SOURCE_URL, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=40) as response:
                if urlparse(response.url).netloc != urlparse(SOURCE_URL).netloc:
                    raise ValueError("Unexpected redirect domain")
                return response.read()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)

def main():
    doc = html.fromstring(fetch())
    links = doc.xpath('//li/a[contains(@href,".html")]')
    records = {}
    for a in links:
        href = a.get("href", "")
        if not re.fullmatch(r'\./\d{2}/\d+\.html', href):
            continue
        title = re.sub(r"\s+", " ", a.text_content()).strip()
        parent = a.getparent()
        date_text = re.sub(r"\s+", " ", parent.text_content())
        match = re.search(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日", date_text)
        if not match or not title:
            continue
        published = datetime(*(int(x) for x in match.groups()), tzinfo=JST)
        if published > datetime.now(JST):
            raise ValueError("Future official publication date")
        article_url = urljoin(SOURCE_URL, href)
        if urlparse(article_url).netloc != urlparse(SOURCE_URL).netloc:
            raise ValueError("Unexpected article domain")
        records[article_url] = (published, title, article_url)
    if len(records) < 3:
        raise RuntimeError("Not enough current articles; original RSS retained")
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = CHANNEL_TITLE
    SubElement(channel, "link").text = SOURCE_URL
    SubElement(channel, "description").text = "武雄市公式のお知らせ（GitHub RSS）"
    for date, title, url in sorted(records.values(), reverse=True)[:MAX_ITEMS]:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = title
        SubElement(item, "link").text = url
        SubElement(item, "guid", isPermaLink="true").text = url
        SubElement(item, "pubDate").text = format_datetime(date)
    temp = Path(OUTPUT_FILE + ".tmp")
    ElementTree(rss).write(temp, encoding="utf-8", xml_declaration=True)
    temp.replace(OUTPUT_FILE)
    print(f"{OUTPUT_FILE}: {len(records)} articles parsed")

if __name__ == "__main__":
    main()
