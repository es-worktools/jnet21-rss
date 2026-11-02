"""1837 Ibusuki: one normal request per new route; no evasion or retries."""
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

OUT = Path('diagnostics/ibusuki-vol6-20261102/results')
ROUTES = [
    ('official_mobile_company', 'official alternate HTML; latest index inferred from indexed pagination', '/main/fp/info/company/index.html'),
    ('official_mobile_collect', 'official alternate HTML discovered in official search result', '/main/fp/info/collect/'),
    ('official_bid_article', 'official individual bid schedule article discovered in search', '/main/shisei/nyusatsu/page013759.html'),
    ('robots', 'standard discovery path; existence unconfirmed', '/robots.txt'),
    ('root_sitemap', 'conventional candidate; existence unconfirmed', '/sitemap.xml'),
    ('main_sitemap', 'conventional candidate; existence unconfirmed', '/main/sitemap.xml'),
    ('atom_candidate', 'conventional candidate; existence unconfirmed', '/main/atom.xml'),
    ('rss_candidate', 'conventional candidate; existence unconfirmed', '/main/index.xml'),
]

class Page(HTMLParser):
    def __init__(self):
        super().__init__(); self.text=[]; self.title=[]; self.in_title=False; self.skip=0; self.links=[]
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag in ('script','style'): self.skip+=1
        if tag=='title': self.in_title=True
        if tag in ('a','link') and a.get('href'): self.links.append(a)
    def handle_endtag(self, tag):
        if tag in ('script','style'): self.skip=max(0,self.skip-1)
        if tag=='title': self.in_title=False
    def handle_data(self, data):
        if self.in_title: self.title.append(data)
        if not self.skip: self.text.append(data)

def get(label, evidence, path):
    url='https://www.city.ibusuki.lg.jp'+path
    rec={'label':label,'url':url,'candidate_evidence':evidence,'checked_at':datetime.now(timezone.utc).isoformat(),'attempts':1}
    raw=None
    try:
        with urlopen(Request(url,headers={'User-Agent':'JNet21-RSS-diagnostic/1.0 (1837 Ibusuki; single request)'}),timeout=18) as r:
            raw=r.read(2_000_001); rec.update(status=r.status,final_url=r.url,content_type=r.headers.get('Content-Type'))
    except HTTPError as e:
        raw=e.read(2_000_001); rec.update(status=e.code,final_url=e.url,content_type=e.headers.get('Content-Type'),error=str(e))
    except Exception as e:
        rec.update(status=None,error=repr(e))
    if raw is not None:
        rec.update(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),truncated=len(raw)>2_000_000)
        body=raw.decode('utf-8','replace'); p=Page(); p.feed(body)
        rec['title']=' '.join(p.title).strip(); rec['text']=' '.join(' '.join(p.text).split())[:16000]
        rec['links']=[dict(a,url=urljoin(url,a['href'])) for a in p.links][:250]
        rec['feed_links']=[a for a in rec['links'] if any(x in (a.get('type','')+' '+a.get('href','')).lower() for x in ('rss','atom'))]
        rec['body_file']=label+'.body'; (OUT/rec['body_file']).write_bytes(raw)
        rec['feed_xml']=bool(re.search(r'<(?:rss(?:\s|>)|(?:[\w-]+:)?feed(?:\s|>))',body[:5000]))
        rec['sitemap_xml']=bool(re.search(r'<(?:urlset|sitemapindex)(?:\s|>)',body[:5000]))
        rec['stop_notice']='サービス停止のお知らせ' in rec['title'] or 'サービス一時停止のお知らせ' in rec['text']
    print(json.dumps({k:rec.get(k) for k in ('label','url','status','title','stop_notice','feed_xml','sitemap_xml','error')},ensure_ascii=False),flush=True)
    return rec

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    results=[]
    for i, route in enumerate(ROUTES):
        if i: time.sleep(1)
        results.append(get(*route))
        (OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'execution.json').write_text(json.dumps({'municipality_id':'1837','name':'鹿児島県指宿市','requests':len(results),'retries':0,'production_rss_changes':False,'notes':'RSS/sitemap conventional paths are unconfirmed candidates. HTTP503 does not prove nonexistence.'},ensure_ascii=False,indent=2),encoding='utf-8')
