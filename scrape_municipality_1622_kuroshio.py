import json, re, time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from urllib.request import Request, build_opener, HTTPCookieProcessor
from http.cookiejar import CookieJar
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree
from pathlib import Path
from lxml import html

SOURCE_URL = 'https://www.town.kuroshio.lg.jp/pb/cont/yakuba/1346'
DATA_URL = 'https://www.town.kuroshio.lg.jp/pb/cont/yakuba/1346'
OUTPUT_FILE = 'municipality-1622-kuroshio.xml'
CHANNEL_TITLE = '1622_高知県黒潮町'
ALLOWED_DOMAIN = urlparse(SOURCE_URL).netloc
MAX_ITEMS = 30
JST = timezone(timedelta(hours=9))
OPENER = build_opener(HTTPCookieProcessor(CookieJar()))

def normalize(text):
    return re.sub(r"\s+", " ", (text or "").replace("\u00ad", "")).strip()

def fetch(url):
    for attempt in range(4):
        try:
            request = Request(url, headers={"User-Agent":"Mozilla/5.0", "Accept":"application/json,text/html;q=0.9,*/*;q=0.8", "Referer":SOURCE_URL})
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
    doc = html.fromstring(text.encode('utf-8'),parser=html.HTMLParser(encoding='utf-8'))
    nodes = doc.xpath('//ul[@id="article_list"]/a[@href]')
    if not nodes: raise RuntimeError('Official news list missing')
    for node in nodes:
        title = one(node,'./li/h3').text_content()
        date_text = normalize(one(node,'./li/p[@class="day"]').text_content())
        match = re.fullmatch(r'(20\d{2})\.(\d{1,2})\.(\d{1,2})',date_text)
        if not match: raise RuntimeError('Official date missing: '+date_text)
        add(items,title,node.get('href'),datetime(*map(int,match.groups()),tzinfo=JST))


def main():
    if DATA_URL != SOURCE_URL: fetch(SOURCE_URL)
    items = {}
    parse_source(fetch(DATA_URL), items)
    if not items: raise RuntimeError("No articles found; existing RSS preserved")
    # Preserve the official list order, including entries with no usable date.
    rows = sorted(items.values(), key=lambda r:r[0], reverse=True)[:MAX_ITEMS]
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
