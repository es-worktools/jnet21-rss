import json,concurrent.futures,time,gzip,base64
from urllib.request import Request,build_opener,HTTPCookieProcessor
from http.cookiejar import CookieJar
URLS={
 "1375-news": "https://www.vill.shimokitayama.nara.jp/oshirase/",
 "1376-news": "https://www.vill.kamikitayama.nara.jp/news_list.html",
 "1376-data": "https://www.vill.kamikitayama.nara.jp/index.update.json",
 "1384-news": "https://www.city.tanabe.lg.jp/news.html",
 "1384-data": "https://www.city.tanabe.lg.jp/index.update.json",
 "1386-news": "https://www.city.kinokawa.lg.jp/whatsnew.html",
 "1388-news": "https://www.town.kimino.wakayama.jp/news.html",
 "1388-data": "https://www.town.kimino.wakayama.jp/index.update.json"
}
def fetch(kv):
 code,url=kv
 for attempt in range(4):
  try:
   opener=build_opener(HTTPCookieProcessor(CookieJar()))
   with opener.open(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=40) as r:b=r.read();final=r.url
   return {'code':code,'url':final,'size':len(b),'payload':base64.b64encode(gzip.compress(b)).decode()}
  except Exception as e:
   if attempt==3:return {'code':code,'url':url,'error':str(e)}
   time.sleep(2**attempt)
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
 for r in pool.map(fetch,URLS.items()):print('SOURCE '+json.dumps(r))
