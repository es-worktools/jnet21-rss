import json,re,hashlib,importlib.util,concurrent.futures
from urllib.request import Request,urlopen
from urllib.parse import urljoin
from datetime import datetime,timedelta,timezone
from pathlib import Path
from email.utils import parsedate_to_datetime
from lxml import html,etree
JST=timezone(timedelta(hours=9))
SPECS=[('1406','kozagawa'),('1407','kitayama'),('1408','kushimoto'),('1414','wakasa')]
def clean(s):return re.sub(r'\s+',' ',s.replace('\u00ad','')).strip()
def get(u):
 with urlopen(Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=60) as r:return r.read(),r.url,r.headers.get('Content-Type','')
def verify(spec):
 code,slug=spec
 ms=importlib.util.spec_from_file_location('m'+code,f'scrape_municipality_{code}_{slug}.py');m=importlib.util.module_from_spec(ms);ms.loader.exec_module(m)
 m.main();rss=Path(m.OUTPUT_FILE).read_bytes();x=etree.fromstring(rss)
 rows=[{'title':n.findtext('title'),'url':n.findtext('link'),'date':parsedate_to_datetime(n.findtext('pubDate')).astimezone(JST).strftime('%Y-%m-%d') if n.findtext('pubDate') else None} for n in x.findall('./channel/item')]
 b,final,ct=get(m.DATA_URL);expected=[]
 if code=='1414':
  cutoff=datetime.now(JST)-timedelta(days=90);seen=set()
  for item in json.loads(b):
   if item['is_category_index'] or item['is_keitai_page']:continue
   dt=datetime.fromisoformat(item['publish_datetime'])
   if dt<cutoff:break
   if item['url'] in seen:continue
   seen.add(item['url']);expected.append({'title':clean(item['page_name']),'url':item['url'],'date':dt.astimezone(JST).strftime('%Y-%m-%d') if dt<=datetime.now(JST) else None})
 else:
  doc=html.fromstring(b.decode('cp932') if code=='1406' else b)
  if code=='1406':
   # The official homepage's wn.html frame has no dates. Exclude separate closed-status anchors.
   nodes=doc.xpath('//a[@href][@target="_parent"]')
   for a in nodes:expected.append({'title':clean(a.text_content()),'url':urljoin(m.SOURCE_URL,a.get('href')),'date':None})
  else:
   for li in doc.xpath('//ul[@class="whatsnewList"]/li[span]'):
    a=li.xpath('./a')[0];nums=re.findall(r'\d+',li.xpath('./span')[0].text_content());day=datetime(*map(int,nums)).strftime('%Y-%m-%d');expected.append({'title':clean(a.text_content()),'url':urljoin(m.SOURCE_URL,a.get('href')),'date':day})
  expected=list({r['url']:r for r in expected}.values())
 expected=expected[:m.MAX_ITEMS]
 assert rows and rows==expected,(code,'source mismatch')
 assert len({r['url'] for r in rows})==len(rows)
 assert x.findtext('./channel/title')==m.CHANNEL_TITLE
 selected=rows[:2];business=next((r for r in rows if re.search('補助|支援|入札|募集|プロポーザル',r['title'])),None)
 if business and business not in selected:selected.append(business)
 samples=[]
 for row in selected:
  rb,ru,rc=get(row['url']);doc=html.fromstring(rb)
  samples.append({'url':ru,'title':clean(doc.xpath('string(//title)')),'headings':[clean(n.text_content()) for n in doc.xpath('//h1|//h2')][:6]})
 before=Path(m.OUTPUT_FILE).read_bytes();saved=m.fetch;m.fetch=lambda u:'not valid source data'
 try:m.main();raise AssertionError('failed to reject invalid source')
 except (RuntimeError,ValueError,IndexError):pass
 finally:m.fetch=saved
 assert Path(m.OUTPUT_FILE).read_bytes()==before
 return {'code':code,'slug':slug,'title':m.CHANNEL_TITLE,'source_url':m.SOURCE_URL,'data_url':m.DATA_URL,'count':len(rows),'all_items_matched':True,'failure_preserves_existing':True,'source_sha256':hashlib.sha256(b).hexdigest(),'samples':samples,'items':rows,'xml':rss.decode()}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 for result in pool.map(verify,SPECS):print('VRESULT '+json.dumps(result,ensure_ascii=False))
