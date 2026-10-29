import subprocess,json,time,shutil
from pathlib import Path
OUT=Path('diagnostics/hold-recovery-20261029/results');OUT.mkdir(exist_ok=True,parents=True)
specs=[('1798','usa'),('1779','taragi')];summary=[]
for round_no in (1,2):
 for num,slug in specs:
  script=f'scrape_municipality_{num}_{slug}.py';report=OUT/f'candidate-{num}-round{round_no}.json'
  r=subprocess.run(['python',script,'--diagnostic-out',str(report)],capture_output=True,text=True)
  print(num,round_no,r.returncode,r.stdout,r.stderr,flush=True)
  (OUT/f'candidate-{num}-round{round_no}.log').write_text(r.stdout+'\n'+r.stderr)
  summary.append({'number':num,'round':round_no,'returncode':r.returncode})
  if r.returncode==0:shutil.copyfile(f'municipality-{num}-{slug}.xml',OUT/f'candidate-{num}-round{round_no}.xml')
 if round_no==1:time.sleep(12)
for num,slug in specs:
 a=OUT/f'candidate-{num}-round1.json';b=OUT/f'candidate-{num}-round2.json'
 if a.exists() and b.exists():
  a=json.loads(a.read_text());b=json.loads(b.read_text());projection=lambda d:[(r['url'],r['title'],r['date']) for r in d['all_articles']]
  summary.append({'number':num,'all_stable':projection(a)==projection(b),'output_stable':a['output_articles']==b['output_articles'],'source_count':len(a['sources']),'all_count':len(a['all_articles']),'output_count':len(a['output_articles'])})
(OUT/'candidate-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False),flush=True)
