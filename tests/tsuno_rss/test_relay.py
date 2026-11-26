import contextlib
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from xml.etree import ElementTree as ET

import relay_municipality_1824_tsuno as relay


LINK = "https://www.town.tsuno.lg.jp/article?articleId=first"
NEXT_LINK = "https://www.town.tsuno.lg.jp/article?articleId=next"
DATE = "Wed, 25 Nov 2026 15:00:00 GMT"
NEXT_DATE = "Thu, 26 Nov 2026 00:00:00 GMT"


def article(link=LINK, date=DATE, title="募集・お知らせ"):
    return f"<item><title>{title}</title><link>{link}</link><description>本文</description><pubDate>{date}</pubDate></item>"


def feed(*items, channel_date=DATE):
    return (
        f'<rss version="2.0"><channel><title>都農町</title><link>https://www.town.tsuno.lg.jp</link>'
        f'<description>新着</description><pubDate>{channel_date}</pubDate>{"".join(items)}</channel></rss>'
    ).encode()


class RelayTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.output = Path(directory.name) / relay.OUTPUT_FILE
        self.enterContext(contextlib.redirect_stdout(StringIO()))

    def test_repeated_source_and_channel_clock_change_are_byte_identical(self):
        relay.update_feed(feed(article()), self.output)
        first = self.output.read_bytes()
        relay.update_feed(feed(article()), self.output, self.output)
        self.assertEqual(self.output.read_bytes(), first)
        relay.update_feed(feed(article(), channel_date=NEXT_DATE), self.output, self.output)
        self.assertEqual(self.output.read_bytes(), first)
        item = ET.fromstring(first).find("./channel/item")
        self.assertEqual(item.findtext("guid"), LINK)
        self.assertEqual(item.find("guid").get("isPermaLink"), "true")
        self.assertEqual(item.findtext("pubDate"), DATE)
        self.assertEqual(item.findtext("description"), "本文")

    def test_new_item_retains_history_and_same_url_keeps_its_guid(self):
        relay.update_feed(feed(article(), article(NEXT_LINK, NEXT_DATE)), self.output)
        relay.update_feed(feed(article(date=NEXT_DATE, title="追記")), self.output, self.output)
        root = ET.parse(self.output)
        published = {item.findtext("guid"): item.findtext("title") for item in root.findall("./channel/item")}
        self.assertEqual(published, {LINK: "追記", NEXT_LINK: "募集・お知らせ"})
        relay.update_feed(feed(article()), self.output, self.output)
        self.assertIn("追記", self.output.read_text())

    def test_invalid_source_keeps_existing_bytes(self):
        relay.update_feed(feed(article()), self.output)
        first = self.output.read_bytes()
        invalid_sources = (
            ("malformed", b"<rss>"),
            ("non-RSS", b"<Channel><feedType>rss_2.0</feedType></Channel>"),
            ("empty", feed()),
            ("duplicate", feed(article(), article())),
            ("wrong host", feed(article("https://example.com/article?articleId=first"))),
            ("bad date", feed(article(date="invalid"))),
        )
        for label, invalid in invalid_sources:
            with self.subTest(label=label):
                with self.assertRaises((ValueError, ET.ParseError)):
                    relay.update_feed(invalid, self.output, self.output)
                self.assertEqual(self.output.read_bytes(), first)

    def test_http_failure_keeps_existing_bytes_and_passes_rss_accept(self):
        relay.update_feed(feed(article()), self.output)
        first = self.output.read_bytes()
        failure = HTTPError(relay.SOURCE_URL, 503, "test failure", None, None)
        with patch.object(relay, "urlopen", side_effect=failure) as request:
            with patch("sys.argv", ["relay", "--output", str(self.output)]):
                with self.assertRaises(HTTPError):
                    relay.main()
            self.assertEqual(request.call_args.args[0].get_header("Accept"), "application/rss+xml")
        self.assertEqual(self.output.read_bytes(), first)

    def test_invalid_existing_feed_keeps_existing_bytes(self):
        existing = feed(article())
        self.output.write_bytes(existing)
        with self.assertRaisesRegex(ValueError, "Unexpected existing GUID"):
            relay.update_feed(feed(article()), self.output, self.output)
        self.assertEqual(self.output.read_bytes(), existing)


if __name__ == "__main__":
    unittest.main()
