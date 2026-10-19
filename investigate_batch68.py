import json,concurrent.futures,time,gzip,base64
from urllib.request import Request,build_opener,HTTPCookieProcessor
from http.cookiejar import CookieJar
URLS={
 "1400-news": "https://www.town.hidakagawa.lg.jp/whatsnew.html",
 "1402-news": "http://www.town.kamitonda.lg.jp/news_list.html",
 "1403-news": "https://www.town.susami.lg.jp/whatsnew.html",
 "1405-news": "https://www.town.taiji.wakayama.jp/whatsnew.html",
 "1401-data": "https://www.town.shirahama.wakayama.jp/index.update.json"
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
