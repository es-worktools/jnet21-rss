import re
import json
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from xml.etree.ElementTree import Element, SubElement, ElementTree

SOURCE_URL = 'https://www.town.yakushima.kagoshima.jp/'
DATA_URL = 'https://www.town.yakushima.kagoshima.jp/index.update.json'
OUTPUT_FILE = 'municipality-1863-yakushima.xml'
CHANNEL_TITLE = '1863_【GH】鹿児島県屋久島町 新着情報'
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
    return fetch_url(DATA_URL)

def parse(raw):
    records = {}
    data = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(data, list):
        raise RuntimeError("Official news JSON structure changed")
    now = datetime.now(JST)
    for article in data:
        if article.get("is_keitai_page"):
            continue
        published = datetime.fromisoformat(article["publish_datetime"])
        if published.tzinfo is None:
            raise RuntimeError("Official publish timezone missing")
        published = published.astimezone(JST)
        if published < now - timedelta(days=90) or published > now:
            continue
        title = re.sub(r"\s+", " ", article["page_name"]).strip()
        url = urljoin(SOURCE_URL, article["url"])
        if not title or urlparse(url).scheme not in ("https", "http") or not urlparse(url).netloc:
            raise RuntimeError("Invalid official article")
        if url not in records or published > records[url][0]:
            records[url] = (published, title, url)
    if not records:
        raise RuntimeError("No dated official articles; existing RSS preserved")
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
