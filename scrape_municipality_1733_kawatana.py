import re,time
from datetime import datetime,timedelta,timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin,urlparse
from urllib.request import Request,urlopen
from xml.etree.ElementTree import Element,SubElement,ElementTree
from lxml import html
SOURCE_URL="https://www.kawatana.jp/topics/news/index.html"
OUTPUT_FILE="municipality-1733-kawatana.xml"
CHANNEL_TITLE="1733_長崎県川棚町"
JST=timezone(timedelta(hours=9))
def main():
 for attempt in range(3):
  try:
   with urlopen(Request(SOURCE_URL,headers={"User-Agent":"Mozilla/5.0"}),timeout=40) as resp:
    if urlparse(resp.url).netloc!="www.kawatana.jp":raise RuntimeError("Unexpected redirect")
    doc=html.fromstring(resp.read())
   break
  except Exception:
   if attempt==2:raise
   time.sleep(2**attempt)
 records={}
 for li in doc.xpath('//div[@id="sub_page"]//article[@id="contents"]//div[contains(concat(" ",normalize-space(@class)," ")," entry ")]//li[div[contains(concat(" ",normalize-space(@class)," ")," date ")] and a[@href]]'):
  nodes=li.xpath('./div[contains(concat(" ",normalize-space(@class)," ")," date ")]')
  links=li.xpath('./a[@href]')
  if len(nodes)!=1 or len(links)!=1:continue
  stamp=re.sub(r"\\s+","",nodes[0].text_content())
  match=re.fullmatch(r'令和(\\d{1,2})年(\\d{1,2})月(\\d{1,2})日',stamp)
  if not match:raise RuntimeError("Unexpected official date: "+stamp)
  y,m,d=map(int,match.groups())
  date=datetime(2018+y,m,d,tzinfo=JST)
  if date>datetime.now(JST):continue
  title=re.sub(r"\\s+"," ",links[0].text_content()).strip()
  url=urljoin(SOURCE_URL,links[0].get("href"))
  if urlparse(url).netloc!="www.kawatana.jp" or not title:continue
  records[url]=(date,title,url)
 if len(records)<5:raise RuntimeError("Official listing unexpectedly empty")
 rss=Element("rss",version="2.0")
 c=SubElement(rss,"channel")
 SubElement(c,"title").text=CHANNEL_TITLE
 SubElement(c,"link").text=SOURCE_URL
 SubElement(c,"description").text="川棚町お知らせ（GitHub生成RSS）"
 for date,title,url in sorted(records.values(),reverse=True)[:30]:
  item=SubElement(c,"item")
  SubElement(item,"title").text=title
  SubElement(item,"link").text=url
  SubElement(item,"guid",isPermaLink="true").text=url
  SubElement(item,"pubDate").text=format_datetime(date)
 tmp=Path(OUTPUT_FILE+".tmp")
 ElementTree(rss).write(tmp,encoding="utf-8",xml_declaration=True)
 tmp.replace(OUTPUT_FILE)
 print("Generated",OUTPUT_FILE,len(records))
if __name__=="__main__":main()
