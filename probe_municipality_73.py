import urllib.request,json,zlib,base64,concurrent.futures
URLS={'1470-top':'https://www.vill.shinjo.okayama.jp/','1470-news':'https://www.vill.shinjo.okayama.jp/index.php?id=63','1470-index':'https://www.vill.shinjo.okayama.jp/index.php?id=1'}
def probe(kv):
 k,u=kv
 try:
  r=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=45);b=r.read()
  return {'id':k,'url':r.url,'bytes':len(b),'zlib64':base64.b64encode(zlib.compress(b)).decode()}
 except Exception as e:return {'id':k,'error':str(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
 for d in ex.map(probe,URLS.items()): print('PROBE73 '+json.dumps(d),flush=True)
