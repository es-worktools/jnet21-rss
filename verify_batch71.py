import json,re,hashlib,importlib.util,concurrent.futures
from urllib.request import Request,urlopen
from urllib.parse import urljoin
from datetime import datetime,timedelta,timezone
from pathlib import Path
from email.utils import parsedate_to_datetime
from lxml import html,etree
JST=timezone(timedelta(hours=9))
SPECS=[('1442','yoshika'),('1443','ama'),('1444','nishinoshima'),('1445','chibu')]
def clean(s):return re.sub(r'\s+',' ',s.replace('\u00ad','')).strip()
def get(u):
 with urlopen(Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=60) as r:return r.read(),r.url,r.headers.get('Content-Type','')
def verify(spec):
 code,slug=spec
 ms=importlib.util.spec_from_file_location('m'+code,f'scrape_municipality_{code}_{slug}.py');m=importlib.util.module_from_spec(ms);ms.loader.exec_module(m)
 m.main();rss=Path(m.OUTPUT_FILE).read_bytes();x=etree.fromstring(rss)
 rows=[{'title':n.findtext('title'),'url':n.findtext('link'),'date':parsedate_to_datetime(n.findtext('pubDate')).astimezone(JST).strftime('%Y-%m-%d') if n.findtext('pubDate') else None} for n in x.findall('./channel/item')]
 b,final,ct=get(m.DATA_URL);expected=[]
 doc=html.fromstring(b);expected=[]
 if code=='1442':
  by_url={}
  for dt in doc.xpath('//div[@id="tab1" or @id="tab2"]/dl/dt'):
   dd=dt.getnext();a=dd.xpath('./a')[0];nums=re.findall(r'\d+',dt.text_content());day=datetime(*map(int,nums)).strftime('%Y-%m-%d');url=urljoin(m.SOURCE_URL,a.get('href'));row={'title':clean(a.text_content()),'url':url,'date':day}
   if url not in by_url or day>by_url[url]['date']:by_url[url]=row
  expected=sorted(by_url.values(),key=lambda r:r['date'],reverse=True)
 elif code=='1443':
  for a in doc.xpath('//a[@href]'):
   if not re.fullmatch(r'/information/\d+',a.get('href')):continue
   row=a.getparent().getparent().getparent();t=row.text_content();match=re.search(r'(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日',t);assert match
   day=datetime(*map(int,match.groups())).strftime('%Y-%m-%d');expected.append({'title':clean(a.text_content()),'url':urljoin(m.SOURCE_URL,a.get('href')),'date':day})
 elif code=='1445':
  by_url={}
  for li in doc.xpath('//div[contains(@class,"content-top1-l-2-infoarea")]//li[span[@class="date"] and span[@class="title"]/a]'):
   a=li.xpath('./span[@class="title"]/a')[0];t=li.xpath('./span[@class="date"]')[0].text_content();day=datetime(*map(int,re.findall(r'\d+',t))).strftime('%Y-%m-%d');url=urljoin(m.SOURCE_URL,a.get('href'));row={'title':clean(a.text_content()),'url':url,'date':day}
   if url not in by_url or day>by_url[url]['date']:by_url[url]=row
  expected=sorted(by_url.values(),key=lambda r:r['date'],reverse=True)
 else:
  for li in doc.xpath('//li[contains(@class,"pagelist-item")]'):
   a=li.xpath('./span[@class="title"]/a')[0];t=li.xpath('./span[@class="date"]')[0].text_content();day=datetime(*map(int,re.findall(r'\d+',t))).strftime('%Y-%m-%d');expected.append({'title':clean(a.text_content()),'url':urljoin(m.SOURCE_URL,a.get('href')),'date':day})
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
