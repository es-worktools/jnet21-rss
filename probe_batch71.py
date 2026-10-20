import json,gzip,base64,urllib.request
for u in ["http://www.vill.chibu.lg.jp/","https://vill.chibu.lg.jp/"]:
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"}),timeout=30) as r:b=r.read();status=r.status;final=r.url
  print("SOURCE "+json.dumps({"url":u,"final_url":final,"status":status,"payload":base64.b64encode(gzip.compress(b)).decode()}))
 except Exception as e:print("SOURCE "+json.dumps({"url":u,"error":str(e)}))
