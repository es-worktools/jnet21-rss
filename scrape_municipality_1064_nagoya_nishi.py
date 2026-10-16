import json, re, time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree
from pathlib import Path
from lxml import html

SOURCES = ['https://www.city.nagoya.jp/nishi/oshirase/index.html']
SOURCE_URL = 'https://www.city.nagoya.jp/nishi/oshirase/index.html'
OUTPUT_FILE = 'municipality-1064-nagoya-nishi.xml'
CHANNEL_TITLE = '1064_愛知県西区'
ALLOWED_DOMAIN = urlparse(SOURCE_URL).netloc
WARD_NAME = '西区'
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
    if date is not None:
        if date.tzinfo is None: raise RuntimeError("Official timezone missing")
        if date > datetime.now(JST): return
    if url not in items: items[url] = (date,title,url)

def one(node, xpath):
    found = node.xpath(xpath)
    if len(found) != 1: raise RuntimeError("Official news structure changed: " + xpath)
    return found[0]

def article_date(page):
    doc=html.fromstring(page.encode('utf-8'))
    if not doc.xpath('//div[@id="voice"]/h1'): raise RuntimeError("Official article body missing")
    nodes=doc.xpath('//p[@class="update"]')
    if len(nodes)!=1:raise RuntimeError("Official update field missing")
    text=normalize(nodes[0].text_content())
    dates=re.findall(r"20\d{2}年\s*\d{1,2}月\s*\d{1,2}日",text)
    if len(dates)>1:raise RuntimeError("Ambiguous official update date")
    return official_date(dates[0]) if dates else None

def parse_source(text, source_url, items):
    from concurrent.futures import ThreadPoolExecutor
    root=urlparse(source_url).path.rsplit('/',1)[0]+'/'
    queue=[(source_url,0,text)]
    visited=set()
    links={}
    while queue:
        url,depth,cached=queue.pop(0)
        if url in visited:continue
        if len(visited)>=25:raise RuntimeError("Too many official category pages")
        visited.add(url)
        doc=html.fromstring((cached if cached is not None else fetch(url)).encode('utf-8'))
        container=one(doc,'//div[@id="voice"]')
        heading=normalize(one(container,'./h1').text_content())
        if url==source_url and heading!=WARD_NAME+'からのお知らせ':raise RuntimeError("Unexpected ward source")
        anchors=container.xpath('.//ul[contains(concat(" ",normalize-space(@class)," ")," listlink ")]/li/a[@href]')
        if not anchors:raise RuntimeError("Official category structure missing")
        for a in anchors:
            target=urljoin(url,a.get('href'))
            parsed=urlparse(target)
            if parsed.netloc!=ALLOWED_DOMAIN or not parsed.path.startswith(root):continue
            if parsed.path.endswith('/index.html'):
                if depth<2:queue.append((target,depth+1,None))
            elif parsed.path.endswith('.html'):
                if target not in links:links[target]=normalize(a.text_content())
    if not links or len(links)>120:raise RuntimeError("Unexpected official article count")
    def read_date(url):return url,article_date(fetch(url))
    with ThreadPoolExecutor(max_workers=4) as pool:
        dates=dict(pool.map(read_date,links))
    for url,title in links.items():add(items,title,url,dates[url],source_url)

def main():
    items={}
    for url in SOURCES: parse_source(fetch(url),url,items)
    if not items: raise RuntimeError("No articles found; existing RSS preserved")
    rows=sorted(items.values(),key=lambda row:row[0] or datetime.min.replace(tzinfo=JST),reverse=True)[:MAX_ITEMS]
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
        if date is not None: SubElement(item,"pubDate").text=format_datetime(date)
        else: SubElement(item,"description").text="公式記事に更新日の記載がないためpubDate省略。"
    temp=Path(OUTPUT_FILE+".tmp")
    ElementTree(rss).write(temp,encoding="utf-8",xml_declaration=True)
    temp.replace(OUTPUT_FILE)
    print(OUTPUT_FILE,len(rows))

if __name__ == "__main__": main()
