import json,re,hashlib,importlib.util,concurrent.futures
from urllib.request import Request,urlopen
from urllib.parse import urljoin
from datetime import datetime,timedelta,timezone
from pathlib import Path
from email.utils import parsedate_to_datetime
from lxml import html,etree
JST=timezone(timedelta(hours=9))
SPECS=[('1448','okayama_kita'),('1449','okayama_naka'),('1450','okayama_higashi'),('1451','okayama_minami'),('1453','tsuyama')]
def clean(s):return re.sub(r'\s+',' ',s.replace('\u00ad','')).strip()
def get(u,payload=None):
 headers={'User-Agent':'Mozilla/5.0'}
 if payload is not None:headers['Content-Type']='application/json'
 with urlopen(Request(u,data=json.dumps(payload).encode() if payload is not None else None,headers=headers),timeout=60) as r:return r.read(),r.url
def verify(spec):
 code,slug=spec
 ms=importlib.util.spec_from_file_location('m'+code,f'scrape_municipality_{code}_{slug}.py');m=importlib.util.module_from_spec(ms);ms.loader.exec_module(m)
 m.main();rss=Path(m.OUTPUT_FILE).read_bytes();x=etree.fromstring(rss)
 rows=[{'title':n.findtext('title'),'url':n.findtext('link'),'time':parsedate_to_datetime(n.findtext('pubDate')).astimezone(JST).isoformat()} for n in x.findall('./channel/item')]
 expected=[];source_checks=[];by_url={}
 if code=='1453':
  for i in range(3):
   payload={'tenantId':'10','siteId':'1001','pageId':'PTARS51','langCode':'JPN','retrievalCount':i,'bulkFlg':False,'articleListContentsType':'latest','originPageId':'PTHMS59','tabType':'all'}
   b,u=get(m.DATA_URL,payload);d=json.loads(b);source_checks.append({'url':u,'page':i,'sha256':hashlib.sha256(b).hexdigest()})
   for a in d['data']['articleList']:
    expected.append({'title':clean(a['title']),'url':urljoin(m.SOURCE_URL,a['articleTransitionUrl'])+'?articleId='+a['articleId'],'time':a['publishStartDateTime']+'+09:00'})
   if not d['data']['hasMore']:break
  selected=expected[:2]
  business=next((r for r in expected if re.search('補助|支援|入札|募集|サウンディング|企画競争',r['title'])),None)
  if business and business not in selected:selected.append(business)
  samples=[]
  for row in selected:
   article_id=row['url'].split('articleId=')[1]
   b,u=get('https://www.city.tsuyama.lg.jp/prd/tym/portal/openapi/v1/article/detail/retrieve',{'tenantId':'10','siteId':'1001','langCode':'JPN','pageId':'PTARS53','articleId':article_id})
   detail=json.loads(b)['data'];j=detail['jpn'];assert detail['articleId']==article_id and detail['requireLoggedIn']=='N'
   assert clean(j['title'])==row['title']
   assert j['publishStartDatetime']+'+09:00'==row['time']
   samples.append({'url':row['url'],'heading':clean(j['title']),'time':j['publishStartDatetime'],'detail_api_verified':True})
 else:
  for u in m.SOURCE_URLS:
   b,final=get(u);doc=html.fromstring(b);source_checks.append({'url':final,'sha256':hashlib.sha256(b).hexdigest()})
   for date in doc.xpath('//article[contains(@class,"kakuka_new") or contains(@class,"kakuka_right")]//li/span[@class="date"] | //article[contains(@class,"kakuka_new") or contains(@class,"kakuka_right")]//li/div[@class="date"]'):
    li=date.getparent();a=li.xpath('.//a[@href]')[0];day=datetime(*map(int,re.findall(r'\d+',date.text_content())),tzinfo=JST).isoformat();url=urljoin(u,a.get('href'));r={'title':clean(a.text_content()),'url':url,'time':day}
    if url not in by_url or day>by_url[url]['time']:by_url[url]=r
  expected=sorted(by_url.values(),key=lambda r:r['time'],reverse=True)
  selected=expected[:2];business=next((r for r in expected if re.search('補助|支援|入札|募集|企画競争|プロポーザル',r['title'])),None)
  if business and business not in selected:selected.append(business)
  samples=[]
  for row in selected:
   b,u=get(row['url']);doc=html.fromstring(b);text=clean(doc.text_content());date=datetime.fromisoformat(row['time']);assert f'{date.year}年{date.month}月{date.day}日' in text,(code,'sample date mismatch',row)
   h=clean(' '.join(doc.xpath('//h1//text()')));assert h==row['title'],(code,'sample title mismatch',h,row)
   samples.append({'url':u,'heading':h,'date_matched':True})
 expected=expected[:m.MAX_ITEMS]
 assert rows and rows==expected,(code,'source mismatch',rows,expected)
 assert len({r['url'] for r in rows})==len(rows)
 assert x.findtext('./channel/title')==m.CHANNEL_TITLE
 before=Path(m.OUTPUT_FILE).read_bytes();saved=m.fetch;m.fetch=lambda *args:'not valid source data'
 try:m.main();raise AssertionError('failed to reject invalid source')
 except (RuntimeError,ValueError,IndexError):pass
 finally:m.fetch=saved
 assert Path(m.OUTPUT_FILE).read_bytes()==before
 return {'code':code,'slug':slug,'title':m.CHANNEL_TITLE,'source_url':m.SOURCE_URL,'data_url':m.DATA_URL,'count':len(rows),'all_items_matched':True,'failure_preserves_existing':True,'source_checks':source_checks,'samples':samples,'items':rows,'xml':rss.decode()}
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
  for result in pool.map(verify,SPECS):print('VRESULT '+json.dumps(result,ensure_ascii=False),flush=True)
