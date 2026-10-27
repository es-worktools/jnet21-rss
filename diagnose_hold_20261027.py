"""Bounded, read-only source comparison; never writes published RSS."""
import hashlib, json, re, sys
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urljoin
from lxml import html, etree

OUT=Path('hold-diagnostics');OUT.mkdir(exist_ok=True)
SOURCES=[
 ('0818-list','https://www.vill.sekikawa.niigata.jp/news/index.html'),
 ('0818-108','https://www.vill.sekikawa.niigata.jp/life/626/c7b0fac9d5c5/index.html'),
 ('0716-list','https://www.vill.miyake.tokyo.jp/news/'),
 ('0296-rss','https://www.village.ohira.miyagi.jp/cgi-bin/feed.php?siteNew=1&displayRange=90'),
 ('0296-top','https://www.village.ohira.miyagi.jp/index.html'),
 ('0296-update','https://www.village.ohira.miyagi.jp/index.update.json'),
 ('0296-list','https://www.village.ohira.miyagi.jp/newslist.html'),
]
def norm(s):return re.sub(r'\s+',' ',s or '').strip()
results=[]
for label,url in SOURCES:
 meta={'label':label,'url':url,'fetched_at':datetime.now(timezone.utc).isoformat(),'request_headers':{'User-Agent':'Mozilla/5.0'}}
 try:
  with urlopen(Request(url,headers=meta['request_headers']),timeout=30) as r:
   data=r.read();meta.update(status=r.status,final_url=r.url,headers=dict(r.headers))
 except HTTPError as e:
  data=e.read();meta.update(status=e.code,headers=dict(e.headers),error=str(e))
 except Exception as e:
  data=b'';meta['error']=repr(e)
 meta.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
 (OUT/(label+'.html')).write_bytes(data)
 if data and meta.get('status')==200:
  try:
   if label=='0296-update':
    source=json.loads(data);meta['items']=[{'title':x['page_name'],'date':x['publish_datetime'],'url':x['url']} for x in source]
   elif label.endswith('rss'):
    root=etree.fromstring(data);ns={'r':'http://purl.org/rss/1.0/','dc':'http://purl.org/dc/elements/1.1/'};meta['items']=[{'title':x.findtext('r:title',namespaces=ns),'date':x.findtext('dc:date',namespaces=ns),'url':x.findtext('r:link',namespaces=ns)} for x in root.findall('.//r:item',ns)]
   else:
    doc=html.fromstring(data);meta['h1']=[norm(x.text_content()) for x in doc.xpath('//h1')]
    if label=='0818-list':
     meta['items']=[{'title':norm(x.xpath('./div[@class="headline-link"]/a')[0].text_content()),'date':norm(x.xpath('./div[@class="headline-meta"]/span[@class="headline-date"]')[0].text_content()),'url':urljoin(url,x.xpath('./div[@class="headline-link"]/a/@href')[0])} for x in doc.xpath('//div[@class="headline-content"]')]
    elif label=='0818-108':
     meta['date_nodes']=[norm(x.text_content()) for x in doc.xpath('//*[contains(@class,"date") or contains(@class,"page-published") or self::time]')]
     meta['108_context']=[norm(x.text_content())[:600] for x in doc.xpath('//p|//h1|//h2|//h3') if '108号' in x.text_content()]
    elif label=='0716-list':
     meta['items']=[{'title':norm(x.xpath('following-sibling::*[1][self::dd]/a')[0].text_content()),'date':norm(x.text_content()),'url':urljoin(url,x.xpath('following-sibling::*[1][self::dd]/a/@href')[0])} for x in doc.xpath('//dt[span[contains(text(),"年")]]')]
    else:
     meta['dated_blocks']=[{'tag':x.tag,'class':x.get('class'),'id':x.get('id'),'text':norm(x.text_content())[:600],'links':[{'title':norm(a.text_content()),'url':urljoin(url,a.get('href',''))} for a in x.xpath('.//a[@href]')]} for x in doc.xpath('//li|//dd|//tr') if re.search(r'2026|令和8|令和８',x.text_content())]
     meta['feed_links']=[dict(x.attrib) for x in doc.xpath('//link[contains(@type,"rss") or contains(@type,"atom")]')]
  except Exception as e:meta['parse_error']=repr(e)
 (OUT/(label+'.json')).write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
 results.append(meta);print(json.dumps(meta,ensure_ascii=False))
(OUT/'summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
