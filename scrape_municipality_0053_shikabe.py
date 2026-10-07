from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

SOURCE_URL = "https://www.town.shikabe.lg.jp/shigoto_sangyo/index.html"
# This URL is explicitly loaded by the source page's newPageDynList1 script.
DATA_URL = "https://www.town.shikabe.lg.jp/shigoto_sangyo/index.update.json"
OUTPUT_FILE = "municipality-0053-shikabe-news.xml"
CHANNEL_TITLE = "0053_北海道鹿部町"
ALLOWED_DOMAIN = "www.town.shikabe.lg.jp"
MAX_ITEMS = 30
# The official new-information section displays articles from the last 30 days.
NEWS_DAYS = 30
JST = timezone(timedelta(hours=9))


def parse_items(records, now):
    if not isinstance(records, list):
        raise RuntimeError("Official new-information JSON must be an array")
    cutoff = now - timedelta(days=NEWS_DAYS)
    seen = {}
    for record in records:
        if not isinstance(record, dict):
            raise RuntimeError("Invalid new-information record")
        if record.get("is_category_index") or record.get("is_keitai_page"):
            continue
        if not all(key in record for key in ("page_name", "url", "publish_datetime")):
            raise RuntimeError("Official new-information JSON schema changed")
        title = " ".join(record["page_name"].split())
        url = record["url"]
        date = datetime.fromisoformat(record["publish_datetime"])
        if date.tzinfo is None or not title:
            raise RuntimeError("Article title or publication timezone missing")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or parsed.netloc != ALLOWED_DOMAIN:
            raise RuntimeError("Unexpected new-information article URL")
        if date < cutoff or date > now:
            continue
        if url not in seen or seen[url][0] < date:
            seen[url] = (date, title, url)
    return sorted(seen.values(), key=lambda item: item[0], reverse=True)[:MAX_ITEMS]


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    retry = Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    response = session.get(DATA_URL, timeout=60)
    response.raise_for_status()
    if urlparse(response.url).netloc != ALLOWED_DOMAIN:
        raise RuntimeError("Unexpected redirect domain")
    records = response.json()
    items = parse_items(records, datetime.now(JST))

    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = CHANNEL_TITLE
    SubElement(channel, "link").text = SOURCE_URL
    SubElement(channel, "description").text = CHANNEL_TITLE + " しごと・産業 新着情報 GitHub generated RSS"
    for date, title, url in items:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = title
        SubElement(item, "link").text = url
        SubElement(item, "guid", isPermaLink="true").text = url
        SubElement(item, "pubDate").text = format_datetime(date)
    # Preserve the previous feed if fetching or validating the JSON fails.
    temp = Path(OUTPUT_FILE + ".tmp")
    ElementTree(rss).write(temp, encoding="utf-8", xml_declaration=True)
    temp.replace(OUTPUT_FILE)
    print(OUTPUT_FILE, len(items))


if __name__ == "__main__":
    main()
