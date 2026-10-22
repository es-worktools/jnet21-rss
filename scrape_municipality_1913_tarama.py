import re
import json
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from xml.etree.ElementTree import Element, SubElement, ElementTree

SOURCE_URL = 'https://www.vill.tarama.okinawa.jp/news/'
OUTPUT_FILE = 'municipality-1913-tarama.xml'
CHANNEL_TITLE = '1913_【GH】沖縄県多良間村 新着情報'
JST = timezone(timedelta(hours=9))
MAX_ITEMS = 30
YEARS_URL = "https://www.vill.tarama.okinawa.jp/common/json/news-years.json"
DATA_URL_TEMPLATE = "https://www.vill.tarama.okinawa.jp/common/json/news-{year}.json"

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
    years = json.loads(fetch_url(YEARS_URL).decode("utf-8-sig"))
    if not isinstance(years, list) or not years or not all(re.fullmatch(r"[0-9]{4}", str(year)) for year in years):
        raise RuntimeError("Official year list changed")
    latest_year = max(int(year) for year in years)
    return fetch_url(DATA_URL_TEMPLATE.format(year=latest_year))

def parse(raw):
    data = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(data, list) or not data:
        raise RuntimeError("No official articles; existing RSS preserved")
    records = {}
    for article in data:
        title = re.sub(r"\s+", " ", article["title"]).strip()
        url = urljoin(SOURCE_URL, article["permalink"])
        published = datetime.strptime(article["date"], "%Y年%m月%d日").replace(tzinfo=JST)
        if not title or urlparse(url).netloc != urlparse(SOURCE_URL).netloc or urlparse(url).scheme not in ("https", "http"):
            raise RuntimeError("Invalid official article")
        if url not in records or published > records[url][0]:
            records[url] = (published, title, url)
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
