import json,gzip,base64,urllib.request,xml.etree.ElementTree as ET,re,html,concurrent.futures
u="http://www.vill.chibu.lg.jp/feed.xml"
def get(u):
 with urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"}),timeout=30) as r:return r.read(),r.url
try:
 b,final=get(u);print("SOURCE "+json.dumps({"url":u,"final_url":final,"payload":base64.b64encode(gzip.compress(b)).decode()}))
 root=ET.fromstring(b);items=[n for n in root.iter() if n.tag.split("}")[-1]=="item"];print("FEEDCOUNT "+str(len(items)))
 def check(n):
  fields={x.tag.split("}")[-1]:x.text for x in n};link=fields.get("link");rb,ru=get(link);text=rb.decode("utf-8-sig");title=re.search(r"<title[^>]*>(.*?)</title>",text,re.S|re.I);plain=html.unescape(re.sub(r"<[^>]+>"," ",text));dates=re.findall(r"(?:更新|掲載|公開|作成)日?\\s*[：:]?\\s*(?:20[0-9]{2}[年月日/.-][0-9]{1,2}[年月日/.-][0-9]{1,2}日?)",plain);return {"feed":fields,"final_url":ru,"title":html.unescape(title.group(1)) if title else None,"dates":dates,"payload":base64.b64encode(gzip.compress(rb)).decode()}
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
  for row in ex.map(check,items[:30]):print("ARTICLE "+json.dumps(row,ensure_ascii=False))
except Exception as e:print("ERROR "+str(e))
