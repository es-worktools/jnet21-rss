import json, re, time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from urllib.request import Request, build_opener, HTTPCookieProcessor
from http.cookiejar import CookieJar
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree
from pathlib import Path
from lxml import html

SOURCES = ['https://www.city.aichi-miyoshi.lg.jp/index.update.json']
SOURCE_URL = 'https://www.city.aichi-miyoshi.lg.jp/news.html'
OUTPUT_FILE = 'municipality-1113-aichi-miyoshi.xml'
CHANNEL_TITLE = '1113_愛知県みよし市'
ALLOWED_DOMAIN = urlparse(SOURCE_URL).netloc
MAX_ITEMS = 30
JST = timezone(timedelta(hours=9))
OPENER = build_opener(HTTPCookieProcessor(CookieJar()))

def normalize(text):
    return re.sub(r"\s+", " ", (text or "").replace("\u00ad", "")).strip()

def fetch(url):
    for attempt in range(4):
        try:
            with OPENER.open(Request(url, headers={"User-Agent":"Mozilla/5.0", "Accept":"application/json,text/html;q=0.9,*/*;q=0.8", "Referer":SOURCE_URL}), timeout=60) as response:
                if urlparse(response.url).netloc != ALLOWED_DOMAIN:
                    raise RuntimeError("Unexpected redirect domain")
                return response.read().decode("utf-8-sig")
        except Exception:
            if attempt == 3: raise
            time.sleep(2 ** attempt)

def official_date(text):
    text = normalize(text)
    jp = re.fullmatch(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日", text)
    numeric = re.fullmatch(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", text)
    match = jp or numeric
    if match: return datetime(*map(int, match.groups()), tzinfo=JST)
    raise RuntimeError("Official article date not found: " + text)

def add(items, title, href, date, source_url):
    title = normalize(title)
    if not title or not href: raise RuntimeError("Missing article title or URL")
    url = urljoin(source_url, href)
    if urlparse(url).scheme not in {"http","https"} or urlparse(url).netloc != ALLOWED_DOMAIN:
        raise RuntimeError("Unexpected article URL: " + url)
    if date.tzinfo is None: raise RuntimeError("Official timezone missing")
    if date > datetime.now(JST): return
    if url not in items or items[url][0] < date: items[url] = (date,title,url)

def one(node, xpath):
    found = node.xpath(xpath)
    if len(found) != 1: raise RuntimeError("Official news structure changed: " + xpath)
    return found[0]

def parse_source(text, source_url, items):
    data=json.loads(text)
    if not isinstance(data,list) or not data: raise RuntimeError("Official news JSON missing")
    cutoff=datetime.now(JST)-timedelta(days=90)
    for row in data:
        if row['is_category_index'] or row['is_keitai_page']: continue
        date=datetime.fromisoformat(row['publish_datetime'])
        if date.tzinfo is None: raise RuntimeError("Official timezone missing")
        if date < cutoff: continue
        date = date.astimezone(JST).replace(hour=0, minute=0, second=0, microsecond=0)
        add(items,row['page_name'],row['url'],date,source_url)

def main():
    # Establish the ordinary anonymous site session before its JSON request.
    fetch(SOURCE_URL)
    items={}
    for url in SOURCES: parse_source(fetch(url),url,items)
    if not items: raise RuntimeError("No articles found; existing RSS preserved")
    rows=sorted(items.values(),key=lambda row:row[0],reverse=True)[:MAX_ITEMS]
    rss=Element("rss",version="2.0")
    channel=SubElement(rss,"channel")
    SubElement(channel,"title").text=CHANNEL_TITLE
    SubElement(channel,"link").text=SOURCE_URL
    SubElement(channel,"description").text=CHANNEL_TITLE+" GitHub generated RSS"
    for date,title,url in rows:
        item=SubElement(channel,"item")
        SubElement(item,"title").text=title
        SubElement(item,"link").text=url
        SubElement(item,"guid",isPermaLink="true").text=url
        SubElement(item,"pubDate").text=format_datetime(date)
    temp=Path(OUTPUT_FILE+".tmp")
    ElementTree(rss).write(temp,encoding="utf-8",xml_declaration=True)
    temp.replace(OUTPUT_FILE)
    print(OUTPUT_FILE,len(rows))

if __name__ == "__main__": main()
