import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from xml.etree.ElementTree import parse

import requests

import scrape_bnest as bnest


def article(number, date, category="講座・セミナー"):
    return f"""
        <div class="eventItem">
          <div class="eventItem__head">
            <p class="date">{date}</p><p class="tag">{category}</p>
          </div>
          <p><p><span><a href="https://example.org/news/{number}">記事 {number}</a></span></p></p>
        </div>
    """


def listing(*cards, category_cards=""):
    return f"""
        <div class="eventTab">
          <div class="eventTab__item" id="event1">{''.join(cards)}</div>
          <div class="eventTab__item" id="event2">{category_cards}</div>
        </div>
    """


class BnestRSSTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.output = Path(directory) / "bnest-topics.xml"
        self.get = self.enterContext(patch.object(bnest.requests, "get"))
        self.enterContext(redirect_stdout(io.StringIO()))

    def update(self, html):
        self.get.return_value.text = html
        bnest.update_rss(self.output)
        return parse(self.output).findall("./channel/item")

    def seed(self, count=3):
        self.update(listing(*(article(i, "2026年12月01日") for i in range(count))))
        return self.output.read_bytes()

    def test_2026_2027_mixed_and_later_years(self):
        for dates in (
            ("2026年12月31日", "2026年12月1日"),
            ("2027年01月01日", "2027年01月02日"),
            ("2026年12月31日", "2027年1月1日"),
            ("2028年01月01日", "2032年02月29日"),
        ):
            with self.subTest(dates=dates):
                items = self.update(listing(article(1, dates[0]), article(2, dates[1])))
                self.assertEqual([item.findtext("title") for item in items], ["記事 1", "記事 2"])
                self.assertTrue(all(item.findtext("guid") == item.findtext("link") for item in items))

    def test_unrelated_links_and_category_tab_duplicates(self):
        seminar = article(1, "2027年01月30日")
        seminar = seminar.replace("<p><p>", '<div><a href="/related/">関連情報</a></div><p><p>')
        event = article(2, "2026年11月28日", "イベント")
        grant = article(3, "2026年09月01日", "各種公募・補助金情報")
        unrelated = article(9, "2026年11月27日", "その他")
        html = '<nav>2027年1月1日 イベント <a href="/related/">ナビ</a></nav>'
        html += listing(seminar, event, grant, unrelated, category_cards=seminar)
        self.assertEqual([item.findtext("title") for item in self.update(html)], ["記事 1", "記事 2", "記事 3"])

    def test_link_resolution_and_item_limit(self):
        cards = [article(i, "2027年01月01日") for i in range(31)]
        cards[0] = cards[0].replace("https://example.org/news/0", "/news/0")
        items = self.update(listing(*cards))
        self.assertEqual(len(items), 30)
        self.assertEqual(items[0].findtext("link"), "https://www.b-nest.jp/news/0")

    def test_http_failure_and_timeout_preserve_feed(self):
        previous = self.seed()
        self.get.return_value.raise_for_status.side_effect = requests.HTTPError("503")
        with self.assertRaises(requests.HTTPError):
            bnest.update_rss(self.output)
        self.assertEqual(self.output.read_bytes(), previous)

        self.get.side_effect = requests.Timeout
        with self.assertRaises(requests.Timeout):
            bnest.update_rss(self.output)
        self.assertEqual(self.output.read_bytes(), previous)

    def test_invalid_html_empty_and_partially_invalid_cards_preserve_feed(self):
        previous = self.seed()
        valid = article(1, "2027年01月01日")
        for html in (
            "<html><broken",
            listing(),
            listing(article(1, "2027年01月01日", "未監視カテゴリ")),
            listing(valid, article(2, "日付なし")),
            listing(valid.replace("https://example.org/news/1", "javascript:void(0)")),
            listing(valid.replace("</span>", '<a href="/related/">関連リンク</a></span>')),
        ):
            with self.subTest(html=html), self.assertRaises(ValueError):
                self.update(html)
            self.assertEqual(self.output.read_bytes(), previous)

    def test_empty_first_run_leaves_no_feed(self):
        with self.assertRaisesRegex(ValueError, "returned no items"):
            self.update(listing())
        self.assertFalse(self.output.exists())

    def test_abnormal_decrease_preserves_feed(self):
        previous = self.seed(12)
        with self.assertRaisesRegex(ValueError, "dropped from 12 to 6"):
            self.update(listing(*(article(i, "2027年01月01日") for i in range(6))))
        self.assertEqual(self.output.read_bytes(), previous)

    def test_normal_decrease_updates_feed(self):
        self.seed()
        items = self.update(listing(article(0, "2027年01月01日"), article(1, "2027年01月02日")))
        self.assertEqual([item.findtext("title") for item in items], ["記事 0", "記事 1"])

    def test_retained_link_keeps_guid_and_publication_date_and_rerun_is_unchanged(self):
        self.output.write_text(
            '<rss><channel><item><link>https://example.org/news/1</link>'
            '<guid isPermaLink="false">original-id</guid>'
            '<pubDate>Thu, 26 Nov 2026 03:00:00 GMT</pubDate></item></channel></rss>',
            encoding="utf-8",
        )
        html = listing(article(1, "2027年01月01日"), article(2, "2027年01月02日"))
        existing, new = self.update(html)
        self.assertEqual(existing.findtext("guid"), "original-id")
        self.assertEqual(existing.find("guid").attrib, {"isPermaLink": "false"})
        self.assertEqual(existing.findtext("pubDate"), "Thu, 26 Nov 2026 03:00:00 GMT")
        self.assertEqual(new.findtext("guid"), "https://example.org/news/2")
        self.assertIsNone(new.find("pubDate"))

        previous = self.output.read_bytes()
        modified = self.output.stat().st_mtime_ns
        self.update(html)
        self.assertEqual(self.output.read_bytes(), previous)
        self.assertEqual(self.output.stat().st_mtime_ns, modified)
