import json, re, time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from urllib.request import Request, build_opener, HTTPCookieProcessor
from http.cookiejar import CookieJar
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree
from pathlib import Path
from lxml import html

SOURCE_URL = 'https://www.city.kobe.lg.jp/a57337/shise/about/construction/soshiki/kita.html'
DATA_URL = 'https://www.city.kobe.lg.jp/a57337/shise/about/construction/soshiki/kita.html'
OUTPUT_FILE = 'municipality-1294-kobe-kita.xml'
CHANNEL_TITLE = '1294_兵庫県北区'
ALLOWED_DOMAIN = urlparse(SOURCE_URL).netloc
SOURCE_PAGES = [('https://www.city.kobe.lg.jp/a57337/shise/about/construction/soshiki/kita.html', '北区（北区役所） 新着情報一覧'), ('https://www.city.kobe.lg.jp/a57337/shise/about/construction/soshiki/hokushin.html', '北区（北神区役所） 新着情報一覧')]
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
    if url not in items or date > items[url][0]: items[url] = (date, title, url, description)

def parse_source(text, items, expected_title):
    doc = html.fromstring(text)
    if normalize(one(doc, "//h1").text_content()) != expected_title:
        raise RuntimeError("Official news page title changed")
    anchors = doc.xpath('//*[@id="tmp_contents"]/ul/li/a[@href]')
    if not anchors: raise RuntimeError("Official dated news list missing")
    for anchor in anchors:
        match = re.fullmatch(r"(.+?)（(20\d{2}年\d{1,2}月\d{1,2}日)）", normalize(anchor.text_content()))
        if not match: raise RuntimeError("Official news title/date format changed")
        date = official_date(match.group(2))
        add(items, match.group(1), anchor.get("href"), date)



def main():
    items = {}
    for page_url, page_title in SOURCE_PAGES:
        parse_source(fetch(page_url), items, page_title)
    if not items: raise RuntimeError("No articles found; existing RSS preserved")
    # Merge both official lists by update date, keeping the latest row for each URL.
    rows = sorted(items.values(), key=lambda row: row[0], reverse=True)[:MAX_ITEMS]
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = CHANNEL_TITLE
    SubElement(channel, "link").text = SOURCE_URL
    SubElement(channel, "description").text = CHANNEL_TITLE + " 北区役所・北神区役所の新着情報（公式サイトの更新情報）"
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
