import json,concurrent.futures,time,gzip,base64
from urllib.request import Request,build_opener,HTTPCookieProcessor
from http.cookiejar import CookieJar
URLS={
 "1390-news": "https://www.town.kudoyama.lg.jp/whatsnew.html",
 "1391-news": "https://www.town.koya.wakayama.jp/update.html",
 "1394-life": "https://www.town.aridagawa.lg.jp/top/index.html",
 "1399-news": "https://www.town.minabe.lg.jp/whatsnew.html"
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
