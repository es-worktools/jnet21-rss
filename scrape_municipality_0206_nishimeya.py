import json, re, time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree
from pathlib import Path
from lxml import html

SOURCES = ["https://www.nishimeya.jp/","https://www.nishimeya.jp/index.update.json"]
SOURCE_URL = SOURCES[0]
OUTPUT_FILE = 'municipality-0206-nishimeya.xml'
CHANNEL_TITLE = '0206_青森県西目屋村'
KIND = 'nishimeya'
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
    tree=html.fromstring(text)
    rows=[]
    if KIND == "goshogawara":
        for n in tree.xpath('//tr[td[@class="date"] and td[@class="line"]/a[@href]]'):
            a=one(n,'./td[@class="line"]/a[@href]')
            rows.append((a.text_content(),a.get('href'),official_date(one(n,'./td[@class="date"]').text_content())))
    elif KIND == "yomogita":
        for n in tree.xpath('//li[span[@class="date"] and a[@class="page_link"][@href]]'):
            a=one(n,'./a[@class="page_link"][@href]')
            rows.append((a.text_content(),a.get('href'),official_date(one(n,'./span[@class="date"]').text_content())))
    elif KIND == "owani":
        for n in tree.xpath('//li[@datetime][a[@class="tit"][@href]]'):
            a=one(n,'./a[@class="tit"][@href]')
            date=official_date(n.get('datetime'))
            for department in a.xpath('./span[@class="sig_name"]'): a.remove(department)
            rows.append((a.text_content(),a.get('href'),date))
    elif KIND == "itayanagi":
        form=one(tree,'//form[@name="ListFrm"]')
        if form.get('method','').lower() != 'get':
            raise RuntimeError("Official article navigation method changed")
        scripts="\n".join(tree.xpath('//script[not(@src)]/text()'))
        if not re.search(r"function\s+JumpToDetails\(id\)",scripts) or 'document.ListFrm.id.value = id;' not in scripts or 'document.ListFrm.action = "info-details.php";' not in scripts:
            raise RuntimeError("Official article navigation changed")
        for n in form.xpath('.//li[span[@class="day"] and a[@href]]'):
            a=one(n,'./a[@href]')
            match=re.fullmatch(r"javascript:JumpToDetails\('(\d+)'\);",a.get('href'))
            if not match: raise RuntimeError("Unexpected official article ID")
            href='info-details.php?id='+match.group(1)
            rows.append((a.text_content(),href,official_date(one(n,'./span[@class="day"]').text_content())))
    if not rows: raise RuntimeError("Official dated news list not found; existing RSS preserved")
    for title,href,date in rows: add(items,title,href,date,source_url)

def parse_json(text,items):
    records=json.loads(text)
    if not isinstance(records,list) or not records: raise RuntimeError("Unexpected official JSON schema")
    for record in records:
        keys={"page_name","url","publish_datetime","is_category_index","is_keitai_page"}
        if not isinstance(record,dict) or not keys.issubset(record):raise RuntimeError("Official JSON structure changed")
        if not isinstance(record['is_category_index'],bool) or not isinstance(record['is_keitai_page'],bool):raise RuntimeError("Unexpected official JSON flags")
        if record['is_category_index'] or record['is_keitai_page']:continue
        date=datetime.fromisoformat(record['publish_datetime'])
        if date.tzinfo is None:raise RuntimeError("Official date has no timezone")
        date=date.astimezone(JST)
        if date < datetime.now(JST)-timedelta(days=90):continue
        add(items,record['page_name'],record['url'],date,SOURCE_URL)

def main():
    items={}
    if KIND == 'nishimeya': parse_json(fetch(SOURCES[1]),items)
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

