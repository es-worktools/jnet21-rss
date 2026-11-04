import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET
from contextlib import redirect_stdout, contextmanager
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scrape_taisyokukin_topics as s
import stage_taisyokukin as stage
import requests

FIX = Path(__file__).parent / "taisyokukin_fixtures"
HISTORY = (FIX / "history24.xml").read_bytes()
HTML = (FIX / "topics33.html").read_bytes()


def response(body=HTML, status=200, media="text/html", url=s.SOURCE_URL):
    r = requests.Response()
    r.status_code = status
    r.url = url
    r.headers["Content-Type"] = media
    r._content = body
    return r


def modified_html(change):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(HTML, "html.parser")
    change(soup)
    return str(soup).encode()


class Safety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.path = self.dir / s.OUTPUT_FILE
        self.summary = self.dir / "taisyokukin-status.json"
        self.path.write_bytes(HISTORY)

    def execute(self, r=None, error=None):
        with patch.object(requests, "get", side_effect=error, return_value=r if r is not None else response()) as get:
            with redirect_stdout(io.StringIO()):
                status = s.run(self.path, self.summary, get)
            self.assertEqual(get.call_count, 1)
            self.assertEqual(get.call_args.kwargs["allow_redirects"], False)
        return status, json.loads(self.summary.read_text())["result"]

    def blocked(self, r=None, error=None):
        before = self.path.read_bytes()
        status, result = self.execute(r, error)
        self.assertEqual(status, 1)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(list(self.dir.glob(".*.tmp")))
        return result

    def test_normal_all33_and_complete_old_items_in_order(self):
        status, result = self.execute()
        self.assertEqual(status, 0)
        self.assertEqual((result["source_items"], result["rss_items"], result["added_items"]), (33, 33, 9))
        items = ET.fromstring(self.path.read_bytes()).findall("./channel/item")
        old = ET.fromstring(HISTORY).findall("./channel/item")
        s.validate_candidate(self.path.read_bytes(), old)
        self.assertEqual(len(items), 33)  # former 30-item truncation regression
        self.assertEqual(items[-1].findtext("guid"), old[-1].findtext("guid"))
        self.assertEqual(items[0].findtext("{" + s.DC + "}date"), "2026-11-02")
        self.assertIsNone(items[0].find("pubDate"))

    def test_repeat_is_byte_identical(self):
        self.execute()
        first = self.path.read_bytes()
        status, result = self.execute()
        self.assertEqual(status, 0)
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual(first, self.path.read_bytes())

    def test_http403(self): self.blocked(response(status=403))
    def test_http503(self): self.blocked(response(status=503))
    def test_http500(self): self.blocked(response(status=500))
    def test_redirect_not_followed(self): self.blocked(response(status=302))
    def test_wrong_response_url(self): self.blocked(response(url="https://example.org/"))
    def test_timeout(self): self.blocked(error=requests.Timeout("test"))
    def test_connection_error(self): self.blocked(error=requests.ConnectionError("test"))
    def test_http200_empty(self): self.blocked(response(b""))
    def test_http200_maintenance(self): self.blocked(response(b"<html>Maintenance</html>"))
    def test_http200_not_html(self): self.blocked(response(media="application/pdf"))
    def test_invalid_utf8(self): self.blocked(response(HTML + b"\xff"))

    def test_one_parsable_article(self):
        body = '<div id="updatelist2">新着情報一覧<dl class="listdt"><dt>2026.11.2</dt><dd><a href="/one.html">One</a></dd></dl></div>'
        self.blocked(response(body.encode()))

    def test_partial_old_missing_even_if_source_count32(self):
        def change(soup):
            dt = soup.select("#updatelist2 dt")[-1]
            dt.find_next_sibling().decompose(); dt.decompose()
        self.blocked(response(modified_html(change)))

    def test_one_missing_of33_after_first_success(self):
        self.execute()
        def change(soup):
            dt = soup.select_one("#updatelist2 dt")
            dt.find_next_sibling().decompose(); dt.decompose()
        self.blocked(response(modified_html(change)))

    def test_equal_count_replacement(self):
        self.execute()
        def change(soup): soup.select_one("#updatelist2 dd a").string = "訂正された別タイトル"
        self.blocked(response(modified_html(change)))

    def test_duplicate_date_article(self):
        def change(soup):
            dl = soup.select_one("#updatelist2 dl")
            dl.append(copy.deepcopy(dl.dt)); dl.append(copy.deepcopy(dl.dd))
        self.blocked(response(modified_html(change)))

    def test_nested_date_markup_supported(self):
        body = HTML.replace(b"<dt>2026.11.2</dt>", b"<dt><span>2026.</span>11.2</dt>")
        self.assertNotEqual(body, HTML)
        self.assertEqual(self.execute(response(body))[0], 0)

    def test_invalid_calendar_date(self):
        self.blocked(response(HTML.replace(b"2026.11.2</dt>", b"2026.2.30</dt>")))

    def test_date_format_changed(self):
        self.blocked(response(HTML.replace(b"2026.11.2</dt>", b"2026/11/2</dt>")))

    def test_unpaired_dd(self):
        self.blocked(response(modified_html(lambda soup: soup.select_one("#updatelist2 dd").decompose())))

    def test_empty_source_title(self):
        self.blocked(response(modified_html(lambda soup: soup.select_one("#updatelist2 dd").clear())))

    def test_unsafe_url(self):
        def change(soup): soup.select_one("#updatelist2 dd a")["href"] = "javascript:alert(1)"
        self.blocked(response(modified_html(change)))

    def test_http_url_external_pdf_and_no_link_supported(self):
        records = s.parse_articles(HTML)
        self.assertTrue(any(r["link"].startswith("https://www.bousai.go.jp/") for r in records))
        self.assertTrue(any(r["link"] == s.SOURCE_URL for r in records))
        self.assertTrue(s.valid_url("http://example.org/a.pdf"))

    def test_generic_and_long_new_titles_and_guid_compatibility(self):
        records = s.parse_articles(HTML)
        generic = next(r for r in records if r["legacy_title"] == "特設サイト")
        self.assertEqual(generic["title"], "中退共の 特設サイト をリニューアルしました。")
        event = next(r for r in records if r["date"] == "2026-10-29")
        self.assertEqual(event["title"], "「ひがしんビジネスフェア2026」に出展します。")
        expected = hashlib.sha256(f"{event['source_date_literal']}|{event['legacy_title']}|{event['link']}".encode()).hexdigest()
        self.assertEqual(event["guid"], "urn:taisyokukin-topics:" + expected)

    def test_no_cap_above30_or33(self):
        def change(soup):
            dl = soup.select_one("#updatelist2 dl")
            dt = copy.deepcopy(dl.dt); dt.string = "2026.11.4"
            dd = copy.deepcopy(dl.dd); dd.a["href"] = "/new.pdf"; dd.a.string = "新しい公式記事"
            dl.insert(0, dd); dl.insert(0, dt)
        self.assertEqual(self.execute(response(modified_html(change)))[1]["rss_items"], 34)

    def test_invalid_baselines_do_not_fetch(self):
        root = ET.fromstring(HISTORY)
        duplicate = copy.deepcopy(root);duplicate.find("channel").append(copy.deepcopy(root.find("./channel/item")))
        changed = copy.deepcopy(root);changed.find("./channel/link").text = "https://wrong.example/"
        partial = copy.deepcopy(root);partial.find("channel").remove(partial.find("./channel/item"))
        for bad in [b"", b"<rss>", b'<rss version="2.0"><channel/></rss>',
                    ET.tostring(duplicate), ET.tostring(changed), ET.tostring(partial)]:
            with self.subTest(bad=bad[:25]):
                self.path.write_bytes(bad)
                with patch.object(requests, "get") as get, redirect_stdout(io.StringIO()):
                    self.assertEqual(s.run(self.path, self.summary, get), 1)
                    get.assert_not_called()
                self.assertEqual(self.path.read_bytes(), bad)

    def test_missing_baseline_not_bootstrapped(self):
        self.path.unlink()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(s.run(self.path, self.summary, lambda *a, **k: self.fail("network called")), 1)
        self.assertFalse(self.path.exists())

    def test_temp_write_interruption(self):
        with patch.object(s.os, "fsync", side_effect=OSError("interrupted")):
            # receipt also uses fsync; direct process isolates RSS transaction.
            with self.assertRaises(OSError): s.process(self.path, lambda *a, **k: response())
        self.assertEqual(self.path.read_bytes(), HISTORY)
        self.assertFalse(list(self.dir.glob(".*.tmp")))

    def test_temp_creation_failure(self):
        with patch.object(s.tempfile, "NamedTemporaryFile", side_effect=OSError("disk full")):
            with self.assertRaises(OSError): s.process(self.path, lambda *a, **k: response())
        self.assertEqual(self.path.read_bytes(), HISTORY)

    def test_partial_write_then_exception(self):
        real = s.tempfile.NamedTemporaryFile
        @contextmanager
        def interrupted(**kwargs):
            with real(**kwargs) as f:
                class Partial:
                    name = f.name
                    def write(self, data):
                        f.write(data[:20])
                        raise OSError("interrupted during write")
                yield Partial()
        with patch.object(s.tempfile, "NamedTemporaryFile", interrupted):
            with self.assertRaises(OSError): s.process(self.path, lambda *a, **k: response())
        self.assertEqual(self.path.read_bytes(), HISTORY)
        self.assertFalse(list(self.dir.glob(".*.tmp")))

    def test_short_write(self):
        real = s.tempfile.NamedTemporaryFile
        @contextmanager
        def partial(**kwargs):
            with real(**kwargs) as f:
                class Partial:
                    name = f.name
                    def write(self, data): return f.write(data[:20])
                yield Partial()
        with patch.object(s.tempfile, "NamedTemporaryFile", partial):
            with self.assertRaises(OSError): s.process(self.path, lambda *a, **k: response())
        self.assertEqual(self.path.read_bytes(), HISTORY)
        self.assertFalse(list(self.dir.glob(".*.tmp")))

    def test_permission_update_failure(self):
        with patch.object(s.os, "chmod", side_effect=OSError("permission denied")):
            with self.assertRaises(OSError): s.process(self.path, lambda *a, **k: response())
        self.assertEqual(self.path.read_bytes(), HISTORY)
        self.assertFalse(list(self.dir.glob(".*.tmp")))

    def test_original24_only_is_partial_against_verified33(self):
        def change(soup):
            old = {i.findtext("guid") for i in ET.fromstring(HISTORY).findall("./channel/item")}
            dt_list = soup.select("#updatelist2 dt")
            for dt, record in zip(dt_list, s.parse_articles(HTML)):
                if record["guid"] not in old:
                    dt.find_next_sibling().decompose(); dt.decompose()
        result = self.blocked(response(modified_html(change)))
        self.assertEqual(result["code"], "PARTIAL_OR_CHANGED_SOURCE")

    def test_historical24_fingerprint_enforced(self):
        root=ET.fromstring(HISTORY)
        root.find("./channel/item/title").text = "unreviewed change"
        with self.assertRaises(s.GuardError): s.read_baseline(ET.tostring(root))

    def test_all33_match_diagnosed_guids_titles_links_dates(self):
        records = s.parse_articles(HTML)
        expected = json.loads((FIX / "expected33.json").read_text())
        self.assertEqual([(r["guid"],r["legacy_title"],r["link"],r["date"]) for r in records],
                         [(r["original_guid"],r["original_parser_title"],r["original_parser_link"],r["source_publication_date"]) for r in expected])

    def test_replace_failure(self):
        with patch.object(s.os, "replace", side_effect=OSError("replace failed")):
            with self.assertRaises(OSError): s.process(self.path, lambda *a, **k: response())
        self.assertEqual(self.path.read_bytes(), HISTORY)
        self.assertFalse(list(self.dir.glob(".*.tmp")))

    def test_temp_read_validation_failure(self):
        with self.assertRaises(s.GuardError):
            s.atomic_write(self.path, b"<rss>", lambda value: s.read_baseline(value), expected=HISTORY)
        self.assertEqual(self.path.read_bytes(), HISTORY)

    def test_concurrent_baseline_change_is_preserved(self):
        changed = HISTORY + b"\n"
        def get(*a, **k): self.path.write_bytes(changed); return response()
        with self.assertRaises(s.GuardError): s.process(self.path, get)
        self.assertEqual(self.path.read_bytes(), changed)

    def test_source_reorder_of_old_items_is_blocked(self):
        root, old = s.read_baseline(HISTORY)
        records = s.parse_articles(HTML)
        old_guids = {i.findtext("guid") for i in old}
        indices = [n for n,r in enumerate(records) if r["guid"] in old_guids]
        i,j = indices[:2]; records[i],records[j] = records[j],records[i]
        data = s.build_candidate(root,old,records)
        with self.assertRaises(s.GuardError): s.validate_candidate(data,old)

    def test_stale_success_receipt_replaced_on_failure(self):
        self.summary.write_text('{"schema":1,"complete":true,"result":{"status":"updated"}}')
        self.blocked(response(status=403))
        self.assertEqual(json.loads(self.summary.read_text())["result"]["code"], "HTTP_ERROR")

    def test_failed_receipt_write_cannot_authorize_stage(self):
        self.summary.write_text('{"result":{"status":"updated"}}')
        with patch.object(s, "atomic_write", side_effect=OSError("disk failure")), redirect_stdout(io.StringIO()):
            with self.assertRaises(OSError): s.run(self.path, self.summary, lambda *a, **k: response())
        self.assertFalse(self.summary.exists())
        self.assertEqual(self.path.read_bytes(), HISTORY)

    def test_old_item_removed_or_title_changed_rejected(self):
        root, old = s.read_baseline(HISTORY)
        root.find("./channel/item/title").text = "changed"
        with self.assertRaises(s.GuardError): s.validate_candidate(ET.tostring(root), ET.fromstring(HISTORY).findall("./channel/item"))

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.dir, stderr=subprocess.STDOUT)

    def setup_git(self):
        self.git("init", "-b", "main")
        self.git("config", "user.email", "tests@example.invalid")
        self.git("config", "user.name", "test")
        self.git("add", s.OUTPUT_FILE); self.git("commit", "-m", "baseline")

    def test_staging_verified_success(self):
        self.setup_git(); self.execute();stage.stage(self.dir)
        self.assertEqual(self.git("diff", "--cached", "--name-only").decode().strip(), s.OUTPUT_FILE)

    def test_staging_failed_receipt(self):
        self.setup_git(); self.execute(response(status=403))
        with self.assertRaises(ValueError): stage.stage(self.dir)
        self.assertEqual(self.git("diff", "--cached", "--name-only"), b"")

    def test_staging_changed_output(self):
        self.setup_git(); self.execute(); self.path.write_bytes(self.path.read_bytes() + b"\n")
        with self.assertRaises(ValueError): stage.stage(self.dir)

    def test_staging_changed_head_baseline(self):
        self.setup_git(); self.execute(); self.git("add", s.OUTPUT_FILE);self.git("commit", "-m", "external")
        with self.assertRaises(ValueError): stage.stage(self.dir)

    def test_staging_missing_receipt(self):
        self.setup_git()
        with self.assertRaises(FileNotFoundError): stage.stage(self.dir)

    def test_git_rebase_keeps_unrelated_main_update(self):
        self.setup_git()
        self.git("branch", "other")
        self.execute(); stage.stage(self.dir);self.git("commit", "-m", "generated")
        self.git("checkout", "other")
        (self.dir/"unrelated.txt").write_text("keep newer main change")
        self.git("add", "unrelated.txt");self.git("commit", "-m", "unrelated")
        self.git("checkout", "main");self.git("rebase", "other")
        self.assertEqual((self.dir/"unrelated.txt").read_text(), "keep newer main change")
        self.assertEqual(len(ET.fromstring(self.path.read_bytes()).findall("./channel/item")), 33)

    def test_git_rebase_same_feed_conflict_fails(self):
        self.setup_git();self.git("branch", "other")
        self.execute();stage.stage(self.dir);self.git("commit", "-m", "generated")
        self.git("checkout", "other")
        self.path.write_bytes(HISTORY.replace("新着情報</description>".encode(), "別途修正</description>".encode()))
        self.git("add", s.OUTPUT_FILE);self.git("commit", "-m", "same-feed external")
        self.git("checkout", "main")
        with self.assertRaises(subprocess.CalledProcessError): self.git("rebase", "other")
        # Workflow uses set -e, so failed rebase never reaches push.
        self.git("rebase", "--abort")


if __name__ == "__main__": unittest.main()
