import json, re, time, hashlib
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree
from pathlib import Path
from lxml import html

SOURCES = ['https://www.vill.takayama.gunma.jp/topics1/topics.cgi']
SOURCE_URL = SOURCES[0]
OUTPUT_FILE = 'municipality-0514-takayama.xml'
CHANNEL_TITLE = '0514_群馬県高山村'
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
                return response.read().decode("cp932")
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
    tree=html.fromstring(text)
    nodes=tree.xpath('//td[b[@style]]')
    if not nodes: raise RuntimeError("Official dated topics list not found")
    for node in nodes:
        title=normalize(one(node,'./b[@style]').text_content())
        match=re.search(r'(20\d{2}/\d{2}/\d{2})\s*$',normalize(node.text_content()))
        if not match or not title: raise RuntimeError("Official topic title/date missing")
        date=official_date(match.group(1))
        if date.date() > datetime.now(JST).date(): continue
        row=node.getparent(); body=row.getnext()
        if body is None or body.tag!='tr': raise RuntimeError("Official topic body missing")
        description=normalize(body.text_content())
        if not description: raise RuntimeError("Official topic body empty")
        # The official inline topics page has no individual article permalinks.
        # Retain its real URL and use an opaque GUID to distinguish each dated topic.
        guid='urn:sha256:'+hashlib.sha256((source_url+'|'+date.date().isoformat()+'|'+title).encode('utf-8')).hexdigest()
        if guid in items: raise RuntimeError("Duplicate official topic identity")
        items[guid]=(date,title,source_url,guid,description)

def main():
    items={}
    for url in SOURCES: parse_source(fetch(url),url,items)
    if not items: raise RuntimeError("No dated articles found; existing RSS preserved")
    rows=sorted(items.values(),key=lambda row:row[0],reverse=True)[:MAX_ITEMS]
    rss=Element("rss",version="2.0")
    channel=SubElement(rss,"channel")
    SubElement(channel,"title").text=CHANNEL_TITLE
    SubElement(channel,"link").text=SOURCE_URL
    SubElement(channel,"description").text=CHANNEL_TITLE+" GitHub generated RSS"
    for date,title,url,guid,description in rows:
        item=SubElement(channel,"item")
        SubElement(item,"title").text=title
        SubElement(item,"link").text=url
        SubElement(item,"guid",isPermaLink="false").text=guid
        SubElement(item,"description").text=description
        SubElement(item,"pubDate").text=format_datetime(date)
    temp=Path(OUTPUT_FILE+".tmp")
    ElementTree(rss).write(temp,encoding="utf-8",xml_declaration=True)
    temp.replace(OUTPUT_FILE)
    print(OUTPUT_FILE,len(rows))

if __name__ == "__main__": main()

