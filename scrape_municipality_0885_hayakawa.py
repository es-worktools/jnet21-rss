import json, re, time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree
from pathlib import Path
from lxml import html

SOURCES = ['https://www.town.hayakawa.yamanashi.jp/']
SOURCE_URL = SOURCES[0]
OUTPUT_FILE = 'municipality-0885-hayakawa.xml'
CHANNEL_TITLE = '0885_山梨県早川町'
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

def lines(node):
    copy=html.fromstring(html.tostring(node,encoding='unicode'))
    for br in copy.xpath('.//br'):br.tail='\n'+(br.tail or '')
    return [normalize(x) for x in copy.text_content().splitlines() if normalize(x)]

def parse_source(text,source_url,items):
    rows=re.findall(r'<!--\s*WCVROW!リスト!(\d+)\s*-->(.*?)<!--\s*/WCVROW\s*-->',text,re.S)
    if not rows:raise RuntimeError("Official bulletin rows missing")
    for rowid,fragment in rows:
        doc=html.fragment_fromstring(fragment,create_parent='div')
        dt=one(doc,'.//dt');dd=one(doc,'.//dd');dtlines=lines(dt);ddlines=lines(dd)
        dated=bool(dtlines and re.fullmatch(r'\d{4}年\d{1,2}月\d{1,2}日',dtlines[0]))
        date=official_date(dtlines[0]) if dated else None
        if date and date.date()>datetime.now(JST).date():continue
        bold=doc.xpath('.//strong|.//b')
        title=lines(bold[0])[0] if bold and lines(bold[0]) else next(iter((dtlines[1:] if dated else dtlines)+ddlines),'')
        if not title:raise RuntimeError("Official bulletin title missing")
        links=[urljoin(source_url,a.get('href')) for a in doc.xpath('.//a[@href]')]
        links=[url for url in links if urlparse(url).netloc==ALLOWED_DOMAIN and urlparse(url).scheme in {'http','https'}]
        url=links[0] if links else source_url
        guid='urn:jnet21:municipality:0885:row:'+rowid
        if guid in items:raise RuntimeError("Duplicate official bulletin row ID")
        items[guid]=(date,title,url,guid,'\n'.join(dtlines+ddlines))

def main():
    items={}
    for url in SOURCES:parse_source(fetch(url),url,items)
    if not items:raise RuntimeError("No official bulletins; existing RSS preserved")
    rows=list(items.values())[:MAX_ITEMS]
    rss=Element('rss',version='2.0');channel=SubElement(rss,'channel')
    SubElement(channel,'title').text=CHANNEL_TITLE;SubElement(channel,'link').text=SOURCE_URL
    SubElement(channel,'description').text=CHANNEL_TITLE+' GitHub generated RSS'
    for date,title,url,guid,description in rows:
        item=SubElement(channel,'item');SubElement(item,'title').text=title
        SubElement(item,'link').text=url;SubElement(item,'guid',isPermaLink='false').text=guid
        if date:SubElement(item,'pubDate').text=format_datetime(date)
        SubElement(item,'description').text=description
    temp=Path(OUTPUT_FILE+'.tmp');ElementTree(rss).write(temp,encoding='utf-8',xml_declaration=True);temp.replace(OUTPUT_FILE)
    print(OUTPUT_FILE,len(rows))

if __name__=='__main__':main()
