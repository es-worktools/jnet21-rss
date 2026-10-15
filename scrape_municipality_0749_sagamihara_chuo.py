from hashlib import sha256
WARD_NAME='中央区'
import json, re, time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree
from pathlib import Path
from lxml import html

SOURCES = ['https://www.city.sagamihara.kanagawa.jp/chuoku/']
SOURCE_URL = SOURCES[0]
OUTPUT_FILE = 'municipality-0749-sagamihara-chuo.xml'
CHANNEL_TITLE = '0749_神奈川県中央区'
ALLOWED_DOMAIN = urlparse(SOURCE_URL).netloc
MAX_ITEMS = 30
JST = timezone(timedelta(hours=9))

ALLOWED_ARTICLE_DOMAINS = {ALLOWED_DOMAIN}

def normalize(text):
    return re.sub(r"\s+", " ", (text or "").replace("\u00ad", "")).strip()

def fetch(url):
    for attempt in range(4):
        try:
            with urlopen(Request(url, headers={"User-Agent":"Mozilla/5.0"}), timeout=60) as response:
                if urlparse(response.url).netloc != ALLOWED_DOMAIN:
                    raise RuntimeError("Unexpected redirect domain")
                return response.read().decode("utf-8")
        except Exception:
            if attempt == 3: raise
            time.sleep(2 ** attempt)

def official_date(text):
    text = normalize(text)
    jp = re.search(r"(令和|平成)?(元|\d{1,4})年\s*(\d{1,2})月\s*(\d{1,2})日", text)
    numeric = re.fullmatch(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", text)
    if jp:
        era,y,m,d = jp.groups()
        y = 1 if y == "元" else int(y)
        y += {"令和":2018,"平成":1988,None:0}[era]
        return datetime(y,int(m),int(d),tzinfo=JST)
    if numeric: return datetime(*map(int,numeric.groups()),tzinfo=JST)
    raise RuntimeError("Official article date not found")

def add(items, title, href, date, source_url):
    title = normalize(title)
    url = urljoin(source_url,href)
    if not title or not href: raise RuntimeError("Missing article title or URL")
    if urlparse(url).scheme not in {"http","https"} or urlparse(url).netloc not in ALLOWED_ARTICLE_DOMAINS:
        raise RuntimeError("Unexpected article URL")
    if date.date() > datetime.now(JST).date(): return
    if url not in items or items[url][0] < date: items[url] = (date,title,url)

def one(node, xpath):
    found = node.xpath(xpath)
    if len(found)!=1: raise RuntimeError("Official news structure changed")
    return found[0]

def parse_source(text,source_url,items):
    tree=html.fromstring(re.sub(r"^\s*<\?xml[^>]*\?>", "", text))
    blocks=tree.xpath('//div[contains(concat(" ",normalize-space(@class)," ")," wardtopics ")]')
    if len(blocks)!=1: raise RuntimeError("Official ward announcements block missing")
    heading=one(blocks[0],'./h2').text_content()
    if WARD_NAME+"からのお知らせ" not in heading: raise RuntimeError("Unexpected ward")
    nodes=blocks[0].xpath('.//ul/li/a[@href]')
    if not nodes: raise RuntimeError("Official ward announcements empty")
    for node in nodes:
        title=normalize(node.text_content())
        url=urljoin(source_url,node.get('href'))
        if not title or urlparse(url).netloc!=ALLOWED_DOMAIN: raise RuntimeError("Invalid ward announcement")
        # No year is supplied for these announcements. Retain official month/day
        # in the title and omit pubDate rather than infer a year.
        items[(title,url)]=(title,url)

def main():
    items={}
    for url in SOURCES: parse_source(fetch(url),url,items)
    if not items: raise RuntimeError("No ward announcements; existing RSS preserved")
    rss=Element("rss",version="2.0");channel=SubElement(rss,"channel")
    SubElement(channel,"title").text=CHANNEL_TITLE
    SubElement(channel,"link").text=SOURCE_URL
    SubElement(channel,"description").text="相模原市"+WARD_NAME+"からのお知らせ"
    for title,url in list(items.values())[:MAX_ITEMS]:
        item=SubElement(channel,"item")
        SubElement(item,"title").text=title
        SubElement(item,"link").text=url
        SubElement(item,"guid",isPermaLink="false").text=sha256((title+"\n"+url).encode("utf-8")).hexdigest()
    temp=Path(OUTPUT_FILE+".tmp");ElementTree(rss).write(temp,encoding="utf-8",xml_declaration=True);temp.replace(OUTPUT_FILE)
    print(OUTPUT_FILE,len(items))

if __name__ == "__main__": main()
