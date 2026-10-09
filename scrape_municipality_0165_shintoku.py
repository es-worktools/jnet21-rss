import re, time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree
from pathlib import Path
from lxml import html

SOURCES = ['https://www.shintoku-town.jp/oshirase/', 'https://www.shintoku-town.jp/history/']
SOURCE_URL = SOURCES[0]
OUTPUT_FILE = 'municipality-0165-shintoku.xml'
CHANNEL_TITLE = '0165_北海道新得町'
KIND = 'shintoku'
ALLOWED_DOMAIN = urlparse(SOURCE_URL).netloc
MAX_ITEMS = 30
JST = timezone(timedelta(hours=9))

def normalize(text):
    return re.sub(r"\s+", " ", text or "").strip()

def fetch(url):
    for attempt in range(4):
        try:
            with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as response:
                if urlparse(response.url).netloc != ALLOWED_DOMAIN:
                    raise RuntimeError("Unexpected redirect domain")
                return html.fromstring(response.read().decode("utf-8"))
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)

def add(items, a, date_text, base_url):
    title = normalize(a.text_content())
    date_text = normalize(date_text)
    jp = re.search(r"(令和|平成)?(元|\d{1,4})年\s*(\d{1,2})月\s*(\d{1,2})日", date_text)
    iso = re.fullmatch(r"(20\d{2})-(\d{2})-(\d{2})", date_text)
    if jp:
        era, y, m, d = jp.groups()
        y = 1 if y == "元" else int(y)
        y += {"令和":2018,"平成":1988,None:0}[era]
        date = datetime(y,int(m),int(d),tzinfo=JST)
    elif iso:
        date = datetime(*map(int,iso.groups()),tzinfo=JST)
    else:
        raise RuntimeError("Official article date not found")
    if not title:
        raise RuntimeError("Empty article title")
    if date.date() > datetime.now(JST).date():
        return
    url = urljoin(base_url, a.get("href", ""))
    if urlparse(url).scheme not in {"http","https"} or urlparse(url).netloc != ALLOWED_DOMAIN:
        raise RuntimeError("Unexpected article URL")
    if url not in items or items[url][0] < date:
        items[url] = (date,title,url)

def parse_source(tree, source_url, items):
    rows = []
    if KIND == "niikappu":
        for n in tree.xpath('//tr[th[@scope="row"] and td/a[@href]]'):
            rows.append((n.xpath('./td/a[@href]')[0],n.xpath('./th')[0].text_content()))
    elif KIND == "otofuke":
        nodes = tree.xpath('//*[@id="whatNewContetns_shincyakutop"]/dt') if source_url.endswith('/shinchaku/') else tree.xpath('//*[@id="topwhatsNew"]//dt')
        for n in nodes:
            a = n.xpath('following-sibling::*[1][self::dd]/a[@href]')
            if len(a) != 1:
                raise RuntimeError("Official news structure changed")
            rows.append((a[0],n.text_content()))
    elif KIND == "shihoro":
        for n in tree.xpath('//li[p[@class="tier2-news-detail-p1"] and p[@class="tier2-news-detail-p2"]]'):
            a = n.xpath('./p[@class="tier2-news-detail-p2"]/a[@href]')
            if len(a)!=1:
                raise RuntimeError("Official news structure changed")
            rows.append((a[0],n.xpath('./p[@class="tier2-news-detail-p1"]')[0].text_content()))
    elif KIND == "kamishihoro":
        boxes = tree.xpath('//div[@class="fbox-ls pos_rel"][div/div[text()="お知らせ・新着情報"]]/div[@class="fbox-r"]')
        if len(boxes)!=1:
            raise RuntimeError("Official dated news section not found")
        for n in boxes[0].xpath('./div'):
            a = n.xpath('./div/a[@href]')
            if len(a)!=1:
                raise RuntimeError("Official news structure changed")
            rows.append((a[0],n.xpath('./div')[0].text_content()))
    elif KIND == "shintoku":
        for n in tree.xpath('//li[@class="home-info-item"]'):
            a,t = n.xpath('./a[@class="home-info-link"]'),n.xpath('.//time[@datetime]')
            if len(a)!=1 or len(t)!=1:
                raise RuntimeError("Official news structure changed")
            rows.append((a[0],t[0].get('datetime')))
    if not rows:
        raise RuntimeError("Official dated news list not found; existing RSS preserved")
    for a,date_text in rows:
        add(items,a,date_text,source_url)

def main():
    items = {}
    for url in SOURCES:
        parse_source(fetch(url),url,items)
    if not items:
        raise RuntimeError("No dated articles found; existing RSS preserved")
    rows = sorted(items.values(),key=lambda row:row[0],reverse=True)[:MAX_ITEMS]
    rss = Element("rss",version="2.0")
    channel = SubElement(rss,"channel")
    SubElement(channel,"title").text = CHANNEL_TITLE
    SubElement(channel,"link").text = SOURCE_URL
    SubElement(channel,"description").text = CHANNEL_TITLE + " GitHub generated RSS"
    for date,title,url in rows:
        item = SubElement(channel,"item")
        SubElement(item,"title").text = title
        SubElement(item,"link").text = url
        SubElement(item,"guid",isPermaLink="true").text = url
        SubElement(item,"pubDate").text = format_datetime(date)
    temp = Path(OUTPUT_FILE+".tmp")
    ElementTree(rss).write(temp,encoding="utf-8",xml_declaration=True)
    temp.replace(OUTPUT_FILE)
    print(OUTPUT_FILE,len(rows))

if __name__ == "__main__":
    main()
