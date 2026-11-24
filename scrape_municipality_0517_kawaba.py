import json, re, time
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlparse
from lxml import html

from municipality_rss_history import write_feed

SOURCES = ['https://www.vill.kawaba.gunma.jp/kurashi/news/']
SOURCE_URL = SOURCES[0]
OUTPUT_FILE = 'municipality-0517-kawaba.xml'
CHANNEL_TITLE = '0517_群馬県川場村'
ALLOWED_DOMAIN = urlparse(SOURCE_URL).netloc
MAX_ITEMS = 30
JST = timezone(timedelta(hours=9))

# This exact HTTPS URL was published in the official dated list.
ALLOWED_EXTERNAL_ARTICLE_URL = (
    "https://www.furusato-tax.jp/gcf/6203"
    "?utm_source=city_portal&utm_medium=referral&utm_campaign=lgmk_10444"
)

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
    parsed = urlparse(url)
    is_official_url = parsed.scheme in {"http", "https"} and parsed.netloc == ALLOWED_DOMAIN
    if not is_official_url and url != ALLOWED_EXTERNAL_ARTICLE_URL:
        raise RuntimeError("Unexpected article URL")
    if date.date() > datetime.now(JST).date(): return
    if url not in items or items[url][0] < date: items[url] = (date,title,url)

def one(node, xpath):
    found = node.xpath(xpath)
    if len(found)!=1: raise RuntimeError("Official news structure changed")
    return found[0]

def parse_source(text,source_url,items):
    tree=html.fromstring(text)
    nodes=tree.xpath('//dt[span[@class="newsSets"]/span[@class="newsSets__date"]]')
    if not nodes: raise RuntimeError("Official dated news list not found")
    for node in nodes:
        dd=node.getnext()
        if dd is None or dd.tag!='dd': raise RuntimeError("Official news structure changed")
        a=one(dd,'.//a[@href]')
        date=official_date(one(node,'./span/span[@class="newsSets__date"]').text_content())
        add(items,a.text_content(),a.get('href').strip(),date,source_url)

def main():
    items={}
    for url in SOURCES: parse_source(fetch(url),url,items)
    if not items: raise RuntimeError("No dated articles found; existing RSS preserved")
    count = write_feed(OUTPUT_FILE, CHANNEL_TITLE, SOURCE_URL, items, MAX_ITEMS)
    print(OUTPUT_FILE, count)

if __name__ == "__main__": main()

