"""Read-only, bounded official endpoint probes; never generates or publishes RSS."""
import concurrent.futures, datetime, hashlib, json, os, pathlib, socket, subprocess, time
OUT=pathlib.Path(os.environ.get("PROBE_OUT","evidence"));OUT.mkdir(exist_ok=True,parents=True)
CASES=[
("baseline-v4","https://www.ehime-iinet.or.jp/information","-4","known URL; isolate connection stage"),
("baseline-v6","https://www.ehime-iinet.or.jp/information","-6","IPv6 availability; not content path"),
("http-www","http://www.ehime-iinet.or.jp/information","-4","scheme variation; existence not established"),
("https-apex","https://ehime-iinet.or.jp/information","-4","host variation; equivalence not established"),
("rss-root","https://www.ehime-iinet.or.jp/feed/","-4","WordPress convention candidate, not discovered official feed"),
("rss-information","https://www.ehime-iinet.or.jp/information/feed/","-4","archive feed candidate, unconfirmed"),
("rss-query","https://www.ehime-iinet.or.jp/?feed=rss2","-4","WordPress query candidate, unconfirmed"),
("api-root","https://www.ehime-iinet.or.jp/wp-json/wp/v2/posts?per_page=1","-4","WordPress REST candidate, unconfirmed"),
("api-wp","https://www.ehime-iinet.or.jp/wp/wp-json/wp/v2/posts?per_page=1","-4","wp installation inferred from public PDF path; candidate only"),
("robots","https://www.ehime-iinet.or.jp/robots.txt","-4","discover sitemap declarations"),
("sitemap","https://www.ehime-iinet.or.jp/sitemap.xml","-4","sitemap candidate, unconfirmed"),
("wp-sitemap","https://www.ehime-iinet.or.jp/wp-sitemap.xml","-4","WordPress sitemap candidate, unconfirmed"),
("static-known","https://www.ehime-iinet.or.jp/wp/wp-content/uploads/2026/03/1-01-youkou.pdf","-4","known indexed official PDF; static path control"),
]
dns={}
for host in ("www.ehime-iinet.or.jp","ehime-iinet.or.jp"):
 try: dns[host]=[{"family":a[0],"ip":a[4][0]} for a in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)]
 except Exception as e:dns[host]={"error":str(e)}
(OUT/"dns.json").write_text(json.dumps(dns,ensure_ascii=False,indent=2))
print("DNS_JSON "+json.dumps(dns),flush=True)
def probe(case):
 ident,url,family,reason=case
 start=datetime.datetime.now(datetime.timezone.utc).isoformat()
 body=OUT/(ident+".body");headers=OUT/(ident+".headers")
 cmd=["curl",family,"--silent","--show-error","--location","--max-redirs","2","--connect-timeout","6","--max-time","20","--max-filesize","2097152","--retry","0","--user-agent","Mozilla/5.0","--dump-header",str(headers),"--output",str(body),"--write-out","%{json}",url]
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=24)
 try:m=json.loads(p.stdout)
 except Exception:m={"write_out":p.stdout}
 keep=["http_code","remote_ip","remote_port","local_ip","url_effective","num_redirects","size_download","time_namelookup","time_connect","time_appconnect","time_starttransfer","time_total","exitcode","errormsg","content_type"]
 result={"id":ident,"url":url,"family":family,"reason":reason,"observed_at":start,"returncode":p.returncode,"stderr":p.stderr,"metrics":{k:m.get(k) for k in keep},"sha256":hashlib.sha256(body.read_bytes()).hexdigest() if body.exists() else None}
 (OUT/(ident+".json")).write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print("PROBE_JSON "+json.dumps(result,ensure_ascii=False),flush=True)
 return result
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(probe,CASES))
(OUT/"results.json").write_text(json.dumps({"dns":dns,"results":results},ensure_ascii=False,indent=2))
print("SUMMARY_JSON "+json.dumps({"cases":len(results),"http_success":sum(200<=r["metrics"].get("http_code",0)<300 for r in results),"production_write":False}),flush=True)
