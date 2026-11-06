from datetime import date
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as ET
import requests
import shiga_candidate as m

FIX = Path(__file__).parent / 'fixtures'
START, END = date(2026,9,3), date(2026,11,6)


class Safety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name) / 'rss'
        self.fixtures = Path(self.tmp.name) / 'fixtures'
        self.fixtures.mkdir()
        for i in [1,2]:
            (self.fixtures / f'shiga-search-{i}.html').write_bytes((FIX / f'shiga-search-{i}.html').read_bytes())
        self.result = m.run(self.output, START, END, self.fixtures, True)
        self.before = {p.name:p.read_bytes() for p in self.output.glob('*.xml')}

    def assert_preserved(self):
        self.assertEqual(self.before, {p.name:p.read_bytes() for p in self.output.glob('*.xml')})

    def test_complete_pagination_and_repeat(self):
        self.assertEqual(self.result['counts'], {'お知らせ':284,'イベント':117,'募集':36})
        self.assertEqual(len(self.result['rows']), 437)
        self.assertEqual(len(self.result['pages']), 2)
        m.run(self.output, START, END, self.fixtures)
        self.assert_preserved()

    def test_every_category_legacy_guid_and_items_survive(self):
        for label, slug in m.CATEGORIES.items():
            p = self.output / f'support-0205-shiga-{slug}.xml'
            root = ET.fromstring(p.read_bytes())
            item = root.find('./channel/item')
            item.find('guid').text = 'urn:legacy:'+slug
            item.find('guid').set('isPermaLink', 'false')
            old_item = ET.tostring(item)
            p.write_bytes(ET.tostring(root))
            before = p.read_bytes()
            # Existing record title changes do not change its old GUID/body.
            rows = [dict(x) for x in self.result['rows'] if x['category']==label]
            rows[0]['title'] = 'Updated official title'
            new_url = 'https://www.pref.shiga.lg.jp/test/99999999.html'
            rows.append(dict(category=label,title='Synthetic new item',date='2026-11-06',url=new_url))
            data = m.candidate(label, rows, before)
            after = ET.fromstring(data)
            old_after = next(i for i in after.findall('./channel/item') if i.findtext('guid') == 'urn:legacy:'+slug)
            self.assertEqual(old_item, ET.tostring(old_after))
            self.assertEqual(len(after.findall('./channel/item')), len(root.findall('./channel/item'))+1)

    def test_empty_bad_category_date_link_count_and_filter_fail_closed(self):
        original = (FIX / 'shiga-search-1.html').read_text()
        cases = ['', original.replace('class="col-category">お知らせ', 'class="col-category">不明分類', 1),
                 original.replace('2026年11月6日', '2026年13月6日', 1),
                 original.replace('/jc00/press-release/34563.html', 'https://example.com/fake.html', 1),
                 original.replace('437件中', '438件中'),
                 original.replace('value="2026-09-03"', 'value="2026-01-01"')]
        for html in cases:
            with self.subTest(case=html[:25]):
                (self.fixtures/'shiga-search-1.html').write_text(html)
                with self.assertRaises((ValueError, AttributeError)):
                    m.run(self.output, START, END, self.fixtures)
                self.assert_preserved()

    def test_repeated_second_page_is_rejected(self):
        (self.fixtures/'shiga-search-2.html').write_bytes((FIX/'shiga-search-1.html').read_bytes())
        with self.assertRaises(ValueError):
            m.run(self.output, START, END, self.fixtures)
        self.assert_preserved()

    def test_second_page_http_failure_keeps_all_categories(self):
        calls = []
        def get(url, **kwargs):
            calls.append(url)
            if len(calls)==2:
                raise requests.HTTPError('simulated 503')
            r=requests.Response();r.status_code=200;r.url=url;r.headers['Content-Type']='text/html'
            r._content=(FIX/'shiga-search-1.html').read_bytes()
            return r
        with self.assertRaises(requests.HTTPError):
            m.run(self.output, START, END, get=get)
        self.assert_preserved()

    def test_missing_or_corrupt_baseline_not_overwritten(self):
        p=next(self.output.glob('*.xml'));p.write_bytes(b'corrupt')
        with self.assertRaises(ET.ParseError):
            m.run(self.output, START, END, self.fixtures, True)
        self.assertEqual(p.read_bytes(),b'corrupt')
        p.unlink()
        with self.assertRaises(ValueError):
            m.run(self.output, START, END, self.fixtures)
        self.assertFalse(p.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
