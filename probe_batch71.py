import json,gzip,base64,urllib.request
u="https://www.vill.chibu.lg.jp/"
try:
 with urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"}),timeout=40) as r:b=r.read();status=r.status
 print("SOURCE "+json.dumps({"url":u,"status":status,"payload":base64.b64encode(gzip.compress(b)).decode()}))
except Exception as e:print("SOURCE "+json.dumps({"url":u,"error":str(e)}))
