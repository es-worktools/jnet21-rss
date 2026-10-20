import json, re, time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from urllib.request import Request, build_opener, HTTPCookieProcessor
from http.cookiejar import CookieJar
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree
from pathlib import Path
from lxml import html

SOURCE_URL = 'https://www.vill.hidaka.kochi.jp/kurashi/'
DATA_URL = 'https://www.vill.hidaka.kochi.jp/kurashi/view_new_info.cgi?SITE_ID=1&TYPE=0'
OUTPUT_FILE = 'municipality-1617-hidaka.xml'
CHANNEL_TITLE = '1617_高知県日高村'
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
    nodes = doc.xpath('//ul[@class="newinfo"]/li')
    if not nodes: raise RuntimeError('Official new-info data missing')
    archive = html.fromstring(fetch(urljoin(SOURCE_URL,'backnumber.cgi')).encode('utf-8'))
    for node in nodes:
        a = one(node,'./a[@href]')
        title = one(a,'./span[@class="new_info_title"]').text_content()
        date_text = one(node,'./span[@class="new_info_date"]').text
        match = re.fullmatch(r'(20\d{2})/(\d{1,2})/(\d{1,2})',normalize(date_text))
        if not match: raise RuntimeError('Official publication date missing')
        url = urljoin(SOURCE_URL,a.get('href'))
        identifier = urlparse(url).fragment
        if not re.fullmatch(r'info_id\d+',identifier): raise RuntimeError('Official article anchor missing')
        entry = one(archive,'//li[@id="'+identifier+'"]')
        if normalize(one(entry,'./dl/dt/h2').text_content()) != normalize(title): raise RuntimeError('Archive title mismatch')
        archive_date = one(entry,'./dl/dt/span[@class="publication_date"]').text
        if normalize(archive_date) != normalize(date_text).replace('/','.'): raise RuntimeError('Archive date mismatch')
        description = normalize(one(entry,'./dl/dd').text_content())
        add(items,title,url,datetime(*map(int,match.groups()),tzinfo=JST),description)


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
