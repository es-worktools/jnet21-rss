import json,concurrent.futures,time,gzip,base64
from urllib.request import Request,build_opener,HTTPCookieProcessor
from http.cookiejar import CookieJar
URLS={
 "1390": "https://www.town.kudoyama.lg.jp/",
 "1391": "https://www.town.koya.wakayama.jp/",
 "1393": "https://www.town.hirogawa.wakayama.jp/",
 "1394": "https://www.town.aridagawa.lg.jp/",
 "1399": "https://www.town.minabe.lg.jp/"
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
