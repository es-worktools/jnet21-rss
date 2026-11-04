import copy, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET
import requests
import scrape_noastec as s
import stage_noastec as stage

def baseline(c,n=None):
 r=ET.Element('rss',version='2.0');ch=ET.SubElement(r,'channel')
 for k,v in [('title',c['name']),('link',c['url']),('description',c['name'])]:ET.SubElement(ch,k).text=v
 for i in range(c['minimum'] if n is None else n):
  it=ET.SubElement(ch,'item');u=c['url']+f'/post_{1000+i}.html'
  for k,v in [('title',f'記事{i}'),('link',u),('guid',u)]:ET.SubElement(it,k).text=v
  if i==0:ET.SubElement(it,'pubDate').text='Tue, 20 Oct 2026 00:00:00 GMT'
 return ET.tostring(r,encoding='utf-8',xml_declaration=True)

def html(c,n=None,start=1000):
 return ('<h1>'+c['label']+'</h1>'+''.join(f'<a href="{c["url"]}/post_{start+i}.html">記事{i}</a>' for i in range(c['minimum'] if n is None else n))).encode()

def response(c,body=None,status=200,media='text/html',url=None):
 r=requests.Response();r.status_code=status;r.url=url or c['url'];r.headers['Content-Type']=media;r._content=html(c) if body is None else body;return r

class SafetyTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.d=Path(self.temp.name);self.c=s.FEEDS[0];self.p=self.d/self.c['output']
  for c in s.FEEDS:(self.d/c['output']).write_bytes(baseline(c))
  self.before=self.p.read_bytes()
 def tearDown(self):self.temp.cleanup()
 def reject(self,r,code):
  with self.assertRaises(s.GuardError) as e:s.process_feed(self.c,self.d,lambda *a,**kw:r)
  self.assertEqual(e.exception.code,code);self.assertEqual(self.p.read_bytes(),self.before);self.assertFalse(list(self.d.glob('.*.tmp')))
 def good(self,n=None,start=1000):return s.process_feed(self.c,self.d,lambda *a,**kw:response(self.c,html(self.c,n,start)))
 def test_403(self):self.reject(response(self.c,status=403),'HTTP_ERROR')
 def test_500(self):self.reject(response(self.c,status=500),'HTTP_ERROR')
 def test_302(self):self.reject(response(self.c,status=302),'HTTP_ERROR')
 def test_204(self):self.reject(response(self.c,status=204),'HTTP_ERROR')
 def test_wrong_url(self):self.reject(response(self.c,url='https://www.noastec.jp/'),'CONTENT_ERROR')
 def test_wrong_media(self):self.reject(response(self.c,media='application/json'),'CONTENT_ERROR')
 def test_200_error_page(self):self.reject(response(self.c,b'<html>Access denied</html>'),'CONTENT_ERROR')
 def test_zero(self):self.reject(response(self.c,'セミナー・イベント'.encode()),'ZERO_ITEMS')
 def test_partial(self):self.reject(response(self.c,html(self.c,9)),'PARTIAL_ITEMS')
 def test_empty_title(self):self.reject(response(self.c,html(self.c).replace('記事0'.encode(),b'')),'PARSE_ERROR')
 def test_changed_url(self):self.reject(response(self.c,html(self.c).replace(b'post_1000.html',b'article_1000.html')),'PARSE_ERROR')
 def test_external_url(self):self.reject(response(self.c,html(self.c).replace(b'https://www.noastec.jp',b'https://example.org',1)),'PARSE_ERROR')
 def test_disjoint(self):self.reject(response(self.c,html(self.c,start=2000)),'DISJOINT_ITEMS')
 def test_conflicting_title(self):self.reject(response(self.c,html(self.c)+f'<a href="{self.c["url"]}/post_1000.html">別のタイトル</a>'.encode()),'PARSE_ERROR')
 def test_duplicate_image(self):
  r=s.process_feed(self.c,self.d,lambda *a,**kw:response(self.c,html(self.c)+f'<a href="{self.c["url"]}/post_1000.html"><img src="x"></a>'.encode()));self.assertEqual(r['source_items'],10)
 def test_empty_baseline(self):
  self.p.write_bytes(baseline(self.c,0))
  with self.assertRaises(s.GuardError):s.read_baseline(self.p,self.c)
 def test_missing_baseline(self):
  self.p.unlink()
  with self.assertRaises(s.GuardError):s.process_feed(self.c,self.d,lambda *a,**kw:self.fail('network called'))
  self.assertFalse(self.p.exists())
 def test_broken_baseline(self):
  self.p.write_bytes(b'<rss')
  with self.assertRaises(s.GuardError):s.read_baseline(self.p,self.c)
 def test_duplicate_baseline(self):
  r=ET.fromstring(self.before);ch=r.find('channel');ch.append(copy.deepcopy(ch.find('item')));self.p.write_bytes(ET.tostring(r))
  with self.assertRaises(s.GuardError):s.read_baseline(self.p,self.c)
 def test_invalid_guid(self):
  self.p.write_bytes(self.before.replace(b'<guid>https:',b'<guid>http:',1))
  with self.assertRaises(s.GuardError):s.read_baseline(self.p,self.c)
 def test_preserve_old_and_dates(self):
  r=self.good(11);old=ET.fromstring(self.before).findall('./channel/item');out=ET.fromstring(self.p.read_bytes()).findall('./channel/item')
  for a,b in zip(old,out):self.assertEqual(ET.tostring(a),ET.tostring(b))
  self.assertEqual(r['rss_items'],11);self.assertIsNone(out[-1].find('pubDate'))
 def test_rolling_list(self):
  r=self.good(start=1001);self.assertEqual(r['rss_items'],11);self.assertEqual(r['source_items'],10);self.assertIn(b'post_1000.html',self.p.read_bytes())
 def test_count_regression(self):
  self.good(11);before=self.p.read_bytes()
  with self.assertRaises(s.GuardError):self.good(10)
  self.assertEqual(before,self.p.read_bytes())
 def test_idempotent(self):
  self.good();before=self.p.read_bytes();self.assertEqual(self.good()['status'],'unchanged');self.assertEqual(before,self.p.read_bytes())
 def test_fsync_error(self):
  with patch.object(s.os,'fsync',side_effect=OSError('disk')):
   with self.assertRaises(OSError):self.good()
  self.assertEqual(self.before,self.p.read_bytes());self.assertFalse(list(self.d.glob('.*.tmp')))
 def test_replace_error(self):
  with patch.object(s.os,'replace',side_effect=OSError('replace')):
   with self.assertRaises(OSError):self.good()
  self.assertEqual(self.before,self.p.read_bytes());self.assertFalse(list(self.d.glob('.*.tmp')))
 def test_temp_validation_error(self):
  with self.assertRaises(ValueError):s.atomic_write(self.p,b'bad',lambda b:(_ for _ in ()).throw(ValueError('bad')))
  self.assertEqual(self.before,self.p.read_bytes());self.assertFalse(list(self.d.glob('.*.tmp')))
 def mixed(self,transport=False):
  def get(url,**kw):
   c=next(c for c in s.FEEDS if c['url']==url)
   if c==s.FEEDS[0] and transport:raise requests.Timeout('timeout')
   return response(c,status=403 if c==s.FEEDS[0] else 200)
  return s.run(self.d,get)
 def test_isolation(self):
  result=self.mixed();self.assertEqual([r['status'] for r in result['results']],['failed','updated','updated']);self.assertEqual(self.before,self.p.read_bytes())
  (self.d/'noastec-status.json').write_text(json.dumps(result));self.assertEqual(set(stage.verified_files(self.d)),{c['output'] for c in s.FEEDS[1:]})
 def test_transport_isolation(self):
  r=self.mixed(True)['results'];self.assertEqual(r[0]['code'],'TRANSPORT_ERROR');self.assertTrue(all(x['status']=='updated' for x in r[1:]))
 def test_receipt_tampering(self):
  result=s.run(self.d,lambda url,**kw:response(next(c for c in s.FEEDS if c['url']==url)));(self.d/'noastec-status.json').write_text(json.dumps(result));self.p.write_bytes(b'tampered')
  with self.assertRaises(ValueError):stage.verified_files(self.d)
 def test_incomplete_receipt(self):
  (self.d/'noastec-status.json').write_text('{"schema":1,"complete":false,"results":[]}')
  with self.assertRaises(ValueError):stage.verified_files(self.d)
 def test_missing_receipt(self):
  with self.assertRaises(FileNotFoundError):stage.verified_files(self.d)
 def test_cli_failure(self):
  with patch('sys.argv',['script','--directory',str(self.d),'--summary',str(self.d/'status.json')]),patch.object(s,'run',return_value={'schema':1,'complete':True,'results':[{'status':'failed'}]}):self.assertEqual(s.main(),1)
  self.assertTrue((self.d/'status.json').exists())

if __name__=='__main__':unittest.main()
