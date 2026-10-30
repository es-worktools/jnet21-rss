import json,re
from urllib.request import Request,urlopen
from lxml import html
BASE='https://www.city.isa.kagoshima.jp'
PATHS=['/residency/','/politics/','/blog/info-prompt/77022/','/blog/category/info-prompt/','/politics/agreement/','/politics/agreement/kouji/','/politics/agreement/keiyaku/']
for path in PATHS:
 try:
  with urlopen(Request(BASE+path,headers={'User-Agent':'Mozilla/5.0'}),timeout=30) as r:raw=r.read();d=html.fromstring(raw)
  meta={'url':BASE+path,'status':r.status,'final':r.url,'canon':d.xpath('//link[@rel="canonical"]/@href'),'rss':d.xpath('//link[contains(@type,"rss") or contains(@type,"atom")]/@href'),'ids':[x.get('id') for x in d.xpath('//*[@id]') if x.tag in ['div','article','main','section']],'times':d.xpath('//time/@datetime'),'news_ancestors':[html.tostring(a.getparent(),encoding='unicode')[:1500] for a in d.xpath('//a[contains(@href,"/blog/")]')][20:24]}
  for e in d.xpath('//head|//script|//style|//header|//nav|//footer|//aside'):e.drop_tree()
  meta['html']=html.tostring(d,encoding='unicode')
  print(json.dumps(meta,ensure_ascii=False),flush=True)
 except Exception as e:print(json.dumps({'url':BASE+path,'error':repr(e)}),flush=True)
