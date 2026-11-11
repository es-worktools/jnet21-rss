import copy
from datetime import datetime, date
import fcntl
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

import requests
import yaml
import scrape_sapporo_consultation as m
import publish_sapporo_consultation as p

FIX = Path(__file__).parent / 'fixtures'
NOW = datetime(2026, 11, 11, 18, 0, tzinfo=m.TZ)
ROOT = Path(__file__).resolve().parents[2]


def records(fixtures=FIX, now=NOW):
    return [r for slug, title, count in m.CONFIG
            for r in m.extract((fixtures / f'{slug}.html').read_bytes(), slug, title, count, now)]


class Safety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / 'rss'
        self.fx = Path(self.tmp.name) / 'fixtures'
        shutil.copytree(FIX, self.fx)
        self.initial = (FIX / 'initial3.xml').read_bytes()
        self.out.mkdir()
        self.target = self.out / m.FILE
        self.target.write_bytes(self.initial)

    def run_feed(self):
        return m.run(self.out, self.fx, now=NOW)

    def edit(self, old, new, slug='woman'):
        path = self.fx / f'{slug}.html'
        text = path.read_text()
        self.assertIn(old, text)
        path.write_text(text.replace(old, new))

    def unchanged_after_error(self, error=ValueError):
        before = self.target.read_bytes()
        with self.assertRaises(error):
            self.run_feed()
        self.assertEqual(before, self.target.read_bytes())

    def test_initial_bootstrap_and_exact_repeat(self):
        self.target.unlink()
        first = m.run(self.out, self.fx, bootstrap=True, now=NOW)
        before = self.target.read_bytes()
        self.assertEqual((first['added'], first['total']), (3, 3))
        self.assertEqual(self.run_feed()['added'], 0)
        self.assertEqual(before, self.target.read_bytes())

    def test_real_official_change_preserves_three_original_items(self):
        result = self.run_feed()
        self.assertEqual((result['added'], result['total']), (1, 4))
        current = ET.fromstring(self.target.read_bytes())
        index = {i.findtext('guid'): i for i in m.validate(current)}
        for item in m.validate(ET.fromstring(self.initial)):
            self.assertEqual(ET.tostring(item), ET.tostring(index[item.findtext('guid')]))
        new = current.find('./channel/item')
        self.assertIn('予定変更 r2', new.findtext('title'))
        self.assertIn('24日（火曜日）・25日（水曜日）※午前のみ', new.findtext('description'))
        self.assertNotIn('模擬', self.target.read_text())

    def test_unchanged_bytes_even_at_next_detection_time(self):
        self.run_feed()
        before = self.target.read_bytes()
        result = m.run(self.out, self.fx, now=NOW.replace(day=12))
        self.assertEqual(result['added'], 0)
        self.assertEqual(before, self.target.read_bytes())

    def test_real_revision_then_reversion_has_new_guid(self):
        self.run_feed()
        old = self.target.read_bytes()
        self.edit('※午後のみ', '※午前のみ')
        self.assertEqual(self.run_feed()['total'], 5)
        shutil.copyfile(FIX / 'woman.html', self.fx / 'woman.html')
        self.assertEqual(self.run_feed()['total'], 6)
        root = ET.fromstring(self.target.read_bytes())
        self.assertIn('r4', root.findtext('./channel/item/title'))
        old_index = {i.findtext('guid'): ET.tostring(i) for i in m.validate(ET.fromstring(old))}
        new_index = {i.findtext('guid'): ET.tostring(i) for i in m.validate(root)}
        self.assertTrue(old_index.items() <= new_index.items())

    def test_month_rollover(self):
        self.run_feed()
        for slug, _, _ in m.CONFIG:
            path = self.fx / f'{slug}.html'
            text = path.read_text().replace('2026年11月', '2026年12月')
            text = re.sub(r'(\d{1,2})日（[月火水木金土日]曜日）',
                          lambda x: x[1] + '日（' + '月火水木金土日'[date(2026,12,int(x[1])).weekday()] + '曜日）', text)
            path.write_text(text)
        result = self.run_feed() # Next month may be published in advance.
        self.assertEqual((result['added'], result['total']), (3, 7))
        self.assertIn('新月予定', self.target.read_text())

    def test_month_regression_rejected(self):
        self.test_month_rollover()
        shutil.copyfile(FIX / 'woman.html', self.fx / 'woman.html')
        shutil.copyfile(FIX / 'consultation-2.html', self.fx / 'consultation-2.html')
        self.unchanged_after_error()

    def test_spacing_profile_and_banner_do_not_notify(self):
        self.run_feed()
        before = self.target.read_bytes()
        self.edit('2日（月曜日）', '2日（ 月曜日 ）')
        self.edit('コンサルティング会社', 'プロフィールの別の表現')
        self.edit('</body>', '<aside>新しい広告</aside></body>')
        self.assertEqual(self.run_feed()['added'], 0)
        self.assertEqual(before, self.target.read_bytes())

    def test_note_change_notifies(self):
        self.run_feed()
        self.edit('★12日以外は午前のみの受付となります★', '★12日以外は午前のみの受付となります。要予約★')
        self.assertEqual(self.run_feed()['added'], 1)

    def test_html_body_is_escaped_and_has_paragraphs(self):
        self.edit('※午後のみ', '※午後のみ &lt;文字列&gt; &amp; 注記')
        self.run_feed()
        root = ET.fromstring(self.target.read_bytes())
        item = root.find('./channel/item')
        encoded = item.findtext(f'{{{m.CONTENT}}}encoded')
        self.assertIn('<p>', encoded)
        self.assertIn('&lt;文字列&gt; &amp;', encoded)
        self.assertNotIn('<文字列>', encoded)
        self.assertEqual(self.run_feed()['added'], 0)

    def test_missing_body(self):
        self.edit('entry-content', 'broken-content')
        self.unchanged_after_error()

    def test_missing_heading(self):
        self.edit('相談予定（2026年11月）', '日程一覧')
        self.unchanged_after_error()

    def test_missing_one_series(self):
        path = self.fx / 'woman.html'
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(path.read_bytes(), 'html.parser')
        soup.find_all('h5', string='相談予定（2026年11月）')[0].decompose()
        path.write_text(str(soup))
        self.unchanged_after_error()

    def test_consultant_identity_change(self):
        self.edit('小西 麻衣', '別の担当者')
        self.unchanged_after_error()

    def test_duplicate_series(self):
        self.edit('木原 真由美', '小西 麻衣')
        self.unchanged_after_error()

    def test_stale_month(self):
        self.edit('2026年11月', '2026年10月')
        self.unchanged_after_error()

    def test_invalid_weekday(self):
        self.edit('2日（月曜日）', '2日（火曜日）')
        self.unchanged_after_error()

    def test_invalid_calendar_day(self):
        self.edit('2日（月曜日）', '32日（月曜日）')
        self.unchanged_after_error()

    def test_partial_bad_date_not_silently_ignored(self):
        self.edit('24日（火曜日）', '24日（火曜）')
        self.unchanged_after_error()

    def test_duplicate_date(self):
        self.edit('24日（火曜日）', '24日（火曜日）・24日（火曜日）')
        self.unchanged_after_error()

    def test_date_loss_rejected_even_if_legitimate_cancellation(self):
        self.run_feed()
        self.edit('・25日（水曜日）※午前のみ', '')
        self.unchanged_after_error()

    def test_note_paragraph_loss_rejected(self):
        path = self.fx / 'woman.html'
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(path.read_bytes(), 'html.parser')
        soup.find('span', string='★12日以外は午前のみの受付となります★').parent.decompose()
        path.write_text(str(soup))
        self.unchanged_after_error()

    def test_unrecognized_schedule_structure(self):
        self.edit('2日（月曜日）', '<img alt="2日（月曜日）">')
        self.unchanged_after_error()

    def test_mock_data_rejected(self):
        self.edit('※午後のみ', '模擬変更・試験データ')
        self.unchanged_after_error()

    def test_missing_baseline_requires_explicit_bootstrap(self):
        self.target.unlink()
        with self.assertRaises(ValueError):
            self.run_feed()
        self.assertFalse(self.target.exists())

    def test_corrupt_baseline_is_not_bootstrapped_over(self):
        self.target.write_bytes(b'broken')
        self.unchanged_after_error(ET.ParseError)

    def test_corrupt_ledger_fields_rejected(self):
        mutations = [lambda i: i.find('guid').__setattr__('text', 'bad'),
                     lambda i: i.find(f'{{{m.NS}}}revision').__setattr__('text', '2'),
                     lambda i: i.find('description').__setattr__('text', 'bad'),
                     lambda i: i.find('link').__setattr__('text', 'https://example.org/'),
                     lambda i: i.find('pubDate').__setattr__('text', 'not a date'),
                     lambda i: i.append(copy.deepcopy(i.find('guid')))]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                root = ET.fromstring(self.initial)
                mutate(root.find('./channel/item'))
                self.target.write_bytes(ET.tostring(root))
                self.unchanged_after_error()

    def test_missing_history_series_rejected(self):
        root = ET.fromstring(self.initial)
        root.find('channel').remove(root.find('./channel/item'))
        self.target.write_bytes(ET.tostring(root))
        self.unchanged_after_error()

    def test_duplicate_revision_rejected(self):
        root = ET.fromstring(self.initial)
        item = copy.deepcopy(root.find('./channel/item'))
        item.find('guid').text += ':duplicate'
        root.find('channel').append(item)
        self.target.write_bytes(ET.tostring(root))
        self.unchanged_after_error()

    def test_failed_second_http_request_preserves_baseline(self):
        def get(url, **kwargs):
            if 'consultation-2' in url:
                raise requests.Timeout('simulated timeout')
            r = requests.Response();r.status_code = 200;r.url = url
            r.headers['Content-Type'] = 'text/html';r._content = (FIX / 'woman.html').read_bytes()
            return r
        with self.assertRaises(requests.Timeout):
            m.run(self.out, now=NOW, get=get)
        self.assertEqual(self.initial, self.target.read_bytes())

    def test_http_error_redirect_and_content_type_preserve_baseline(self):
        for status, suffix, ctype in [(503, '', 'text/html'), (200, 'changed', 'text/html'), (200, '', 'application/pdf')]:
            def get(url, **kwargs):
                r = requests.Response();r.status_code = status;r.url = url + suffix
                r.headers['Content-Type'] = ctype;r._content = (FIX / 'woman.html').read_bytes()
                return r
            with self.subTest(status=status, suffix=suffix, ctype=ctype):
                with self.assertRaises((ValueError, requests.HTTPError)):
                    m.run(self.out, now=NOW, get=get)
                self.assertEqual(self.initial, self.target.read_bytes())

    def test_atomic_replace_failure_leaves_old_bytes_and_no_temp(self):
        with patch.object(m.os, 'replace', side_effect=OSError('simulated write failure')):
            self.unchanged_after_error(OSError)
        self.assertEqual({x.name for x in self.out.iterdir()}, {m.FILE})

    def test_compare_before_replace_detects_external_change(self):
        actual = m.os.fsync
        def change(fd):
            actual(fd)
            self.target.write_bytes(b'other writer')
        with patch.object(m.os, 'fsync', side_effect=change):
            with self.assertRaises(ValueError):
                self.run_feed()
        self.assertEqual(self.target.read_bytes(), b'other writer')

    def test_local_writer_lock(self):
        lock = Path(tempfile.gettempdir()) / ('jnet21-sapporo-' + m.digest(str(self.out.resolve())) + '.lock')
        with lock.open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.unchanged_after_error(BlockingIOError)

    def test_aware_timestamp_required(self):
        with self.assertRaises(ValueError):
            m.generate(self.initial, records(), NOW.replace(tzinfo=None))

    def test_record_fingerprint_mismatch(self):
        batch = records();batch[0]['fingerprint'] = '0' * 64
        with self.assertRaises(ValueError):
            m.generate(self.initial, batch, NOW)

    def test_partial_record_batch(self):
        with self.assertRaises(ValueError):
            m.generate(self.initial, records()[:2], NOW)

    def test_preview_cannot_modify_source_checkout(self):
        with self.assertRaises(ValueError):
            p.build(self.out, self.out)

    def test_prepared_rss_keeps_original_guids_and_has_no_mock(self):
        data = (ROOT / m.FILE).read_bytes()
        items = m.validate(ET.fromstring(data))
        old = {i.findtext('guid') for i in m.validate(ET.fromstring(self.initial))}
        self.assertTrue(old <= {i.findtext('guid') for i in items})
        self.assertEqual(len(items), 4)
        self.assertNotIn('模擬変更', data.decode())

    def test_workflow_publish_guards_and_schedule(self):
        raw = (ROOT / '.github/workflows/update-sapporo-consultation.yml').read_text()
        config = yaml.load(raw, Loader=yaml.BaseLoader)
        self.assertEqual(config['on']['workflow_dispatch']['inputs']['publish']['default'], 'false')
        self.assertEqual(config['on']['schedule'][0]['cron'], '37 22 * * *')
        self.assertIn("github.ref == 'refs/heads/main'", config['jobs']['update']['if'])
        self.assertEqual(config['concurrency']['cancel-in-progress'], 'false')
        self.assertIn('--publish', raw)
        self.assertNotIn('push:', raw)


if __name__ == '__main__':
    unittest.main()
