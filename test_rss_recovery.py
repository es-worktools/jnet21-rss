"""Regression checks for municipal feed recovery (no network required)."""
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


kitamoto = load('scrape_municipality_0564_kitamoto')
funagata = load('scrape_municipality_0350_funagata')


class RecoveryTests(unittest.TestCase):
    def record(self, url, title='Municipal news'):
        return dict(page_name=title, url=url,
                    publish_datetime=kitamoto.datetime.now(kitamoto.JST).isoformat(),
                    is_category_index=False, is_keitai_page=False)

    def listing(self, *paths):
        return '<dl class="news icon">' + ''.join(
            '<dt>11月2日</dt><dd><a href="%s">Article</a></dd>' % p for p in paths) + '</dl>'

    def generate(self, module, fetch):
        with tempfile.TemporaryDirectory() as directory:
            output = str(Path(directory) / 'feed.xml')
            Path(output).write_bytes(b'previous feed')
            with patch.object(module, 'OUTPUT_FILE', output), patch.object(module, 'fetch', side_effect=fetch):
                module.main()
            return ET.parse(output)

    def test_external_shortcut_does_not_block_internal_news(self):
        records = [self.record('https://maple-festa.com/'), self.record('/support.html', 'Support')]
        tree = self.generate(kitamoto, lambda _: json.dumps(records))
        self.assertEqual([n.text for n in tree.findall('./channel/item/title')], ['Support'])
        self.assertEqual(tree.findtext('./channel/item/guid'), 'https://www.city.kitamoto.lg.jp/support.html')

    def test_invalid_scheme_still_fails(self):
        with self.assertRaisesRegex(RuntimeError, 'Unexpected article URL'):
            kitamoto.parse_source(json.dumps([self.record('javascript:alert(1)')]), kitamoto.SOURCE_URL, {})

    def test_duplicate_url_keeps_newest_record(self):
        old = self.record('/support.html', 'Old')
        new = self.record('/support.html', 'Updated')
        old['publish_datetime'] = (kitamoto.datetime.now(kitamoto.JST) - kitamoto.timedelta(days=1)).isoformat()
        tree = self.generate(kitamoto, lambda _: json.dumps([old, new]))
        self.assertEqual([n.text for n in tree.findall('./channel/item/title')], ['Updated'])

    def test_pr_templates_and_regular_page_are_all_retained(self):
        pages = {
            funagata.SOURCE_URL: self.listing('/normal.html', '/posted.html', '/undated.html'),
            funagata.SOURCE_URL.replace('/news.html', '/normal.html'): '<h1>Normal</h1><p class="right">更新日：2026年11月2日</p>',
            funagata.SOURCE_URL.replace('/news.html', '/posted.html'): '<h1>Posted</h1><div class="txtbox">掲載日：令和8年10月21日<br/>Article</div>',
            funagata.SOURCE_URL.replace('/news.html', '/undated.html'): '<h1>Undated</h1><div class="txtbox">Article</div>',
        }
        tree = self.generate(funagata, pages.__getitem__)
        items = tree.findall('./channel/item')
        self.assertEqual(len(items), 3)
        self.assertIn('02 Nov 2026', items[0].findtext('pubDate'))
        self.assertIn('21 Oct 2026', items[1].findtext('pubDate'))
        self.assertIsNone(items[2].find('pubDate'))
        self.assertEqual(len({n.findtext('guid') for n in items}), 3)

    def assert_preserved(self, module, fetch):
        with tempfile.TemporaryDirectory() as directory:
            output = str(Path(directory) / 'feed.xml')
            Path(output).write_bytes(b'previous feed')
            with patch.object(module, 'OUTPUT_FILE', output), patch.object(module, 'fetch', side_effect=fetch):
                with self.assertRaises((RuntimeError, ValueError)):
                    module.main()
            self.assertEqual(Path(output).read_bytes(), b'previous feed')
            self.assertFalse(Path(output + '.tmp').exists())

    def test_empty_or_broken_json_preserves_previous_feed(self):
        for response in ['[]', '{}', 'not json']:
            with self.subTest(response=response):
                self.assert_preserved(kitamoto, lambda _: response)

    def test_external_only_json_preserves_previous_feed(self):
        self.assert_preserved(kitamoto, lambda _: json.dumps([self.record('https://maple-festa.com/')]))

    def test_unexpected_detail_structure_preserves_previous_feed(self):
        self.assert_preserved(funagata, lambda url: self.listing('/article.html') if url == funagata.SOURCE_URL else '<h1>Access denied</h1>')

    def test_network_failure_preserves_previous_feed(self):
        def fetch(url):
            if url == funagata.SOURCE_URL:
                return self.listing('/article.html')
            raise RuntimeError('HTTP 503')
        self.assert_preserved(funagata, fetch)


if __name__ == '__main__':
    unittest.main()
