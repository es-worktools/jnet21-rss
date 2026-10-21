import re, time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from xml.etree.ElementTree import Element, SubElement, ElementTree
from lxml import html

SOURCE_URL = "https://www.city.hirado.nagasaki.jp/kurashi/news/"
OUTPUT_FILE = "municipality-1722-hirado.xml"
CHANNEL_TITLE = "1722_長崎県平戸市"
JST = timezone(timedelta(hours=9))
MAX_ITEMS = 30

def main():
    for attempt in range(3):
        try:
            request = Request(SOURCE_URL, headers={"User-Agent":"Mozilla/5.0"})
            with urlopen(request,timeout=40) as response:
                if urlparse(response.url).netloc != urlparse(SOURCE_URL).netloc:
                    raise RuntimeError("Unexpected redirect domain")
                raw=response.read()
            break
        except Exception:
            if attempt == 2: raise
            time.sleep(2**attempt)
    doc=html.fromstring(raw)
    rows={}
    for a in doc.xpath('//*[@id="main-contents"]/li[span[@class="news-time"]]/a[@href]'):
        href=a.get('href','')
        title=re.sub(r'\s+',' ',a.text_content()).strip()
        parent=a.getparent()
        txt=re.sub(r'\s+',' ',parent.text_content())
        match=re.search(r'(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日',txt)
        if not match or not title:
            continue
        date=datetime(*(int(x) for x in match.groups()),tzinfo=JST)
        if date>datetime.now(JST):raise RuntimeError('Official date is in future')
        link=urljoin(SOURCE_URL,href)
        if urlparse(link).netloc!=urlparse(SOURCE_URL).netloc:raise RuntimeError('Unexpected link domain')
        rows[link]=(date,title,link)
    if len(rows)<8:raise RuntimeError(f'Insufficient official items ({len(rows)}); RSS preserved')
    rss=Element('rss',version='2.0')
    channel=SubElement(rss,'channel')
    SubElement(channel,'title').text=CHANNEL_TITLE
    SubElement(channel,'link').text=SOURCE_URL
    SubElement(channel,'description').text=CHANNEL_TITLE+' GitHub generated RSS'
    for date,title,link in sorted(rows.values(),reverse=True)[:MAX_ITEMS]:
        item=SubElement(channel,'item')
        SubElement(item,'title').text=title
        SubElement(item,'link').text=link
        SubElement(item,'guid',isPermaLink='true').text=link
        SubElement(item,'pubDate').text=format_datetime(date)
    temp=Path(OUTPUT_FILE+'.tmp')
    ElementTree(rss).write(temp,encoding='utf-8',xml_declaration=True)
    temp.replace(OUTPUT_FILE)
    print(OUTPUT_FILE,len(rows))

if __name__=='__main__':main()
