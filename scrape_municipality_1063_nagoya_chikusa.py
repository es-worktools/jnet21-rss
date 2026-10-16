import json, re, time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree
from pathlib import Path
from lxml import html

SOURCES = ['https://www.city.nagoya.jp/chikusa/newslist.html']
SOURCE_URL = 'https://www.city.nagoya.jp/chikusa/newslist.html'
OUTPUT_FILE = 'municipality-1063-nagoya-chikusa.xml'
CHANNEL_TITLE = '1063_愛知県千種区'
ALLOWED_DOMAIN = urlparse(SOURCE_URL).netloc
MAX_ITEMS = 30
JST = timezone(timedelta(hours=9))

def normalize(text):
    return re.sub(r"\s+", " ", (text or "").replace("\u00ad", "")).strip()

def fetch(url):
    for attempt in range(4):
        try:
            with urlopen(Request(url, headers={"User-Agent":"Mozilla/5.0"}), timeout=60) as response:
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
    doc=html.fromstring(text.encode('utf-8'))
    container=one(doc,'//div[@id="voice"]')
    if normalize(one(container,'./h1').text_content())!='千種区 新着情報':raise RuntimeError("Unexpected ward news page")
    rows=container.xpath('./ul[@class="newslist"]/li')
    if not rows: raise RuntimeError("Official news currently empty; existing RSS preserved")
    for row in rows:
        date=official_date(one(row,'span[@class="date"]').text_content())
        a=one(row,'span[@class="newsli"]/a[@href]')
        add(items,a.text_content(),a.get('href'),date,source_url)

def main():
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
