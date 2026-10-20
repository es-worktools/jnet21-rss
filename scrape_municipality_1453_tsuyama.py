import json, re, time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from urllib.request import Request, build_opener, HTTPCookieProcessor
from http.cookiejar import CookieJar
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree
from pathlib import Path
from lxml import html

SOURCE_URL = 'https://www.city.tsuyama.lg.jp/'
DATA_URL = 'https://www.city.tsuyama.lg.jp/prd/tym/portal/openapi/v1/article/pattern/retrieve'
OUTPUT_FILE = 'municipality-1453-tsuyama.xml'
CHANNEL_TITLE = '1453_岡山県津山市'
ALLOWED_DOMAIN = urlparse(SOURCE_URL).netloc
MAX_ITEMS = 30
JST = timezone(timedelta(hours=9))
OPENER = build_opener(HTTPCookieProcessor(CookieJar()))

def normalize(text):
    return re.sub(r"\s+", " ", (text or "").replace("\u00ad", "")).strip()

def fetch(url, retrieval_count=0):
    for attempt in range(4):
        try:
            payload = {"tenantId":"10", "siteId":"1001", "langCode":"JPN", "pageId":"PTARS51", "retrievalCount":retrieval_count, "bulkFlg":False, "articleListContentsType":"latest", "originPageId":"PTHMS59", "tabType":"all"}
            request = Request(url, data=json.dumps(payload).encode("utf-8"), headers={"User-Agent":"Mozilla/5.0", "Content-Type":"application/json", "Accept":"application/json,text/html;q=0.9,*/*;q=0.8", "Referer":SOURCE_URL})
            with OPENER.open(request, timeout=60) as response:
                if urlparse(response.url).netloc != ALLOWED_DOMAIN:
                    raise RuntimeError("Unexpected redirect domain")
                return response.read().decode("utf-8-sig")
        except Exception:
            if attempt == 3: raise
            time.sleep(2 ** attempt)

def one(node, xpath):
    nodes = node.xpath(xpath)
    if len(nodes) != 1: raise RuntimeError("Official news structure changed: " + xpath)
    return nodes[0]

def official_date(text):
    match = re.fullmatch(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日", normalize(text))
    if not match: raise RuntimeError("Official date missing: " + text)
    return datetime(*map(int, match.groups()), tzinfo=JST)

def add(items, title, href, date, description=""):
    title = normalize(title)
    if not title or not href: raise RuntimeError("Missing article title or URL")
    url = urljoin(SOURCE_URL, href)
    if urlparse(url).scheme not in {"http","https"} or urlparse(url).netloc != ALLOWED_DOMAIN:
        raise RuntimeError("Unexpected article URL: " + url)
    if date is not None and (date.tzinfo is None or date > datetime.now(JST)):
        raise RuntimeError("Invalid publication date")
    if url not in items: items[url] = (date, title, url, description)

def parse_source(text, items):
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("data"), dict):
        raise RuntimeError("Official public news response changed")
    rows = data["data"].get("articleList")
    if not isinstance(rows, list): raise RuntimeError("Official article list missing")
    for row in rows:
        article_id = row.get("articleId", "")
        if not re.fullmatch(r"[0-9a-f]{24}", article_id) or row.get("articleTransitionUrl") != "/article":
            raise RuntimeError("Unexpected article route or ID")
        value = row.get("publishStartDateTime", "")
        if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", value):
            raise RuntimeError("Official publication time missing")
        day = datetime.fromisoformat(value).replace(tzinfo=JST)
        add(items, row.get("title"), "/article?articleId=" + article_id, day)
    return data["data"].get("hasMore") is True


def main():
    items = {}
    for page in range(3):
        if not parse_source(fetch(DATA_URL, page), items): break
    if not items: raise RuntimeError("No articles found; existing RSS preserved")
    # Preserve the official list order, including entries with no usable date.
    rows = list(items.values())[:MAX_ITEMS]
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = CHANNEL_TITLE
    SubElement(channel, "link").text = SOURCE_URL
    SubElement(channel, "description").text = CHANNEL_TITLE + " GitHub generated RSS"
    for date, title, url, description in rows:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = title
        SubElement(item, "link").text = url
        SubElement(item, "guid", isPermaLink="true").text = url
        if date is not None: SubElement(item, "pubDate").text = format_datetime(date)
        if description: SubElement(item, "description").text = description
    temp = Path(OUTPUT_FILE + ".tmp")
    ElementTree(rss).write(temp, encoding="utf-8", xml_declaration=True)
    temp.replace(OUTPUT_FILE)
    print(OUTPUT_FILE, len(rows))

if __name__ == "__main__": main()
