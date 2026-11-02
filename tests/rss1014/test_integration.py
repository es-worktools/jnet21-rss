import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import rss_1014 as m
FIX=ROOT/'experiments/rss-recovery-1014/fixtures'

class FakeFetcher:
    def __init__(self,fail=None,index=None,pdf=None):
        self.fail=fail; self.index=index; self.pdf=pdf
    def get(self,url):
        if url==self.fail:raise RuntimeError('simulated retrieval failure')
        names={m.OFFICIAL:'official-home.html',m.SIMPLE:'simple-index.html',m.WELFARE:'sonfuku.html'}
        if url==m.SIMPLE and self.index is not None:return self.index
        if url in names:return (FIX/names[url]).read_bytes()
        return self.pdf if self.pdf is not None else b'%PDF-1.7\n'+b'x'*200

class Integration(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.dir=Path(self.temp.name)
        self.output=self.dir/'feed.xml';self.history=self.dir/'history.json';self.config=self.dir/'config.json'
        self.old=(FIX/'baseline.xml').read_bytes();self.output.write_bytes(self.old)
        self.history.write_text(json.dumps(m.empty_state()))
        self.settings={'mode':'temporary','normal_review':{'approved':False,'articles':{}}}
        self.save_config()
    def save_config(self):self.config.write_text(json.dumps(self.settings))
    def run_engine(self,**kw):
        return m.run(self.config,self.output,self.history,self.dir/'evidence',fetcher=kw.pop('fetcher',FakeFetcher()),published=kw.pop('published',self.old),**kw)
    def state(self):return json.loads(self.history.read_text())
    def snapshot(self):return self.output.read_bytes(),self.history.read_bytes()
    def assert_failure_unchanged(self,**kw):
        before=self.snapshot()
        with self.assertRaises((RuntimeError,ValueError,KeyError)):self.run_engine(**kw)
        self.assertEqual(self.snapshot(),before)
    def test_current_rss_plus_history_and_repeat(self):
        r=self.run_engine()
        self.assertEqual((r['baseline_count'],r['output_count'],len(r['added'])),(17,19,2))
        self.assertEqual(len(self.state()['temporary']),3)
        snap=self.snapshot()
        self.run_engine()
        self.assertEqual(self.snapshot(),snap)
        for entry in self.state()['temporary'].values():
            self.assertEqual(len(entry['versions']),1)
            self.assertTrue(entry['versions'][0]['body_sha256'])
            self.assertTrue(entry['versions'][0]['pdfs'][0]['sha256'])
    def extra(self,data,guid=99999):
        root=ET.fromstring(data);item=copy.deepcopy(root.find('./channel/item'))
        item.find('guid').text=m.OFFICIAL+'news/detail/'+str(guid)
        item.find('link').text=item.findtext('guid');item.find('title').text='New current production article '+str(guid)
        root.find('channel').append(item)
        return ET.tostring(root)
    def test_live_public_article_not_in_local_fixture_is_retained(self):
        self.run_engine(published=self.extra(self.old))
        self.assertEqual(len(m.feed_items(self.output.read_bytes())[1]),20)
    def test_latest_checked_out_article_is_retained(self):
        self.output.write_bytes(self.extra(self.old))
        self.run_engine()
        self.assertEqual(len(m.feed_items(self.output.read_bytes())[1]),20)
    def test_persistent_archive_restores_missing_item(self):
        self.run_engine();state=self.state()
        # Simulate externally prepared but hash-consistent current feed losing an old item.
        root=ET.fromstring(self.output.read_bytes());root.find('channel').remove(root.findall('./channel/item')[-1])
        data=ET.tostring(root);self.output.write_bytes(data);state['rss_sha256']=m.digest(data)
        self.history.write_text(json.dumps(state))
        self.run_engine(published=data)
        self.assertEqual(len(m.feed_items(self.output.read_bytes())[1]),19)
    def test_all_existing_guid_title_and_dates_are_exact(self):
        self.run_engine();_,old=m.feed_items(self.old);_,new=m.feed_items(self.output.read_bytes())
        for guid,item in old.items():
            self.assertIn(guid,new)
            for field in ['title','pubDate']:self.assertEqual(item.findtext(field),new[guid].findtext(field))
    def test_no_truncation_above_thirty(self):
        data=self.old
        for i in range(20):data=self.extra(data,i+99000)
        self.output.write_bytes(data);self.run_engine(published=data)
        self.assertEqual(len(m.feed_items(self.output.read_bytes())[1]),39)
    def test_fetch_failure_all_stages_preserves_pair(self):
        for url in [m.OFFICIAL,m.SIMPLE,m.WELFARE,m.SIMPLE.rsplit('/',1)[0]+'/20261115akifes01.pdf']:
            self.assert_failure_unchanged(fetcher=FakeFetcher(fail=url))
    def test_bad_pdf_and_index_preserve_pair(self):
        self.assert_failure_unchanged(fetcher=FakeFetcher(pdf=b'not a pdf'))
        self.assert_failure_unchanged(fetcher=FakeFetcher(index=b'<html>maintenance</html>'))
    def test_public_fetch_failure_preserves_pair(self):
        before=self.snapshot()
        with patch.object(m,'public_rss',side_effect=RuntimeError('failed')):
            with self.assertRaises(RuntimeError):m.run(self.config,self.output,self.history,self.dir/'evidence',fetcher=FakeFetcher())
        self.assertEqual(self.snapshot(),before)
    def test_public_local_date_conflict_stops(self):
        root=ET.fromstring(self.old);root.find('./channel/item/pubDate').text='Sun, 01 Nov 2026 00:00:00 +0900'
        self.assert_failure_unchanged(published=ET.tostring(root))
    def test_bad_state_or_mismatched_hash_stops(self):
        self.run_engine();self.output.write_bytes(self.old)
        self.assert_failure_unchanged()
    def test_reused_url_date_or_title_stops_even_with_history(self):
        self.run_engine()
        for b in [(FIX/'simple-index.html').read_bytes().replace(b'2026.11.02',b'2026.11.01')]:
            self.assert_failure_unchanged(fetcher=FakeFetcher(index=b))
    def test_body_and_pdf_versions_are_retained(self):
        self.run_engine()
        self.run_engine(fetcher=FakeFetcher(pdf=b'%PDF-1.7\n'+b'y'*200))
        for entry in self.state()['temporary'].values():self.assertEqual(len(entry['versions']),2)
        self.run_engine(fetcher=FakeFetcher(pdf=b'%PDF-1.7\n'+b'y'*200))
        for entry in self.state()['temporary'].values():self.assertEqual(len(entry['versions']),2)
    def normal_rows(self):
        return [dict(url=m.OFFICIAL+'news/detail/8800'+str(n),date=e['official_date']+'T00:00:00+09:00',title=e['versions'][-1]['title']) for n,e in enumerate(self.state()['temporary'].values())]
    def approve(self):
        entries=list(self.state()['temporary'].values());rows=self.normal_rows()
        self.settings['mode']='normal'
        self.settings['normal_review']={'approved':True,'reviewed_at':'2026-11-02','coverage_note':'manually checked temporary period including all older pages','articles':{e['guid']:{'normal_url':r['url'],'evidence':'title/date/body/PDF matched manually'} for e,r in zip(entries,rows)}}
        self.save_config();return rows
    def test_no_automatic_switchback_or_fallback(self):
        self.run_engine();self.assert_failure_unchanged(fetcher=FakeFetcher(fail=m.OFFICIAL))
        self.settings['mode']='normal';self.save_config()
        self.assert_failure_unchanged(normal_provider=self.normal_rows)
    def test_explicit_normal_switch_preserves_temporary_guids(self):
        self.run_engine();before=m.feed_items(self.output.read_bytes())[1];rows=self.approve()
        self.run_engine(normal_provider=lambda:rows)
        after=m.feed_items(self.output.read_bytes())[1]
        self.assertEqual(set(before),set(after))
        self.assertEqual(self.state()['last_mode'],'normal')
        self.assertEqual(len(self.state()['reconciliation']),1)
        for guid in before:self.assertEqual(before[guid].findtext('pubDate'),after[guid].findtext('pubDate'))
        snap=self.snapshot();self.run_engine(normal_provider=lambda:rows);self.assertEqual(snap,self.snapshot())
    def test_normal_unmatched_temporary_retained(self):
        self.run_engine();rows=self.approve();guid=next(iter(self.settings['normal_review']['articles']))
        self.settings['normal_review']['articles'][guid]={'retain_temporary':True,'evidence':'not re-posted; reviewed all pages'};self.save_config()
        self.run_engine(normal_provider=lambda:rows[1:]);self.assertEqual(len(m.feed_items(self.output.read_bytes())[1]),19)
    def test_unmapped_normal_article_duplicate_is_blocked(self):
        self.run_engine();rows=self.approve()
        self.settings['normal_review']['articles'][next(iter(self.settings['normal_review']['articles']))]={'retain_temporary':True,'evidence':'unresolved'};self.save_config()
        self.assert_failure_unchanged(normal_provider=lambda:rows)
    def test_normal_identity_difference_needs_review(self):
        self.run_engine();rows=self.approve();rows[0]['title']='changed title'
        self.assert_failure_unchanged(normal_provider=lambda:rows)
        self.settings['normal_review']['articles'][next(iter(self.settings['normal_review']['articles']))]['accept_identity_difference']=True;self.save_config()
        self.run_engine(normal_provider=lambda:rows)
        self.assertNotIn('changed title',[i.findtext('title') for i in m.feed_items(self.output.read_bytes())[1].values()])
    def test_write_failure_rolls_back_both_files(self):
        before=self.snapshot();real=Path.replace
        def fail(path,target):
            if Path(target)==self.history:raise OSError('simulated disk failure')
            return real(path,target)
        with patch.object(Path,'replace',fail):
            with self.assertRaises(OSError):self.run_engine()
        self.assertEqual(before,self.snapshot())
    def test_unsafe_urls_rejected(self):
        for u in ['http://www.50913.ne.jp/higashishirakawa/%2e%2e/a.pdf','http://www.50913.ne.jp/higashishirakawa/%252e%252e/a','https://evil.example/x','http://www.50913.ne.jp/higashishirakawa/a%0ab']:
            with self.assertRaises(RuntimeError):m.checked_url(u)
    def test_duplicate_candidate_title_date_is_rejected(self):
        rows=m.parse_index((FIX/'simple-index.html').read_bytes())
        with patch.object(m,'collect_temporary',return_value=(rows+[rows[0]],{},{})):
            self.assert_failure_unchanged()
    def test_invalid_mode_does_not_write(self):
        self.assert_failure_unchanged(mode='auto')
    def test_public_bad_xml_or_identity_stops(self):
        for data in [b'<html>error</html>',self.old.replace('1014_岐阜県東白川村'.encode(),b'OTHER')]:self.assert_failure_unchanged(published=data)

if __name__=='__main__':unittest.main()
