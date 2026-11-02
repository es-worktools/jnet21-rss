import json, re, time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree
from pathlib import Path
from lxml import html

SOURCES = ['https://www.vill.higashishirakawa.gifu.jp/news/', 'https://www.vill.higashishirakawa.gifu.jp/news/?page=2', 'https://www.vill.higashishirakawa.gifu.jp/news/?page=3']
SOURCE_URL = 'https://www.vill.higashishirakawa.gifu.jp/news/'
OUTPUT_FILE = 'municipality-1014-higashishirakawa.xml'
CHANNEL_TITLE = '1014_岐阜県東白川村'
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
    doc=html.fromstring(text)
    rows=doc.xpath('//div[@class="box_news"]/a')
    if not rows: raise RuntimeError("Official current news links missing")
    for a in rows:
        date=official_date(one(a,'.//p[@class="date"]').text)
        add(items,one(a,'.//p[@class="name"]').text_content(),a.get('href'),date,source_url)

def normal_rows():
    items={}
    for url in SOURCES: parse_source(fetch(url),url,items)
    if not items: raise RuntimeError("No articles found; existing RSS preserved")
    return [dict(date=date.isoformat(),title=title,url=url) for date,title,url in sorted(items.values(),reverse=True)]

def main():
    import argparse
    import rss_1014
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',default='config/rss-1014.json')
    parser.add_argument('--mode',choices=['normal','temporary'])
    parser.add_argument('--output',default=OUTPUT_FILE)
    parser.add_argument('--history',default='history/municipality-1014-higashishirakawa.json')
    parser.add_argument('--evidence',default='validation-output/1014')
    args=parser.parse_args()
    report=rss_1014.run(args.config,args.output,args.history,args.evidence,mode=args.mode,normal_provider=normal_rows)
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__ == "__main__": main()
