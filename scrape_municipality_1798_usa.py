"""Official public news JSON plus complete business category trees.
No private endpoints, authentication, proxying, or access-control bypasses.
"""
import json,re,time,sys,hashlib
from datetime import datetime,timedelta,timezone
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from urllib.parse import urlparse,urlunparse
from pathlib import Path
from email.utils import format_datetime
from xml.etree.ElementTree import Element,SubElement,ElementTree

CONFIG = {'host': 'www.city.usa.oita.jp', 'title': '1798_【GH】大分県宇佐市 新着情報', 'link': 'https://www.city.usa.oita.jp/', 'output': 'municipality-1798-usa.xml', 'sources': ['https://www.city.usa.oita.jp/index.update.json', 'https://www.city.usa.oita.jp/sougo/index.update.json', 'https://www.city.usa.oita.jp/sougo/jigyosha/index.tree.json', 'https://www.city.usa.oita.jp/sougo/3/index.tree.json']}
JST=timezone(timedelta(hours=9))
MAX_ITEMS=100

def normalize(s):return re.sub(r'\s+',' ',s or '').strip()
def safe_url(url):
    p=urlparse(url)
    if p.scheme not in ('http','https') or p.netloc!=CONFIG['host'] or p.username or p.password or p.port not in (None,80,443):
        raise RuntimeError('Unexpected official URL: '+url)
    return urlunparse(('https',p.netloc,p.path,p.params,p.query,''))

def fetch_json(url, evidence):
    url=safe_url(url)
    if len(evidence)>=80:raise RuntimeError('Category tree exceeded reviewed request bound')
    for attempt in range(2):
        try:
            with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=30) as r:
                safe_url(r.url);raw=r.read()
            data=json.loads(raw)
            if not isinstance(data,list):raise RuntimeError('Official JSON is not an array')
            evidence.append({'url':url,'count':len(data),'sha256':hashlib.sha256(raw).hexdigest()})
            return data
        except HTTPError as error:
            if error.code in (401,403,404,429) or attempt==1:raise
            time.sleep(2)
        except Exception:
            if attempt==1:raise
            time.sleep(2)

def collect():
    evidence=[];items={};visited=set();externals=[]
    def article(n,source):
        title=normalize(n.get('page_name'))
        if not title or not n.get('url') or not n.get('publish_datetime'):raise RuntimeError('Missing official title URL or date')
        url=safe_url(n['url'])
        date=datetime.fromisoformat(n['publish_datetime'])
        if date.tzinfo is None:raise RuntimeError('Official date lacks time zone')
        if date>datetime.now(JST):return
        row={'title':title,'url':url,'date':date.isoformat(),'source':source,'page_no':n.get('page_no')}
        if url not in items or date>datetime.fromisoformat(items[url]['date']):items[url]=row
    def nodes(data,source,depth=0):
        if depth>12:raise RuntimeError('Category tree depth changed')
        for n in data:
            if not isinstance(n,dict) or 'is_category_index' not in n:raise RuntimeError('Official JSON schema changed')
            if n.get('is_keitai_page'):continue
            if n['is_category_index']:
                children=n.get('child_pages')
                if children is not None:nodes(children,source,depth+1)
                elif n.get('child_pages_count',0)>0:
                    url=safe_url(n['url'])
                    if not url.endswith('.html'):raise RuntimeError('Unexpected category URL')
                    tree=url[:-5]+'.tree.json'
                    if tree not in visited:
                        visited.add(tree);nodes(fetch_json(tree,evidence),tree,depth+1)
            else:article(n,source)
    for source in CONFIG['sources']:
        visited.add(source);data=fetch_json(source,evidence)
        if not data:raise RuntimeError('Official source unexpectedly empty; RSS preserved: '+source)
        nodes(data,source)
    if len(items)<10:raise RuntimeError('Too few official articles; existing RSS preserved')
    allrows=sorted(items.values(),key=lambda r:(r['date'],r['url']),reverse=True)
    return allrows[:MAX_ITEMS],{'checked_at':datetime.now(JST).isoformat(),'sources':evidence,'all_articles':allrows,'output_articles':allrows[:MAX_ITEMS]}

def main():
    rows,evidence=collect()
    rss=Element('rss',version='2.0');ch=SubElement(rss,'channel')
    SubElement(ch,'title').text=CONFIG['title'];SubElement(ch,'link').text=CONFIG['link'];SubElement(ch,'description').text=CONFIG['title']+'（公式新着・事業者向けカテゴリを統合）'
    for row in rows:
        item=SubElement(ch,'item');SubElement(item,'title').text=row['title'];SubElement(item,'link').text=row['url'];SubElement(item,'guid',isPermaLink='true').text=row['url'];SubElement(item,'pubDate').text=format_datetime(datetime.fromisoformat(row['date']))
    out=Path(CONFIG['output']);temp=Path(str(out)+'.tmp');ElementTree(rss).write(temp,encoding='utf-8',xml_declaration=True);temp.replace(out)
    if '--diagnostic-out' in sys.argv:
        p=Path(sys.argv[sys.argv.index('--diagnostic-out')+1]);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
    print(json.dumps({'output':str(out),'items':len(rows),'all_articles':len(evidence['all_articles']),'requests':len(evidence['sources'])},ensure_ascii=False))

if __name__=='__main__':main()
