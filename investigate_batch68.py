import json,concurrent.futures,time,gzip,base64
from urllib.request import Request,build_opener,HTTPCookieProcessor
from http.cookiejar import CookieJar
URLS={
 "1400": "https://www.town.hidakagawa.lg.jp/",
 "1401": "https://www.town.shirahama.wakayama.jp/",
 "1402": "https://www.town.kamitonda.lg.jp/",
 "1403": "https://www.town.susami.lg.jp/",
 "1405": "https://www.town.taiji.wakayama.jp/"
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
