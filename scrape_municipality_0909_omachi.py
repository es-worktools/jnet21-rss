import json, re, time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree
from pathlib import Path
from lxml import html

SOURCES = ['https://www.city.omachi.nagano.jp/news']
SOURCE_URL = SOURCES[0]
OUTPUT_FILE = 'municipality-0909-omachi.xml'
CHANNEL_TITLE = '0909_長野県大町市'
ALLOWED_DOMAIN = urlparse(SOURCE_URL).netloc
MAX_ITEMS = 60
JST = timezone(timedelta(hours=9))

ALLOWED_ARTICLE_DOMAINS = {ALLOWED_DOMAIN}

def normalize(text):
    return re.sub(r"\s+", " ", (text or "").replace("\u00ad", "")).strip()

def fetch(url):
    for attempt in range(4):
        try:
            with urlopen(Request(url, headers={"User-Agent":"Mozilla/5.0"}), timeout=60) as response:
                if urlparse(response.url).netloc not in ALLOWED_FETCH_DOMAINS:
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

API_ROOT = 'https://omachi-adm.codefiesta.work/api'
ALLOWED_FETCH_DOMAINS = {'omachi-adm.codefiesta.work'}
EXCLUDE_MAYOR = False

def make_sources():
    from urllib.parse import urlencode
    now=datetime.now(timezone.utc).isoformat()
    urls=[API_ROOT+'/v1/mayor_contents/edit']
    for kind in ['article','open_call']:
        params={'filters[type][$eq]':kind,'filters[$and][0][start_at_for_notice][$lte]':now,'filters[$and][1][$or][0][close_at_for_notice][$null]':'true','filters[$and][1][$or][1][close_at_for_notice][$gte]':now,'filters[$and][2][category][$notNull]':'true','sort':'start_at:desc','pagination[pageSize]':'50','populate[category][fields][0]':'name_ja','populate[category][fields][1]':'slug_full'}
        urls.append(API_ROOT+'/contents?'+urlencode(params))
    return urls

SOURCES = make_sources()

def parse_source(text, source_url, items):
    global EXCLUDE_MAYOR
    data=json.loads(text)
    if source_url.endswith('/mayor_contents/edit'):
        EXCLUDE_MAYOR = data['content']['enabled'] is False
        return
    rows=data['data']
    if not isinstance(rows,list):raise RuntimeError("Official article API structure changed")
    count=0
    for row in rows:
        cat=row['category']['slug_full']
        if EXCLUDE_MAYOR and cat.startswith('shicho/'):continue
        published=datetime.fromisoformat(row['start_at'].replace('Z','+00:00')).astimezone(JST)
        if published>datetime.now(JST):continue
        slug=(row.get('slug') or '').strip() or (row.get('documentId') or '').strip() or str(row['id'])
        url='https://www.city.omachi.nagano.jp/'+cat+'/'+slug
        date=published.replace(hour=0,minute=0,second=0,microsecond=0)
        add(items,row['title'],url,date,SOURCE_URL)
        count+=1
        if count>=30:break

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


