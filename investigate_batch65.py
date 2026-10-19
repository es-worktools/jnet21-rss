import json, re, concurrent.futures
from urllib.request import Request, urlopen
from urllib.parse import urljoin
from lxml import html, etree

URLS = {
 '1363': 'https://www.asukamura.jp/',
 '1365': 'https://www.town.oji.nara.jp/',
 '1367': 'https://www.town.kawai.nara.jp/',
 '1373': 'https://www.vill.nosegawa.nara.jp/news_list.html',
 '1374': 'https://www.vill.totsukawa.lg.jp/',
 '1365-rss': 'https://www.town.oji.nara.jp/cgi-bin/feed.php?new1=1&type=rss_2.0',
 '1367-rss': 'http://www.town.kawai.nara.jp/cgi-bin/feed.php',
}
def fetch(kv):
 k,u=kv
 try:
  with urlopen(Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=45) as r:
   b=r.read(); final=r.url
  s=b.decode('utf-8-sig',errors='replace'); d=html.fromstring(s)
  info={'id':k,'url':final,'size':len(b),'rss':[[a.get('href'),a.text_content().strip()] for a in d.xpath('//a[@href]|//link[@href]') if re.search('rss|atom|feed',a.get('href','')+' '+a.text_content(),re.I)],'scripts':d.xpath('//script[@src]/@src')}
  if '-rss' in k:
   info['raw']=s[:6000]
  else:
   info['news_links']=[[urljoin(final,a.get('href')),a.text_content().strip()] for a in d.xpath('//a[@href]') if re.search('一覧|しごと|新着|お知らせ',a.text_content())][:35]
   nodes=d.xpath('//*[text()[re:test(., "2026[年./-]", "i")]]',namespaces={'re':'http://exslt.org/regular-expressions'})
   info['snippets']=[etree.tostring(n.getparent(),encoding='unicode')[:4500] for n in nodes[:5]]
   info['inline_scripts']=[x.text for x in d.xpath('//script[not(@src)]') if x.text and re.search('json|news|ajax|update',x.text,re.I)]
  return info
 except Exception as e:return {'id':k,'error':str(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
 for result in ex.map(fetch,URLS.items()): print('RESULT '+json.dumps(result,ensure_ascii=False))
