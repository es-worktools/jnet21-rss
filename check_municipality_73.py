import json,re,hashlib,importlib.util,concurrent.futures,os
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urljoin
from datetime import datetime,timedelta,timezone
from email.utils import parsedate_to_datetime
from lxml import html,etree

ROOT=Path.cwd()
OUT=ROOT/'outputs/vol17'
JST=timezone(timedelta(hours=9))
SPECS=[('1470','shinjo')]
def clean(s):return re.sub(r'\s+',' ',s.replace('\u00ad','')).strip()
def get(u):
    with urlopen(Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=50) as r:return r.read(),r.url
def parse_rss(b):
    x=etree.fromstring(b)
    if x.tag.endswith('RDF'):
        ns={'r':'http://purl.org/rss/1.0/','d':'http://purl.org/dc/elements/1.1/'}
        return [{'title':clean(i.findtext('r:title',namespaces=ns)),'url':i.findtext('r:link',namespaces=ns),'time':datetime.fromisoformat(i.findtext('d:date',namespaces=ns)).isoformat()} for i in x.findall('r:item',ns)]
    return [{'title':clean(i.findtext('title')),'url':i.findtext('link'),'time':parsedate_to_datetime(i.findtext('pubDate')).astimezone(JST).isoformat()} for i in x.findall('./channel/item')]
def expected(code,m):
    sources=[];rows=[]
    def load(u):
        b,f=get(u);sources.append({'url':f,'sha256':hashlib.sha256(b).hexdigest()});return b
    if code=='1464':
        d=json.loads(load(m.DATA_URL));cutoff=datetime.now(JST)-timedelta(days=90)
        for a in d:
            if a['is_category_index'] or a['is_keitai_page']:continue
            dt=datetime.fromisoformat(a['publish_datetime'])
            if dt>=cutoff:rows.append({'title':clean(a['page_name']),'url':a['url'],'time':dt.isoformat()})
        rows=sorted(rows,key=lambda r:r['time'],reverse=True)
    elif code=='1466':
        d=html.fromstring(load(m.SOURCE_URL));seen=set()
        for panel in d.xpath('//*[@id="tab-info" or @id="tab-event" or @id="tab-boshu"]'):
            for day in panel.xpath('.//span[@class="date"]'):
                li=day.getparent();a=li.xpath('.//a[@href]')[0];title=clean(a.text_content());dt=datetime(*map(int,re.findall(r'\d+',day.text_content())),tzinfo=JST);key=(title,dt)
                if key in seen:continue
                seen.add(key);rows.append({'title':title,'url':urljoin(m.SOURCE_URL,a.get('href')),'time':dt.isoformat()})
        rows=sorted(rows,key=lambda r:r['time'],reverse=True)
    elif code=='1469':
        u=m.SOURCE_URL
        for p in range(3):
            d=html.fromstring(load(u))
            for dd in d.xpath('//div[@id="newsContents"]/dl/dd'):
                dt=dd.getprevious();digits=re.search(r'(20\d{2})年(\d+)月(\d+)日',dt.text_content());day=datetime(*map(int,digits.groups()),tzinfo=JST);a=dd.xpath('a[@href]')[0];rows.append({'title':clean(a.text_content()),'url':urljoin(u,a.get('href')),'time':day.isoformat()})
            links=d.xpath('//a[@href][normalize-space(.)=">"]/@href')
            if len(rows)>=30 or not links:break
            u=urljoin(u,links[0])
    else:
        d=html.fromstring(load(m.SOURCE_URL))
        for day in d.xpath('//li[span[@class="date"] and p/a]/span[@class="date"]'):
            a=day.getparent().xpath('p/a')[0];dt=datetime(*map(int,re.findall(r'\d+',day.text_content())),tzinfo=JST);rows.append({'title':clean(a.text_content()),'url':urljoin(m.SOURCE_URL,a.get('href')),'time':dt.isoformat()})
    unique={}
    for r in rows:unique.setdefault(r['url'],r)
    return list(unique.values())[:30],sources
def verify(spec):
    code,slug=spec
    ms=importlib.util.spec_from_file_location('m'+code,ROOT/f'scrape_municipality_{code}_{slug}.py');m=importlib.util.module_from_spec(ms);ms.loader.exec_module(m)
    m.main();b=Path(m.OUTPUT_FILE).read_bytes();rows=parse_rss(b);exp,sources=expected(code,m)
    assert rows and rows==exp,(code,'source mismatch',rows,exp)
    before=b;saved=m.fetch;m.fetch=lambda *a:'invalid source'
    try:m.main();raise AssertionError('invalid source accepted')
    except (ValueError,RuntimeError,IndexError,KeyError):pass
    finally:m.fetch=saved
    assert Path(m.OUTPUT_FILE).read_bytes()==before
    result={'code':code,'slug':slug,'title':m.CHANNEL_TITLE,'source_url':m.SOURCE_URL,'feed_url':'https://es-worktools.github.io/jnet21-rss/'+m.OUTPUT_FILE,'count':len(rows),'all_items_matched':True,'failure_preserves_existing':True,'source_checks':sources,'items':rows}
    (OUT/f'{code}-local.xml').write_bytes(b)
    (OUT/f'{code}-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print('VERIFY73 '+json.dumps(dict(result, xml=b.decode()),ensure_ascii=False),flush=True)
    return result
if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:results=list(ex.map(verify,SPECS))
    (OUT/'batch73-dry-run-verification.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
