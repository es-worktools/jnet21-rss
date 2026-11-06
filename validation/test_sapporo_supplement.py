import copy
from datetime import datetime, date
import json
from pathlib import Path
import re
import tempfile
import unittest
from xml.etree import ElementTree as ET
import requests

import sapporo_supplement as m

NOW = datetime(2026, 11, 6, 12, 30, tzinfo=m.TZ)
FIX = Path(__file__).parent / 'fixtures'


class Safety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name) / 'rss'
        self.fixtures = Path(self.tmp.name) / 'fixtures'
        self.fixtures.mkdir()
        for slug, _, _ in m.CONFIG:
            (self.fixtures / f'{slug}.html').write_bytes((FIX / f'{slug}.html').read_bytes())
        self.result = m.run(self.output, self.fixtures, True, NOW)
        self.path = self.output / m.FILE
        self.before = self.path.read_bytes()

    def mutate(self, old, new, slug='woman'):
        p = self.fixtures / f'{slug}.html'
        p.write_text(p.read_text().replace(old, new))

    def test_initial_and_no_change(self):
        self.assertEqual((self.result['added'], self.result['total']), (3, 3))
        result = m.run(self.output, self.fixtures, now=NOW)
        self.assertEqual(result['added'], 0)
        self.assertEqual(self.before, self.path.read_bytes())

    def test_revision_reversion_and_old_items_preserved(self):
        self.mutate('※午後のみ', '※午前のみ')
        result = m.run(self.output, self.fixtures, now=NOW)
        self.assertEqual((result['added'], result['total']), (1, 4))
        self.mutate('※午前のみ', '※午後のみ')
        # Restore the exact original page, including the other consultant.
        (self.fixtures / 'woman.html').write_bytes((FIX / 'woman.html').read_bytes())
        self.assertEqual(m.run(self.output, self.fixtures, now=NOW)['total'], 5)
        after = ET.fromstring(self.path.read_bytes())
        old = ET.fromstring(self.before).findall('./channel/item')
        indexed = {i.findtext('guid'): i for i in after.findall('./channel/item')}
        for i in old:
            self.assertEqual(ET.tostring(i), ET.tostring(indexed[i.findtext('guid')]))

    def test_whitespace_profile_and_banner_no_notification(self):
        self.mutate('2日（月曜日）', '2日（ 月曜日 ）')
        self.mutate('コンサルティング会社', 'プロフィール内容を変更')
        self.mutate('</body>', '<aside>広告の変更</aside></body>')
        self.assertEqual(m.run(self.output, self.fixtures, now=NOW)['added'], 0)
        self.assertEqual(self.before, self.path.read_bytes())

    def test_new_month(self):
        for slug, _, _ in m.CONFIG:
            p = self.fixtures / f'{slug}.html'
            html = p.read_text().replace('2026年11月', '2026年12月')
            html = re.sub(r'(\d{1,2})日（[月火水木金土日]曜日）', lambda x: x[1]+'日（'+'月火水木金土日'[date(2026,12,int(x[1])).weekday()]+'曜日）', html)
            p.write_text(html)
        result = m.run(self.output, self.fixtures, now=NOW.replace(month=12))
        self.assertEqual((result['added'], result['total']), (3, 6))

    def test_following_month_can_be_announced_early(self):
        for slug, _, _ in m.CONFIG:
            p = self.fixtures / f'{slug}.html'
            html = p.read_text().replace('2026年11月', '2026年12月')
            html = re.sub(r'(\d{1,2})日（[月火水木金土日]曜日）', lambda x: x[1]+'日（'+'月火水木金土日'[date(2026,12,int(x[1])).weekday()]+'曜日）', html)
            p.write_text(html)
        result = m.run(self.output, self.fixtures, now=NOW)
        self.assertEqual((result['added'], result['total']), (3, 6))

    def test_partial_structure_stale_and_bad_weekday_keep_bytes(self):
        original = (FIX / 'woman.html').read_text()
        for html in ['', original.replace('entry-content', 'broken'), original.replace('相談予定（2026年11月）', '相談予定（2026年10月）'), original.replace('2日（月曜日）', '2日（火曜日）'), original.replace('相談予定（2026年11月）', '相談日程', 1)]:
            with self.subTest(html=html[:30]):
                (self.fixtures / 'woman.html').write_text(html)
                with self.assertRaises(ValueError):
                    m.run(self.output, self.fixtures, now=NOW)
                self.assertEqual(self.before, self.path.read_bytes())

    def test_http_failure_after_first_page_keeps_bytes(self):
        calls = []
        def get(url, **kwargs):
            calls.append(url)
            if len(calls) == 2:
                raise requests.Timeout('simulated')
            r = requests.Response()
            r.status_code = 200
            r.url = url
            r.headers['Content-Type'] = 'text/html'
            r._content = (FIX / 'woman.html').read_bytes()
            return r
        with self.assertRaises(requests.Timeout):
            m.run(self.output, now=NOW, get=get)
        self.assertEqual(self.before, self.path.read_bytes())

    def test_missing_and_corrupt_baseline_are_not_reset(self):
        self.path.write_bytes(b'corrupt')
        with self.assertRaises(ET.ParseError):
            m.run(self.output, self.fixtures, True, NOW)
        self.assertEqual(self.path.read_bytes(), b'corrupt')
        self.path.unlink()
        with self.assertRaises(ValueError):
            m.run(self.output, self.fixtures, now=NOW)
        self.assertFalse(self.path.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
