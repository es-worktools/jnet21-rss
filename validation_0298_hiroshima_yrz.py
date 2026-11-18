"""Read-only 0298 proof of concept. Writes /tmp XML; never touches main feed."""
import hashlib, re, urllib.request, urllib.error
from datetime import datetime
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup
BASE = "https://www.yorozu-hiroshima.go.jp"
SECTIONS = [("/news/", "お知らせ"), ("/onestop/seminar/", "ワンストップ・セミナー"), ("/productivity/seminar/", "生産性向上・セミナー")]
def get(path):
    url = urljoin(BASE, path)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        if r.status != 200 or r.url.split("#")[0] != url or "html" not in r.headers.get("Content-Type", ""):
            raise ValueError("unexpected response: " + str(r.status) + " " + r.url)
        return BeautifulSoup(r.read(400000), "html.parser")
def linked(soup, section):
    values = {}
    for a in soup.find_all("a", href=True):
        link = urljoin(BASE, a["href"])
        if not link.startswith(BASE + section): continue
        tail = link[len(BASE + section):].strip("/")
        if not tail or "/" in tail or tail.startswith("page") or "?" in tail: continue
        label = a.get_text(" ", strip=True)
        if len(label) < 8: continue
        values[link] = label
    return values
def fetch_rows(section, label):
    found = {}
    for page in (1,2):
        path = section if page == 1 else section + "page/2/"
        try: soup=get(path)
        except urllib.error.HTTPError as e:
            if page == 2 and e.code == 404: continue
            raise
        rows=linked(soup, section)
        if not rows: raise ValueError("no records in " + path)
        print("LIST_OK",path,"links",len(rows),flush=True)
        found.update(rows)
    return found
def item_from_link(link, section, label):
    soup=get(link)
    h1=soup.find("h1")
    if not h1 or not h1.get_text(" ",strip=True): raise ValueError("missing h1: "+link)
    title=h1.get_text(" ",strip=True)
    canonical=soup.find("link",rel="canonical")
    c = urljoin(BASE,canonical.get("href","")) if canonical else link
    if not c.startswith(BASE+"/"): raise ValueError("unsafe canonical "+c)
    out={"title":title,"link":c,"category":label}
    if section=="/news/":
        times=soup.find_all("time")
        candidates=[]
        for tm in times:
            d=tm.get_text(" ",strip=True)
            m=re.search(r"(20\d{2})年(\d{1,2})月(\d{1,2})日",d)
            if m:
                try: candidates.append(datetime(*map(int,m.groups())))
                except ValueError: pass
        if candidates and len(set(candidates))==1: out["pubdate"]=candidates[0].strftime("%a, %d %b %Y 00:00:00 +0900")
    out["guid"]="urn:hiroshima-yorozu:"+hashlib.sha256(c.encode("utf-8")).hexdigest()
    return out
def main():
    items=[]; visited={}
    for section,label in SECTIONS:
        rows=fetch_rows(section,label)
        print("SECTION",label,"unique_urls",len(rows),flush=True)
        successes=0
        for link in list(rows)[:25]:
            try: data=item_from_link(link,section,label)
            except Exception as e:
                print("ITEM_ERROR",link,type(e).__name__,str(e)[:100],flush=True)
                continue
            if data["guid"] not in visited:
                visited[data["guid"]]=data
                items.append(data); successes+=1
        print("SECTION_ITEMS",label,successes,flush=True)
    if len(items)<15: raise ValueError("too few valid items")
    rss=ET.Element("rss",{"version":"2.0"})
    ch=ET.SubElement(rss,"channel")
    for k,v in (("title","広島県よろず支援拠点（検証）"),("link",BASE),("description","公式お知らせ・セミナーの検証用RSS")): ET.SubElement(ch,k).text=v
    for p in items:
        i=ET.SubElement(ch,"item")
        for k in ("title","link","guid","category","pubdate"):
            if k in p: ET.SubElement(i,"pubDate" if k=="pubdate" else k).text=p[k]
    dest="/tmp/hiroshima-yorozu-validation.xml"
    ET.ElementTree(rss).write(dest,encoding="utf-8",xml_declaration=True)
    parsed=ET.parse(dest).getroot()
    check=parsed.findall("./channel/item")
    if len(check)!=len(items) or len({x.findtext("guid") for x in check})!=len(check): raise ValueError("RSS integrity error")
    print("VALIDATION_RSS",dest,"items",len(check),"with_pubdate",sum("pubdate" in i for i in items),flush=True)
    print("SAMPLE",[(x["category"],x["title"][:60],x["link"][-75:],bool(x.get("pubdate"))) for x in items[:9]],flush=True)
if __name__=="__main__": main()
