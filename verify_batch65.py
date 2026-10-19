import json,re,hashlib,importlib.util,concurrent.futures
from urllib.request import Request,urlopen
from urllib.parse import urljoin
from datetime import datetime,timedelta,timezone
from pathlib import Path
from email.utils import parsedate_to_datetime
from lxml import html,etree
JST=timezone(timedelta(hours=9))
def clean(s):return re.sub(r'\s+',' ',s.replace('\u00ad','')).strip()
def get(u):
 with urlopen(Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=60) as r:return r.read(),r.url
def verify(spec):
 code,slug=spec
 path=f'scrape_municipality_{code}_{slug}.py'
 modspec=importlib.util.spec_from_file_location('m'+code,path);m=importlib.util.module_from_spec(modspec);modspec.loader.exec_module(m)
 m.main()
 rss=Path(m.OUTPUT_FILE).read_bytes();x=etree.fromstring(rss)
 rows=[{'title':i.findtext('title'),'url':i.findtext('link'),'date':parsedate_to_datetime(i.findtext('pubDate')).astimezone(JST).strftime('%Y-%m-%d') if i.findtext('pubDate') else None} for i in x.findall('./channel/item')]
 assert len(rows)>0 and len({r['url'] for r in rows})==len(rows)
 b,final=get(m.DATA_URL);expected=[]
 if code in ['1365','1373']:
  data=json.loads(b);cutoff=datetime.now(JST)-timedelta(days=30 if code=='1365' else 90)
  seen=set()
  for r in data:
   if r['is_category_index'] or r['is_keitai_page']:continue
   dt=datetime.fromisoformat(r['publish_datetime'])
   if dt<cutoff:break
   if r['url'] in seen:continue
   seen.add(r['url'])
   expected.append({'title':clean(r['page_name']),'url':r['url'],'date':dt.astimezone(JST).strftime('%Y-%m-%d') if dt<=datetime.now(JST) else None})
 else:
  d=html.fromstring(b)
  if code=='1363':
   tabs=d.xpath('//div[@class="tab-content"]');nodes=tabs[0].xpath('.//div[@class="News_Wrapp"]')+tabs[2].xpath('.//div[@class="News_Wrapp"]')
  else:nodes=d.xpath('//ul[@class="list-cmn-news"]/li/dl')
  for n in nodes:
   a=n.xpath('.//a[@href]')[0];date=n.xpath('.//div[@class="News_Date"]|./dt')[0]
   row={'title':clean(a.text_content()),'url':urljoin(m.SOURCE_URL,a.get('href')),'date':datetime.strptime(clean(date.text_content()),'%Y.%m.%d').strftime('%Y-%m-%d')}
   if row['url'] not in {r['url'] for r in expected}:expected.append(row)
  if code=='1363':expected.sort(key=lambda x:x['date'],reverse=True)
 expected=expected[:30]
 assert rows==expected,(code,'all-item source comparison failed',rows[:3],expected[:3])
 assert x.findtext('./channel/title')==m.CHANNEL_TITLE
 # Fetch representative article URLs and record official headings.
 samples=[]
 for row in rows[:2]:
  if row['url'].endswith('.pdf'):continue
  b2,final2=get(row['url']);d=html.fromstring(b2)
  samples.append({'url':final2,'title':clean(' '.join(d.xpath('//title/text()'))),'headings':[clean(n.text_content()) for n in d.xpath('//h1|//h2')][:6]})
 # Failure must leave existing RSS bytes untouched.
 before=Path(m.OUTPUT_FILE).read_bytes();fetch_orig=m.fetch
 def broken(url):return 'not valid source data'
 m.fetch=broken
 try:m.main();raise AssertionError('failure not raised')
 except (RuntimeError,ValueError,IndexError,json.JSONDecodeError):pass
 finally:m.fetch=fetch_orig
 assert Path(m.OUTPUT_FILE).read_bytes()==before
 return {'code':code,'count':len(rows),'items':rows,'source_url':m.SOURCE_URL,'data_url':m.DATA_URL,'source_sha256':hashlib.sha256(b).hexdigest(),'all_items_matched':True,'failure_preserves_existing':True,'samples':samples,'xml':rss.decode()}
def official():
 u='https://www.town.kawai.nara.jp/cgi-bin/feed.php';b,final=get(u);x=etree.fromstring(b)
 ns={'r':'http://purl.org/rss/1.0/','dc':'http://purl.org/dc/elements/1.1/'}
 rows=[{'title':clean(i.findtext('r:title',namespaces=ns)),'url':i.findtext('r:link',namespaces=ns),'date':datetime.fromisoformat(i.findtext('dc:date',namespaces=ns)).astimezone(JST).strftime('%Y-%m-%d')} for i in x.findall('r:item',ns)]
 data,_=get('https://www.town.kawai.nara.jp/index.update.json');data=json.loads(data)
 source={r['url']:(clean(r['page_name']),datetime.fromisoformat(r['publish_datetime']).astimezone(JST).strftime('%Y-%m-%d')) for r in data if not r['is_category_index'] and not r['is_keitai_page']}
 missing=[];diff=[]
 for row in rows:
  if row['url'] not in source:missing.append(row)
  elif source[row['url']]!=(row['title'],row['date']):diff.append({'rss':row,'source':source[row['url']]})
 assert rows and not diff,(missing,diff)
 assert not missing,missing
 return {'code':'1367','method':'公式RSS','feed_url':final,'count':len(rows),'items':rows,'all_items_matched':True,'xml':b.decode('utf-8-sig')}
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
 futures=[ex.submit(verify,s) for s in [('1363','asuka'),('1365','oji'),('1373','nosegawa'),('1374','totsukawa')]]+[ex.submit(official)]
 for f in futures:print('VRESULT '+json.dumps(f.result(),ensure_ascii=False))
