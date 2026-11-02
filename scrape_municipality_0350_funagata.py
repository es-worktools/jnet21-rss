import json, re, time, logging
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree
from pathlib import Path
from lxml import html

SOURCES = ['https://www.town.funagata.yamagata.jp/news.html']
SOURCE_URL = SOURCES[0]
OUTPUT_FILE = 'municipality-0350-funagata.xml'
CHANNEL_TITLE = '0350_山形県舟形町'
ALLOWED_DOMAIN = urlparse(SOURCE_URL).netloc
MAX_ITEMS = 20
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
    if date is not None and date.date() > datetime.now(JST).date(): return
    if url not in items or (date is not None and (items[url][0] is None or items[url][0] < date)):
        items[url] = (date,title,url)

def one(node, xpath):
    found = node.xpath(xpath)
    if len(found)!=1: raise RuntimeError("Official news structure changed")
    return found[0]

def parse_source(text,source_url,items):
    tree=html.fromstring(text)
    nodes=tree.xpath('//dl[@class="news icon"]/dd')
    if not nodes: raise RuntimeError("Official dated news list not found")
    # The list omits the year. Never infer it from the URL or current date.
    candidates=[]
    for node in nodes[:MAX_ITEMS]:
        a=one(node,'./a[@href]')
        url=urljoin(source_url,a.get('href'))
        if urlparse(url).netloc!=ALLOWED_DOMAIN: raise RuntimeError("Unexpected article domain")
        candidates.append((a.text_content(),url))
    def article(candidate):
        title,url=candidate
        detail=html.fromstring(fetch(url))
        date_nodes=detail.xpath('//p[contains(concat(" ",normalize-space(@class)," ")," right ") and contains(text(),"更新日")]')
        if date_nodes:
            if len(date_nodes) != 1: raise RuntimeError('Ambiguous official update date')
            return title,url,official_date(date_nodes[0].text_content())
        # The town's PR templates omit p.right; some explicitly give a
        # publication date at the start of the article's text box.
        published=[]
        for node in detail.xpath('//div[contains(concat(" ",normalize-space(@class)," ")," txtbox ")]'):
            label=re.match(r'^掲載日\s*[：:]\s*((?:令和|平成)?(?:元|\d{1,4})年\s*\d{1,2}月\s*\d{1,2}日)', normalize(node.text_content()))
            if label: published.append(official_date(label.group(1)))
        if published:
            if len(published) != 1: raise RuntimeError('Ambiguous official publication date')
            return title,url,published[0]
        # Preserve a listed article even when its PR template has no full
        # date. RSS permits omitted pubDate. Verify the expected detail
        # structure so an error/block page cannot silently become an item.
        if not detail.xpath('//h1') or not detail.xpath('//div[contains(concat(" ",normalize-space(@class)," ")," txtbox ")]'):
            raise RuntimeError('Official article structure changed: '+url)
        logging.warning('Official full date unavailable; included without pubDate: %s', url)
        return title,url,None
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool:
        for title,url,date in pool.map(article,candidates):
            add(items,title,url,date,source_url)

def main():
    items={}
    for url in SOURCES: parse_source(fetch(url),url,items)
    if not items: raise RuntimeError("No dated articles found; existing RSS preserved")
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
    temp=Path(OUTPUT_FILE+".tmp")
    ElementTree(rss).write(temp,encoding="utf-8",xml_declaration=True)
    temp.replace(OUTPUT_FILE)
    print(OUTPUT_FILE,len(rows))

if __name__ == "__main__": main()

