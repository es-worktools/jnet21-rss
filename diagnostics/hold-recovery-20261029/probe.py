import json,hashlib,time,os,re
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from urllib.parse import urljoin,urlparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from lxml import html
CONFIG='diagnostics/hold-recovery-20261029/urls.json'
OUT=Path('diagnostics/hold-recovery-20261029/results');OUT.mkdir(parents=True,exist_ok=True)
def norm(x):return ' '.join(x.split())
def get(url):
 rec={'url':url,'checked_at':datetime.now(timezone.utc).isoformat()}
 try:
  with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=25) as r:
   data=r.read();rec.update(status=r.status,final_url=r.url,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
  
  if url.endswith('.json'):
   rec['json_data']=json.loads(data);rec['file']=hashlib.sha256(url.encode()).hexdigest()[:12]+'.json';(OUT/rec['file']).write_bytes(data);return rec
  d=html.fromstring(data);main=d.xpath('//*[@id="contents" or @id="main" or @id="mainContent" or @id="content"]')
  root=main[0] if main else d
  rec['h1']=[norm(x.text_content()) for x in d.xpath('//h1')]
  rec['rss']=[dict(x.attrib) for x in d.xpath('//link[contains(@type,"rss") or contains(@type,"atom")]|//a[contains(translate(@href,"RSSATOM","rssatom"),"rss") or contains(translate(@href,"RSSATOM","rssatom"),"atom")]')]
  rec['text']=norm(root.text_content())[:18000]
  rec['links']=[{'title':norm(a.text_content()),'url':urljoin(url,a.get('href')),'parent':norm(a.getparent().text_content())[:350],'html':html.tostring(a.getparent(),encoding='unicode')[:1000]} for a in root.xpath('.//a[@href]') if norm(a.text_content())][:250]
  rec['scripts']=[urljoin(url,x) for x in d.xpath('//script/@src')]
  rec['file']=hashlib.sha256(url.encode()).hexdigest()[:12]+'.html';(OUT/rec['file']).write_bytes(data)
 except HTTPError as e:rec.update(status=e.code,error=str(e));rec['body']=e.read().decode('utf-8',errors='replace')[:300]
 except Exception as e:rec.update(status=None,error=repr(e))
 print(json.dumps({k:v for k,v in rec.items() if k in ['url','status','error','h1','rss','bytes']},ensure_ascii=False),flush=True)
 return rec
urls=json.load(open(CONFIG))
for round_no in range(1,3):
 with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(get,urls))
 (OUT/f'phase2-round{round_no}.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
 if round_no==1:time.sleep(12)
