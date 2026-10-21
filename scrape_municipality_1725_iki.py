import json, re, time
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from urllib.request import Request, urlopen
from urllib.parse import urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree
from pathlib import Path

SOURCE_URL="https://www.city.iki.nagasaki.jp/news.html"
DATA_URL="https://www.city.iki.nagasaki.jp/index.update.json"
OUTPUT_FILE="municipality-1725-iki.xml"
CHANNEL_TITLE="1725_長崎県壱岐市"
JST=timezone(timedelta(hours=9))

def fetch(url):
    for attempt in range(3):
        try:
            with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json,text/html;q=0.9"}),timeout=40) as r:
                if urlparse(r.url).netloc!="www.city.iki.nagasaki.jp":raise RuntimeError("Unexpected source redirect")
                return r.read().decode("utf-8-sig")
        except Exception:
            if attempt==2:raise
            time.sleep(2**attempt)

def main():
    fetch(SOURCE_URL)
    rows=json.loads(fetch(DATA_URL))
    if not isinstance(rows,list):raise RuntimeError("Official update JSON format changed")
    items={}
    for rec in rows:
        if rec.get("is_category_index") or rec.get("is_keitai_page"):continue
        title=re.sub(r"\s+"," ",str(rec.get("page_name") or "")).strip()
        link=rec.get("url") or ""
        stamp=rec.get("publish_datetime")
        if not (title and link and stamp):continue
        if urlparse(link).netloc!="www.city.iki.nagasaki.jp" or urlparse(link).scheme!="https":continue
        dt=datetime.fromisoformat(stamp)
        if dt.tzinfo is None:raise RuntimeError("Missing official date timezone")
        if dt>datetime.now(JST):continue
        if dt<datetime.now(JST)-timedelta(days=120):continue
        items[link]=(dt,title,link)
    if len(items)<3:raise RuntimeError("No usable current official entries, do not overwrite RSS")
    rss=Element("rss",version="2.0")
    chan=SubElement(rss,"channel")
    SubElement(chan,"title").text=CHANNEL_TITLE
    SubElement(chan,"link").text=SOURCE_URL
    SubElement(chan,"description").text=CHANNEL_TITLE+" GitHub generated RSS"
    for dt,title,link in sorted(items.values(),reverse=True)[:30]:
        item=SubElement(chan,"item")
        SubElement(item,"title").text=title
        SubElement(item,"link").text=link
        SubElement(item,"guid",isPermaLink="true").text=link
        SubElement(item,"pubDate").text=format_datetime(dt)
    tmp=Path(OUTPUT_FILE+".tmp")
    ElementTree(rss).write(tmp,encoding="utf-8",xml_declaration=True)
    tmp.replace(OUTPUT_FILE)
    print(OUTPUT_FILE,len(items))

if __name__=="__main__":main()
