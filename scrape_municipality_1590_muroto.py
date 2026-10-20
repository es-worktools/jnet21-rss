import json, re, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from urllib.request import Request, build_opener, HTTPCookieProcessor
from http.cookiejar import CookieJar
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree
from pathlib import Path
from lxml import html

SOURCE_URL = 'https://www.city.muroto.kochi.jp/pages/info.php'
DATA_URL = 'https://www.city.muroto.kochi.jp/pages/info.php'
OUTPUT_FILE = 'municipality-1590-muroto.xml'
CHANNEL_TITLE = '1590_高知県室戸市'
ALLOWED_DOMAIN = urlparse(SOURCE_URL).netloc
MAX_ITEMS = 30
JST = timezone(timedelta(hours=9))
OPENER = build_opener(HTTPCookieProcessor(CookieJar()))

def normalize(text):
    return re.sub(r"\s+", " ", (text or "").replace("\u00ad", "")).strip()

def fetch(url):
    for attempt in range(4):
        try:
            request = Request(url, headers={"User-Agent":"Mozilla/5.0", "Accept":"application/json,text/html;q=0.9,*/*;q=0.8", "Referer":SOURCE_URL})
            with OPENER.open(request, timeout=60) as response:
                if urlparse(response.url).netloc != ALLOWED_DOMAIN:
                    raise RuntimeError("Unexpected redirect domain")
                return response.read().decode("utf-8-sig")
        except Exception:
            if attempt == 3: raise
            time.sleep(2 ** attempt)

def one(node, xpath):
    nodes = node.xpath(xpath)
    if len(nodes) != 1: raise RuntimeError("Official news structure changed: " + xpath)
    return nodes[0]

def official_date(text):
    match = re.fullmatch(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日", normalize(text))
    if not match: raise RuntimeError("Official date missing: " + text)
    return datetime(*map(int, match.groups()), tzinfo=JST)

def add(items, title, href, date, description=""):
    title = normalize(title)
    if not title or not href: raise RuntimeError("Missing article title or URL")
    url = urljoin(SOURCE_URL, href)
    if urlparse(url).scheme not in {"http","https"} or urlparse(url).netloc != ALLOWED_DOMAIN:
        raise RuntimeError("Unexpected article URL: " + url)
    if date is not None and (date.tzinfo is None or date > datetime.now(JST)):
        raise RuntimeError("Invalid publication date")
    if url not in items: items[url] = (date, title, url, description)

def parse_source(text, items):
    doc = html.fromstring(text.encode('utf-8'))
    links = doc.xpath('//div[@id="id_main"]//div[contains(concat(" ",normalize-space(@class)," ")," cs_info1 ")]/dl/dd/a[@href]')
    if not links: raise RuntimeError('Official news list missing')
    candidates = []
    seen = set()
    for link in links:
        url = urljoin(SOURCE_URL, link.get('href'))
        if urlparse(url).netloc != ALLOWED_DOMAIN or not re.fullmatch(r'/pages/page\d+\.php',urlparse(url).path):
            raise RuntimeError('Unexpected news article URL')
        if url in seen: continue
        seen.add(url)
        label = normalize(link.getparent().text_content())
        monthday = re.search(r'（(\d{1,2})月(\d{1,2})日更新）',label)
        if not monthday: raise RuntimeError('List update date missing')
        candidates.append((url,normalize(link.text_content()),tuple(map(int,monthday.groups()))))
        if len(candidates) >= MAX_ITEMS: break
    def article(candidate):
        url,title,monthday = candidate
        page = html.fromstring(fetch(url).encode('utf-8'))
        main = one(page,'//div[@id="pb_main"]')
        heading = one(main,'./h2')
        if normalize(heading.text_content()) != title: raise RuntimeError('Article title differs from official list')
        dates = [re.fullmatch(r'(20\d{2})年(\d{1,2})月(\d{1,2})日\s*更新',normalize(p.text_content())) for p in main.xpath('./p')]
        dates = [m for m in dates if m]
        if len(dates) > 1: raise RuntimeError('Ambiguous article update date')
        date = None
        if dates:
            values = tuple(map(int,dates[0].groups()))
            if values[1:] == monthday: date = datetime(*values,tzinfo=JST)
        description = f'公式新着一覧の更新日：{monthday[0]}月{monthday[1]}日。'
        if date is None: description += '年を含む一致した更新日を確認できないためRSS日付は付与していません。'
        return title,url,date,description
    with ThreadPoolExecutor(max_workers=4) as pool:
        for title,url,date,description in pool.map(article,candidates): add(items,title,url,date,description)


def main():
    if DATA_URL != SOURCE_URL: fetch(SOURCE_URL)
    items = {}
    parse_source(fetch(DATA_URL), items)
    if not items: raise RuntimeError("No articles found; existing RSS preserved")
    # Preserve the official list order, including entries with no usable date.
    rows = list(items.values())[:MAX_ITEMS]
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = CHANNEL_TITLE
    SubElement(channel, "link").text = SOURCE_URL
    SubElement(channel, "description").text = CHANNEL_TITLE + " GitHub generated RSS"
    for date, title, url, description in rows:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = title
        SubElement(item, "link").text = url
        SubElement(item, "guid", isPermaLink="true").text = url
        if date is not None: SubElement(item, "pubDate").text = format_datetime(date)
        if description: SubElement(item, "description").text = description
    temp = Path(OUTPUT_FILE + ".tmp")
    ElementTree(rss).write(temp, encoding="utf-8", xml_declaration=True)
    temp.replace(OUTPUT_FILE)
    print(OUTPUT_FILE, len(rows))

if __name__ == "__main__": main()
