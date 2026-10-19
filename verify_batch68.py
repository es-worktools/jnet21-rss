import json,re,hashlib,importlib.util,concurrent.futures,time
from urllib.request import Request,urlopen
from urllib.parse import urljoin
from datetime import datetime,timedelta,timezone
from pathlib import Path
from email.utils import parsedate_to_datetime
from lxml import html,etree
JST=timezone(timedelta(hours=9))
SPECS=[('1400','hidakagawa'),('1401','shirahama'),('1402','kamitonda'),('1403','susami'),('1405','taiji')]
def clean(s):return re.sub(r'\s+',' ',s.replace('\u00ad','')).strip()
def get(u):
 for attempt in range(4):
  try:
   with urlopen(Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=60) as r:return r.read(),r.url,r.headers.get('Content-Type','')
  except Exception:
   if attempt==3:raise
   time.sleep(2**attempt)
def verify(spec):
 code,slug=spec
 modspec=importlib.util.spec_from_file_location('m'+code,f'scrape_municipality_{code}_{slug}.py');m=importlib.util.module_from_spec(modspec);modspec.loader.exec_module(m)
 m.main();rss=Path(m.OUTPUT_FILE).read_bytes();x=etree.fromstring(rss)
 rows=[{'title':n.findtext('title'),'url':n.findtext('link'),'date':parsedate_to_datetime(n.findtext('pubDate')).astimezone(JST).strftime('%Y-%m-%d') if n.findtext('pubDate') else None} for n in x.findall('./channel/item')]
 assert rows and len({r['url'] for r in rows})==len(rows)
 expected=[];b,final,ctype=get(m.DATA_URL)
 if code in ['1401','1402']:
  cutoff=datetime.now(JST)-timedelta(days=60 if code=='1402' else 90);seen=set()
  for r in json.loads(b):
   if r['is_category_index'] or r['is_keitai_page']:continue
   dt=datetime.fromisoformat(r['publish_datetime'])
   if dt<cutoff:break
   if r['url'] in seen:continue
   seen.add(r['url']);expected.append({'title':clean(r['page_name']),'url':r['url'],'date':dt.astimezone(JST).strftime('%Y-%m-%d') if dt<=datetime.now(JST) else None})
 else:
  doc=html.fromstring(b)
  nodes=doc.xpath('//div[contains(concat(" ",normalize-space(@class)," ")," whatsnewList ")]/ul/li[span[@class="post-date" or @class="postDate"]]')
  if code=='1400':
   top,_,_=get(m.EXTRA_SOURCE_URL);td=html.fromstring(top)
   nodes+=td.xpath('//li[span[@class="post-date"]]')
  by_url={}
  for node in nodes:
   a=node.xpath('./a')[0];date=node.xpath('./span')[0];nums=re.findall(r'\d+',date.text_content());day=datetime(*map(int,nums)).strftime('%Y-%m-%d');u=urljoin(m.SOURCE_URL,a.get('href'))
   row={'title':clean(a.text_content()),'url':u,'date':day}
   if u not in by_url or day>by_url[u]['date']:by_url[u]=row
  expected=list(by_url.values())
  if code=='1400':expected.sort(key=lambda row:row['date'],reverse=True)
 expected=expected[:m.MAX_ITEMS]
 assert rows==expected,(code,'all-item source comparison failed',rows[:3],expected[:3])
 assert x.findtext('./channel/title')==m.CHANNEL_TITLE
 samples=[];sample_rows=rows[:2]
 business=next((r for r in rows if re.search('補助|支援|入札|公募|商品|セミナー|プロポーザル',r['title'])),None)
 if business and business not in sample_rows:sample_rows=sample_rows+[business]
 for row in sample_rows:
  b2,final2,ct=get(row['url'])
  if 'pdf' in ct:samples.append({'url':final2,'content_type':ct,'bytes':len(b2)});continue
  doc=html.fromstring(b2)
  samples.append({'url':final2,'title':clean(' '.join(doc.xpath('//title/text()'))),'headings':[clean(n.text_content()) for n in doc.xpath('//h1|//h2')][:8]})
 before=Path(m.OUTPUT_FILE).read_bytes();fetch_orig=m.fetch;m.fetch=lambda url:'not valid source data'
 try:m.main();raise AssertionError('failure not raised')
 except (RuntimeError,ValueError,IndexError,json.JSONDecodeError):pass
 finally:m.fetch=fetch_orig
 assert Path(m.OUTPUT_FILE).read_bytes()==before
 return {'code':code,'count':len(rows),'items':rows,'source_url':m.SOURCE_URL,'data_url':m.DATA_URL,'source_sha256':hashlib.sha256(b).hexdigest(),'all_items_matched':True,'failure_preserves_existing':True,'samples':samples,'xml':rss.decode()}
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
 for result in pool.map(verify,SPECS):print('VRESULT '+json.dumps(result,ensure_ascii=False))
