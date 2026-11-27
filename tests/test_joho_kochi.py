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


def input_page(count=14, *, first_date="12/31", first_title="案内 0", first_url="/events/0"):
    panels = []
    for section_index, section in enumerate(feed.SECTIONS):
        rows = []
        for i in range(section_index, count, len(feed.SECTIONS)):
            posted, title, url = (first_date, first_title, first_url) if i == 0 else (
                "1/1", f"案内 {i}", f"/events/{i}"
            )
            rows.append(
                f'<li><span>New</span>{posted}-<a href="{url}">{title}</a></li>'
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
        first_old = old_items[0]
        same_url = first_old.findtext("link").replace(
            "https://joho-kochi.or.jp", "http://www.joho-kochi.or.jp"
        ) + "?utm_source=test"
        html = input_page(first_url=same_url, first_title=first_old.findtext("title"))
        html = html.replace('<a href="/events/2">案内 2</a>', '<a href="/events/1">案内 1</a>', 1)
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

    def test_legacy_url_can_carry_a_different_announcement(self):
        old = next(
            item for item in items(self.output) if item.findtext("link").endswith("/lp/mtech-osaka.php")
        )
        url = old.findtext("link")
        run_with_html(self.output, input_page(first_url=url, first_title=old.findtext("title")))
        original = items(self.output)
        self.assertEqual(len([item for item in original if item.findtext("link") == url]), 1)

        new_title = "「機械要素技術展大阪2027」に6社出展します【会期：10/6(水)～10/8(金)】"
        run_with_html(self.output, input_page(first_url=url, first_title=new_title))
        result = items(self.output)
        self.assertEqual(len(result), len(original) + 1)
        self.assertEqual(result[0].findtext("title"), new_title)
        self.assertEqual(result[0].findtext("link"), url)
        self.assertNotEqual(result[0].findtext("guid"), old.findtext("guid"))
        preserved = next(item for item in result if item.findtext("guid") == old.findtext("guid"))
        self.assertEqual(ET.tostring(preserved), ET.tostring(old))

    def test_next_year_same_month_day_has_a_distinct_guid(self):
        run_with_html(self.output, input_page(first_date="10/19", first_title="2026年度 受注企業募集"))
        original = items(self.output)
        run_with_html(self.output, input_page(first_date="10/19", first_title="2027年度 受注企業募集"))
        result = items(self.output)
        self.assertEqual(len(result), len(original) + 1)
        self.assertEqual(result[0].findtext("link"), original[0].findtext("link"))
        self.assertEqual(result[0].findtext("description"), original[0].findtext("description"))
        self.assertNotEqual(result[0].findtext("guid"), original[0].findtext("guid"))

    def test_unchanged_december_announcement_survives_new_year(self):
        run_with_html(self.output, input_page(first_date="12/31", first_title="2月の講習会"))
        original = items(self.output)
        january = input_page(first_date="12/31", first_title="2月の講習会")
        january = january.replace('1/1-<a href="/events/1">案内 1', '1/3-<a href="/events/1">追加案内')
        run_with_html(self.output, january)
        result = items(self.output)
        self.assertEqual(len(result), len(original) + 1)
        self.assertEqual(ET.tostring(result[1]), ET.tostring(original[0]))

    def test_cosmetic_title_correction_keeps_original_item(self):
        run_with_html(self.output, input_page(first_title="「第３回 ＩＴセミナー」開催のお知らせ"))
        original = self.output.read_bytes()
        run_with_html(self.output, input_page(first_title="[受付中] 第3回ITセミナー、開催します！"))
        self.assertEqual(self.output.read_bytes(), original)

    def test_reappearing_url_only_adds_a_different_announcement(self):
        page = input_page(first_title="出展企業募集【説明会：1/11】")
        run_with_html(self.output, page)
        original = items(self.output)
        without_url = page.replace('<li><span>New</span>12/31-<a href="/events/0">'
                                   '出展企業募集【説明会：1/11】</a></li>', "")
        run_with_html(self.output, without_url)
        self.assertEqual(len(items(self.output)), len(original))
        run_with_html(self.output, page)
        self.assertEqual(len(items(self.output)), len(original))
        run_with_html(self.output, without_url)

        run_with_html(self.output, input_page(first_title="出展企業募集【説明会：11/1】"))
        result = items(self.output)
        self.assertEqual(len(result), len(original) + 1)
        self.assertEqual(result[0].findtext("link"), original[0].findtext("link"))
        self.assertNotEqual(result[0].findtext("guid"), original[0].findtext("guid"))

    def test_same_page_can_list_two_invitations_to_the_same_url(self):
        html = input_page(first_date="1/1", first_title="発注企業募集")
        html = html.replace('<a href="/events/1">案内 1</a>', '<a href="/events/0">受注企業募集</a>')
        run_with_html(self.output, html)
        same_url = [item for item in items(self.output) if item.findtext("link").endswith("/events/0")]
        self.assertEqual({item.findtext("title") for item in same_url}, {"発注企業募集", "受注企業募集"})
        self.assertEqual(len({item.findtext("guid") for item in same_url}), 2)

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
