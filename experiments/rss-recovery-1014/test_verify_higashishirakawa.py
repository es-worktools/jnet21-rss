import copy
import importlib.util
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

SPEC = importlib.util.spec_from_file_location('prototype', Path(__file__).with_name('verify_higashishirakawa.py'))
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
FIXTURES = Path(__file__).parent/'fixtures'

class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.old = (FIXTURES/'baseline.xml').read_bytes()
        self.index = (FIXTURES/'simple-index.html').read_bytes()
        self.rows = m.parse_index(self.index)

    def test_real_diff_and_retention(self):
        payload, report = m.merge(self.old, self.rows)
        self.assertEqual((report['baseline_count'], report['dated_notices'], len(report['added']), len(report['aliases']), report['output_count']), (17,3,2,1,19))
        self.assertEqual({x['date'][:10] for x in report['added']}, {'2026-10-27','2026-11-02'})
        old = ET.fromstring(self.old).findall('./channel/item')
        new = {x.findtext('guid'):x for x in ET.fromstring(payload).findall('./channel/item')}
        for x in old:
            self.assertEqual(x.findtext('title'),new[x.findtext('guid')].findtext('title'))
            self.assertEqual(x.findtext('pubDate'),new[x.findtext('guid')].findtext('pubDate'))
        self.assertEqual(report['aliases'][0]['retained_guid'], 'https://www.vill.higashishirakawa.gifu.jp/news/detail/767')
        self.assertEqual(new[report['aliases'][0]['retained_guid']].findtext('link'),m.SIMPLE+'#DIY_WS')

    def test_event_date_is_not_publication_date(self):
        row = next(x for x in self.rows if x['url'].endswith('#akifesta'))
        self.assertEqual(row['date'][:10], '2026-11-02')
        self.assertIn('2026(令和8)年11月15日開催', row['body'])

    def test_undated_welfare_is_reference_only(self):
        row = m.parse_welfare((FIXTURES/'sonfuku.html').read_bytes())
        self.assertIsNone(row['date'])
        self.assertEqual(len(row['pdfs']),1)

    def test_authority_must_be_current_and_exact(self):
        m.authority((FIXTURES/'official-home.html').read_bytes())
        with self.assertRaises(RuntimeError):
            m.authority(b'<html>maintenance <a href="http://example.com">link</a></html>')

    def test_empty_or_maintenance_page_rejected(self):
        for body in (b'<html></html>',(FIXTURES/'official-home.html').read_bytes()):
            with self.assertRaises(RuntimeError): m.parse_index(body)

    def test_invalid_or_missing_date_rejected(self):
        for replacement in (b'2026.99.02', b''):
            body = self.index.replace(b'2026.11.02',replacement)
            with self.assertRaises((RuntimeError,ValueError)): m.parse_index(body)

    def test_external_article_is_rejected(self):
        body = self.index.replace(b'href="#akifesta"',b'href="https://example.com/#akifesta"')
        with self.assertRaises(RuntimeError): m.parse_index(body)
        for u in ('https://evil.example/a','file:///tmp/a','http://www.50913.ne.jp/other/a','http://www.50913.ne.jp/higashishirakawa/../a'):
            with self.assertRaises(RuntimeError): m.checked_url(u)

    def test_unknown_new_page_requires_scope_review(self):
        body=self.index.replace(b'</body>',b'<a href="new-section.html">new</a></body>')
        with self.assertRaises(RuntimeError): m.parse_index(body)

    def test_missing_pdf_or_anchor_rejected(self):
        for body in (self.index.replace(b'name="akifesta" id="akifesta"',b'name="changed" id="changed"'), self.index.replace(b'.pdf"',b'.dat"')):
            with self.assertRaises(RuntimeError): m.parse_index(body)

    def test_merge_is_idempotent(self):
        once,_=m.merge(self.old,self.rows)
        twice,r=m.merge(once,self.rows)
        self.assertEqual(once,twice)
        self.assertFalse(r['added'])
        self.assertEqual(r['output_count'],19)

    def test_reused_temporary_url_is_not_silently_overwritten(self):
        once,_=m.merge(self.old,self.rows)
        rows=copy.deepcopy(self.rows)
        rows[0]['title']='another article'
        with self.assertRaises(RuntimeError): m.merge(once,rows)

    def test_empty_baseline_rejected(self):
        root=ET.fromstring(self.old)
        for item in root.findall('./channel/item'):root.find('channel').remove(item)
        with self.assertRaises(RuntimeError):m.merge(ET.tostring(root),self.rows)

    def test_ambiguous_title_date_match_rejected(self):
        root=ET.fromstring(self.old)
        item=copy.deepcopy(root.find('./channel/item'))
        item.find('guid').text='https://www.vill.higashishirakawa.gifu.jp/news/detail/999999'
        root.find('channel').append(item)
        with self.assertRaises(RuntimeError):m.merge(ET.tostring(root),self.rows)

    def test_failure_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'candidate.xml'
            output.write_bytes(self.old)
            # Fail on the absent PDF fixture, after successful source parsing.
            with self.assertRaises(FileNotFoundError):
                m.run(FIXTURES/'baseline.xml',output,Path(folder)/'evidence',FIXTURES)
            self.assertEqual(output.read_bytes(),self.old)

    def test_production_filename_and_baseline_overwrite_forbidden(self):
        with tempfile.TemporaryDirectory() as folder:
            for output in (Path(folder)/m.PRODUCTION_NAME,FIXTURES/'baseline.xml'):
                with self.assertRaises(RuntimeError):m.run(FIXTURES/'baseline.xml',output,folder,FIXTURES)

if __name__=='__main__':unittest.main()
