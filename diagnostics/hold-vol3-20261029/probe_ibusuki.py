"""One check of the previously failing route; no retries after HTTP503."""
import json, hashlib
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone
from pathlib import Path
from lxml import html

OUT=Path('diagnostics/hold-vol3-20261029/results')
OUT.mkdir(parents=True,exist_ok=True)
def get(url):
    rec={'url':url,'checked_at':datetime.now(timezone.utc).isoformat()}
    try:
        with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=30) as r:
            raw=r.read();rec.update(status=r.status,final_url=r.url,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
        doc=html.fromstring(raw)
        for e in doc.xpath('//script|//style'):e.drop_tree()
        rec['title']=doc.xpath('string(//title)')
        rec['h1']=[' '.join(e.text_content().split())for e in doc.xpath('//h1')]
        rec['text']=' '.join(doc.text_content().split())[:18000]
        rec['links']=[{'url':urljoin(url,a.get('href')),'title':' '.join(a.text_content().split())}for a in doc.xpath('//a[@href]')if a.text_content().strip()]
    except HTTPError as e:
        rec.update(status=e.code,error=str(e),body=e.read().decode('utf-8',errors='replace')[:5000])
    except Exception as e:rec.update(status=None,error=repr(e))
    print(json.dumps({k:v for k,v in rec.items()if k in ['url','status','h1','error']},ensure_ascii=False),flush=True)
    return rec

results=[]
listing=get('https://www.city.ibusuki.lg.jp/main/info/company/index.html');results.append(listing)
if listing.get('status')==200:
    urls=[]
    for a in listing['links']:
        u=a['url']
        if urlparse(u).netloc=='www.city.ibusuki.lg.jp' and '/main/' in u and u.endswith('.html') and u!=listing['url'] and any(w in a['title']for w in ['令和','補助','募集','入札','セミナー','支援']):
            if u not in urls:urls.append(u)
    for u in urls[:5]:results.append(get(u))
else:
    print('Previously failing company route remains unavailable; stop without retries.',flush=True)
(OUT/'ibusuki-single-check.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
