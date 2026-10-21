import json,re,time
from datetime import datetime,timedelta,timezone
from email.utils import format_datetime
from urllib.request import Request,urlopen
from urllib.parse import urlparse
from xml.etree.ElementTree import Element,SubElement,ElementTree
from pathlib import Path
SOURCE_URL="https://www.town.ojika.lg.jp/news_list.html"
DATA_URL="https://www.town.ojika.lg.jp/index.update.json"
OUTPUT_FILE="municipality-1735-ojika.xml"
CHANNEL_TITLE="1735_長崎県小値賀町"
JST=timezone(timedelta(hours=9))
def fetch(url):
 for attempt in range(3):
  try:
   with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0"}),timeout=40) as r:
    if urlparse(r.url).netloc!="www.town.ojika.lg.jp":raise RuntimeError("Unexpected official redirect")
    return r.read().decode("utf-8-sig")
  except Exception:
   if attempt==2:raise
   time.sleep(2**attempt)
def main():
 fetch(SOURCE_URL)
 data=json.loads(fetch(DATA_URL))
 if not isinstance(data,list):raise RuntimeError("Official JSON format changed")
 now=datetime.now(JST)
 records={}
 for rec in data:
  if rec.get("is_category_index") or rec.get("is_keitai_page"):continue
  title=re.sub(r"\\s+"," ",str(rec.get("page_name") or "")).strip()
  link=str(rec.get("url") or "")
  stamp=rec.get("publish_datetime")
  if not(title and link and stamp):continue
  if urlparse(link).scheme!="https" or urlparse(link).netloc!="www.town.ojika.lg.jp":continue
  date=datetime.fromisoformat(stamp)
  if date.tzinfo is None:raise RuntimeError("Official date lacks timezone")
  if not now-timedelta(days=180)<=date<=now:continue
  records[link]=(date,title,link)
 if len(records)<3:raise RuntimeError(f"Only {len(records)} current items; RSS preserved")
 rss=Element("rss",version="2.0")
 chan=SubElement(rss,"channel")
 SubElement(chan,"title").text=CHANNEL_TITLE
 SubElement(chan,"link").text=SOURCE_URL
 SubElement(chan,"description").text=CHANNEL_TITLE+" GitHub generated RSS"
 for date,title,link in sorted(records.values(),reverse=True)[:30]:
  item=SubElement(chan,"item")
  SubElement(item,"title").text=title
  SubElement(item,"link").text=link
  SubElement(item,"guid",isPermaLink="true").text=link
  SubElement(item,"pubDate").text=format_datetime(date)
 tmp=Path(OUTPUT_FILE+".tmp")
 ElementTree(rss).write(tmp,encoding="utf-8",xml_declaration=True)
 tmp.replace(OUTPUT_FILE)
 print(OUTPUT_FILE,len(records))
if __name__=="__main__":main()
