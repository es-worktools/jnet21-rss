import json, re, time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree
from pathlib import Path
from lxml import html

SOURCES = ['https://www.vill.nakasatsunai.hokkaido.jp/info/']
SOURCE_URL = SOURCES[0]
OUTPUT_FILE = 'municipality-0168-nakasatsunai.xml'
CHANNEL_TITLE = '0168_北海道中札内村'
KIND = 'nakasatsunai'
ALLOWED_DOMAIN = urlparse(SOURCE_URL).netloc
MAX_ITEMS = 30
JST = timezone(timedelta(hours=9))

def normalize(text):
    return re.sub(r"\s+", " ", text or "").strip()

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
    numeric = re.fullmatch(r"(20\d{2})[/-](\d{1,2})[/-](\d{1,2})", text)
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
    if urlparse(url).scheme not in {"http","https"} or urlparse(url).netloc != ALLOWED_DOMAIN:
        raise RuntimeError("Unexpected article URL")
    if date.date() > datetime.now(JST).date(): return
    if url not in items or items[url][0] < date: items[url] = (date,title,url)

def one(node, xpath):
    found = node.xpath(xpath)
    if len(found)!=1: raise RuntimeError("Official news structure changed")
    return found[0]

def parse_source(text, source_url, items):
    tree = html.fromstring(text)
    rows = []
    if KIND == "shimizu":
        nodes = tree.xpath('//li[div[@class="date"] and div[@class="title"]/a[@href]]')
        for n in nodes:
            a = one(n,'./div[@class="title"]/a[@href]')
            rows.append((a.text_content(),a.get('href'),official_date(one(n,'./div[@class="date"]').text_content())))
    elif KIND == "memuro":
        nodes = tree.xpath('//*[@id="news-list"]/dl[dt and dd/a[@href]]')
        for n in nodes:
            a = one(n,'./dd/a[@href]')
            rows.append((a.text_content(),a.get('href'),official_date(one(n,'./dt').text_content())))
    elif KIND in {"nakasatsunai","sarabetsu"}:
        nodes = tree.xpath('//a[@href][dl[dt and dd]]')
        for a in nodes:
            rows.append((one(a,'./dl/dd').text_content(),a.get('href'),official_date(one(a,'./dl/dt').text_content())))
    if not rows: raise RuntimeError("Official dated news list not found; existing RSS preserved")
    for title,href,date in rows: add(items,title,href,date,source_url)

def parse_json(text, items):
    data=json.loads(text)
    if not isinstance(data,list) or not data: raise RuntimeError("Unexpected official JSON schema")
    for record in data:
        keys={"page_name","url","publish_datetime","is_category_index","is_keitai_page"}
        if not isinstance(record,dict) or not keys.issubset(record): raise RuntimeError("Official JSON structure changed")
        if not isinstance(record['is_category_index'],bool) or not isinstance(record['is_keitai_page'],bool):
            raise RuntimeError("Unexpected official JSON flags")
        if record['is_category_index'] or record['is_keitai_page']: continue
        date=datetime.fromisoformat(record['publish_datetime'])
        if date.tzinfo is None: raise RuntimeError("Official date has no timezone")
        date=date.astimezone(JST)
        if date < datetime.now(JST)-timedelta(days=90): continue
        add(items,record['page_name'],record['url'],date,SOURCE_URL)

def main():
    items={}
    if KIND == "taiki": parse_json(fetch(SOURCES[1]),items)
    else:
        for url in SOURCES: parse_source(fetch(url),url,items)
    if not items: raise RuntimeError("No dated articles found; existing RSS preserved")
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
