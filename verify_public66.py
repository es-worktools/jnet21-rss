import json,concurrent.futures,time,re
from urllib.request import Request,urlopen
from lxml import etree
from email.utils import parsedate_to_datetime
from datetime import timezone,timedelta
JST=timezone(timedelta(hours=9))
expected=json.load(open('expected_batch66.json'))
def verify(x):
 url=x['feed_url']
 for attempt in range(4):
  try:
   with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0','Cache-Control':'no-cache'}),timeout=60) as r:b=r.read();final=r.url
   break
  except Exception:
   if attempt==3:raise
   time.sleep(2**attempt)
 tree=etree.fromstring(b)
 rows=[{'title':n.findtext('title'),'url':n.findtext('link'),'date':parsedate_to_datetime(n.findtext('pubDate')).astimezone(JST).strftime('%Y-%m-%d') if n.findtext('pubDate') else None} for n in tree.findall('./channel/item')]
 for row in rows:row['title']=re.sub(r'\s+',' ',row['title'].replace('\u00ad','')).strip()
 assert rows==x['items'],(x['code'],'public mismatch')
 assert tree.findtext('./channel/title')==x['title']
 return {'code':x['code'],'url':final,'count':len(rows),'all_items_matched':True,'title':x['title'],'items':rows,'xml':b.decode('utf-8-sig')}
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
 for result in pool.map(verify,expected):print('PRESULT '+json.dumps(result,ensure_ascii=False))
