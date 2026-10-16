import json, re, time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree
from pathlib import Path
from lxml import html

SOURCES = ['https://www.city.hamamatsu.shizuoka.jp/tn-shinko/ward/tenryuku/oshirase/index.html']
SOURCE_URL = 'https://www.city.hamamatsu.shizuoka.jp/tn-shinko/ward/tenryuku/oshirase/index.html'
OUTPUT_FILE = 'municipality-1028-hamamatsu-tenryu.xml'
CHANNEL_TITLE = '1028_静岡県天竜区'
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
    if date is not None: raise RuntimeError("Yearless official dates must not be inferred")
    if url not in items: items[url] = (date,title,url)

def one(node, xpath):
    found = node.xpath(xpath)
    if len(found) != 1: raise RuntimeError("Official news structure changed: " + xpath)
    return found[0]

def parse_source(text, source_url, items):
    doc=html.fromstring(text)
    container=one(doc,'//div[@id="tmp_contents"]')
    if normalize(one(container,'./h1').text_content()) != '天竜区からのお知らせ':
        raise RuntimeError("Unexpected official ward list")
    rows=container.xpath('./ul/li/a[@href]')
    if not rows: raise RuntimeError("Official current news links missing")
    for a in rows:
        title=normalize(a.text_content())
        if not re.search(r"（\d{1,2}月\d{1,2}日）$",title):
            raise RuntimeError("Official month/day missing")
        add(items,title,a.get('href'),None,source_url)

def main():
    items={}
    for url in SOURCES: parse_source(fetch(url),url,items)
    if not items: raise RuntimeError("No articles found; existing RSS preserved")
    rows=list(items.values())[:MAX_ITEMS]
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
        SubElement(item,"description").text="公式一覧の月日のみをタイトルに保持。年の明記がないためpubDateは省略。"
    temp=Path(OUTPUT_FILE+".tmp")
    ElementTree(rss).write(temp,encoding="utf-8",xml_declaration=True)
    temp.replace(OUTPUT_FILE)
    print(OUTPUT_FILE,len(rows))

if __name__ == "__main__": main()
