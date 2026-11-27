from pathlib import Path
import os
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import scrape_joho_kochi as feed


def input_page(count=14, *, first_date="12/31"):
    panels = []
    for section_index, section in enumerate(feed.SECTIONS):
        rows = []
        for i in range(section_index, count, len(feed.SECTIONS)):
            posted = first_date if i == 0 else "1/1"
            rows.append(
                f'<li><span>New</span>{posted}-<a href="/events/{i}">案内 {i}</a></li>'
            )
        panels.append(
            f'<div class="panel"><div class="panel-heading">{section}</div>'
            f'<div class="panel-body"><ul>{"".join(rows)}</ul></div></div>'
        )
    return '<meta charset="utf-8">' + "".join(panels)


def items(path):
    return ET.parse(path).findall("./channel/item")


def run_with_html(output, html):
    with patch.object(feed.requests, "get") as get:
        get.return_value.__enter__.return_value.content = html.encode()
        feed.generate(output)


class PreservationTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.output = Path(directory.name) / feed.OUTPUT_FILE
        shutil.copyfile(ROOT / feed.OUTPUT_FILE, self.output)

    def test_preserves_history_deduplicates_and_is_idempotent(self):
        old_items = items(self.output)
        first_old_url = old_items[0].findtext("link")
        html = input_page().replace("/events/1", first_old_url.replace(
            "https://joho-kochi.or.jp", "http://www.joho-kochi.or.jp"
        ) + "?utm_source=test", 1)
        html = html.replace('href="/events/2"', 'href="/events/0"', 1)
        run_with_html(self.output, html)
        result = items(self.output)
        self.assertEqual(len(result), len(old_items) + 12)
        self.assertEqual(
            [ET.tostring(item) for item in result[-len(old_items):]],
            [ET.tostring(item) for item in old_items],
        )
        self.assertEqual(len({item.findtext("guid") for item in result}), len(result))
        before = self.output.read_bytes()
        before_mtime = self.output.stat().st_mtime_ns
        run_with_html(self.output, html)
        self.assertEqual(self.output.read_bytes(), before)
        self.assertEqual(self.output.stat().st_mtime_ns, before_mtime)

    def test_reused_url_with_a_new_date_can_carry_a_new_announcement(self):
        run_with_html(self.output, input_page())
        first = items(self.output)
        run_with_html(self.output, input_page(first_date="1/2"))
        second = items(self.output)
        self.assertEqual(len(second), len(first) + 1)
        self.assertEqual(second[0].findtext("link"), first[0].findtext("link"))
        self.assertNotEqual(second[0].findtext("guid"), first[0].findtext("guid"))

    def test_http_error_preserves_rss(self):
        before = self.output.read_bytes()
        with patch.object(feed.requests, "get") as get:
            response = get.return_value.__enter__.return_value
            response.raise_for_status.side_effect = requests.HTTPError("503")
            with self.assertRaises(requests.HTTPError):
                feed.generate(self.output)
        self.assertEqual(self.output.read_bytes(), before)

    def test_invalid_page_empty_and_abrupt_drop_preserve_rss(self):
        run_with_html(self.output, input_page(20))
        before = self.output.read_bytes()
        for html in (
            "<html>Temporary maintenance</html>",
            input_page().replace(">セミナー<", ">見出し変更<"),
            input_page().replace("12/31-", "日付不明"),
            input_page(0),
            input_page(10),
        ):
            with self.subTest(html=html[:100]):
                with self.assertRaises(ValueError):
                    run_with_html(self.output, html)
                self.assertEqual(self.output.read_bytes(), before)

    def test_normal_reduction_preserves_all_items(self):
        run_with_html(self.output, input_page())
        before = items(self.output)
        run_with_html(self.output, input_page(11))
        self.assertEqual([ET.tostring(item) for item in items(self.output)],
                         [ET.tostring(item) for item in before])


def validate_live():
    output = Path(os.environ["RUNNER_TEMP"]) / "joho-kochi-preview.xml"
    shutil.copyfile(ROOT / feed.OUTPUT_FILE, output)
    original = items(output)
    response = requests.get(feed.SOURCE_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    response.raise_for_status()
    with patch.object(feed.requests, "get", return_value=response):
        feed.generate(output)
        result = items(output)
        assert len(result) > len(original), "The source did not add any announcements"
        assert any("となりの情シス交流会" in item.findtext("title", "") for item in result)
        assert [ET.tostring(item) for item in result[-len(original):]] == [
            ET.tostring(item) for item in original
        ], "Existing items changed"
        assert len({item.findtext("guid") for item in result}) == len(result)
        before = output.read_bytes()
        before_mtime = output.stat().st_mtime_ns
        feed.generate(output)
        assert output.read_bytes() == before
        assert output.stat().st_mtime_ns == before_mtime
    print(f"Live preview verified: {len(original)} original items, {len(result) - len(original)} added")


if __name__ == "__main__":
    if sys.argv[1:] == ["--live"]:
        validate_live()
    else:
        unittest.main()
