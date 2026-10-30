import json, hashlib, re
from urllib.request import Request,urlopen
from lxml import html
BASE='https://www.city.isa.kagoshima.jp'
PATHS=['/','/residency/','/politics/','/blog/category/info-residency/','/blog/info-prompt/77022/','/residency/sangyou/syoukougyou/','/residency/sangyou/nougyou/']
for round in range(2):
 for path in PATHS:
  u=BASE+path
  try:
   with urlopen(Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=35) as r:
    raw=r.read(); d=html.fromstring(raw)
    print(json.dumps({'round':round+1,'url':u,'status':r.status,'final':r.url,'bytes':len(raw),'title':d.xpath('//title/text()'),'h1':d.xpath('//h1//text()'),'rss':d.xpath('//link[contains(@type,"rss") or contains(@type,"atom")]/@href'),'links':[{'href':a.get('href'),'text':re.sub(r'\\s+',' ',a.text_content()).strip()} for a in d.xpath('//a[@href]') if a.text_content().strip()],'structure':raw.decode('utf-8','replace')[15000:40000] if path in ['/residency/','/blog/info-prompt/77022/'] else ''},ensure_ascii=False))
  except Exception as e: print(json.dumps({'round':round+1,'url':u,'error':repr(e)},ensure_ascii=False))
