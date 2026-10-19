import json, re, concurrent.futures
from urllib.request import Request, urlopen
from urllib.parse import urljoin
from lxml import html, etree

URLS = {
 '1363': 'https://www.asukamura.jp/',
 '1365': 'https://www.town.oji.nara.jp/news.html',
 '1367': 'https://www.town.kawai.nara.jp/news_list.html',
 '1373': 'https://www.vill.nosegawa.nara.jp/news_list.html',
 '1374': 'https://www.vill.totsukawa.lg.jp/news/index.php',
 '1365-rss': 'https://www.town.oji.nara.jp/cgi-bin/feed.php?new1=1&type=rss_2.0',
 '1367-rss': 'http://www.town.kawai.nara.jp/cgi-bin/feed.php',
}
def fetch(kv):
 k,u=kv
 try:
  with urlopen(Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=45) as r:
   b=r.read(); final=r.url
  s=b.decode('utf-8-sig',errors='replace')
  if '-rss' in k:
   x=etree.fromstring(b)
   return {'id':k,'url':final,'size':len(b),'root':x.tag,'raw':s[:12000]}
  d=html.fromstring(s)
  info={'id':k,'url':final,'size':len(b),'rss':[[a.get('href'),a.text_content().strip()] for a in d.xpath('//a[@href]|//link[@href]') if re.search('rss|atom|feed',a.get('href','')+' '+a.text_content(),re.I)],'scripts':d.xpath('//script[@src]/@src')}
  if '-rss' in k:
   info['raw']=s[:6000]
  else:
   info['news_links']=[[urljoin(final,a.get('href')),a.text_content().strip()] for a in d.xpath('//a[@href]') if re.search('一覧|しごと|新着|お知らせ',a.text_content())][:35]
   nodes=d.xpath('//*[text()[re:test(., "2026[年./-]", "i")]]',namespaces={'re':'http://exslt.org/regular-expressions'})
   info['snippets']=[etree.tostring(n.getparent(),encoding='unicode')[:2000] for n in nodes[:3]]
   info['components']=[dict(n.attrib) for n in d.xpath('//*[@data-url]')]
   info['inline_scripts']=[x.text for x in d.xpath('//script[not(@src)]') if x.text and re.search('getJSON\([\'\"]|getTopics|topics_list',x.text,re.I)]
   if k=='1363':info['news_html']=''.join(etree.tostring(n,encoding='unicode') for n in d.xpath('//div[@class="News_Wrapp"]'))
   if k=='1374':info['news_html']=etree.tostring(d.xpath('//main')[0] if d.xpath('//main') else d.xpath('//body')[0],encoding='unicode')[:20000]
   data_urls=set(urljoin(final,n.get('data-url')) for n in d.xpath('//*[@data-url]') if 'update.json' in n.get('data-url',''))
   for script in info['inline_scripts']:
    for data_url in re.findall(r'getJSON\([\'\"]([^\'\"]+)',script):data_urls.add(urljoin(final,data_url))
   info['data']=[]
   for data_url in sorted(data_urls):
    if 'update.json' not in data_url:continue
    with urlopen(Request(data_url,headers={'User-Agent':'Mozilla/5.0'}),timeout=45) as q:data=json.load(q)
    info['data'].append({'url':data_url,'rows':data[:80]})
  return info
 except Exception as e:return {'id':k,'error':str(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
 for result in ex.map(fetch,URLS.items()): print('RESULT '+json.dumps(result,ensure_ascii=False))
