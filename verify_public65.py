import json,concurrent.futures
from urllib.request import Request,urlopen
from lxml import etree
from email.utils import parsedate_to_datetime
from datetime import timezone,timedelta
JST=timezone(timedelta(hours=9))
expected=json.load(open('expected_batch65.json'))
def verify(x):
 code=x['code'];url=x.get('feed_url')
 if not url:url='https://es-worktools.github.io/jnet21-rss/municipality-'+code+'-'+{'1363':'asuka','1365':'oji','1373':'nosegawa','1374':'totsukawa'}[code]+'.xml'
 with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0','Cache-Control':'no-cache'}),timeout=60) as r:b=r.read();final=r.url
 tree=etree.fromstring(b)
 if code=='1367':
  from datetime import datetime
  ns={'r':'http://purl.org/rss/1.0/','dc':'http://purl.org/dc/elements/1.1/'}
  rows=[{'title':n.findtext('r:title',namespaces=ns),'url':n.findtext('r:link',namespaces=ns),'date':datetime.fromisoformat(n.findtext('dc:date',namespaces=ns)).astimezone(JST).strftime('%Y-%m-%d')} for n in tree.findall('r:item',ns)]
 else:rows=[{'title':n.findtext('title'),'url':n.findtext('link'),'date':parsedate_to_datetime(n.findtext('pubDate')).astimezone(JST).strftime('%Y-%m-%d') if n.findtext('pubDate') else None} for n in tree.findall('./channel/item')]
 import re
 for row in rows:row['title']=re.sub(r'\s+',' ',row['title'].replace('\u00ad','')).strip()
 assert rows==x['items'],(code,'public mismatch')
 return {'code':code,'url':final,'count':len(rows),'all_items_matched':True,'items':rows,'xml':b.decode('utf-8-sig')}
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
 for r in pool.map(verify,expected):print('PRESULT '+json.dumps(r,ensure_ascii=False))
