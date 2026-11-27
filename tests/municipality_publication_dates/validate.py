import argparse
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from io import StringIO
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from types import ModuleType
import unittest
from unittest.mock import patch
from xml.etree.ElementTree import parse

ROOT = Path(__file__).resolve().parents[2]
TOWNS = ("1671_hisayama", "1567_tadotsu")
JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 27, 17, 45, tzinfo=JST)


def scraper(town, base_ref=None):
    path = f"scrape_municipality_{town}.py"
    source = (
        (ROOT / path).read_bytes()
        if base_ref is None
        else subprocess.check_output(["git", "show", f"{base_ref}:{path}"], cwd=ROOT)
    )
    module = ModuleType(path.removesuffix(".py"))
    exec(compile(source, path, "exec"), module.__dict__)
    return module


def generate(module, path, data, instant):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz)

    def fetch(url):
        if url == module.DATA_URL and isinstance(data, Exception):
            raise data
        return data if url == module.DATA_URL else "official list"

    with patch.multiple(module, OUTPUT_FILE=str(path), fetch=fetch, datetime=Clock):
        module.main()


def rss_items(path):
    items = {}
    for item in parse(path).findall("./channel/item"):
        guid = item.find("guid")
        link = item.findtext("link")
        assert link not in items and guid.text == link and guid.get("isPermaLink") == "true"
        items[link] = (item.findtext("title"), parsedate_to_datetime(item.findtext("pubDate")))
    return items


def row(number, date):
    return {
        "page_name": f"記事 {number}",
        "url": f"/{number}.html",
        "publish_datetime": date.isoformat() if isinstance(date, datetime) else date,
        "is_category_index": False,
        "is_keitai_page": False,
    }


class PublicationDateTests(unittest.TestCase):
    def test_date_boundary_and_repeat(self):
        release = NOW + timedelta(days=2)
        data = json.dumps([row(2, release), row(1, NOW), row(1, NOW)])
        for town in TOWNS:
            with self.subTest(town=town), TemporaryDirectory() as tmp:
                module = scraper(town)
                target = Path(tmp) / module.OUTPUT_FILE
                future_url = f"https://{module.ALLOWED_DOMAIN}/2.html"
                log = StringIO()
                with redirect_stdout(log):
                    generate(module, target, data, release - timedelta(seconds=1))
                self.assertIn(f"Deferred (future publication date {release.isoformat()})", log.getvalue())
                self.assertIn(future_url, log.getvalue())
                self.assertIn("Deferred rows: 1", log.getvalue())
                self.assertEqual(len(rss_items(target)), 1)
                self.assertNotIn(future_url, rss_items(target))

                generate(module, target, data, release)
                self.assertEqual(len(rss_items(target)), 2)
                self.assertEqual(rss_items(target)[future_url], ("記事 2", release))
                first = target.read_bytes()
                generate(module, target, data, release)
                self.assertEqual(target.read_bytes(), first)

    def test_failed_or_incomplete_input_preserves_output(self):
        data = [row(1, NOW), row(2, NOW - timedelta(days=1))]
        bad_inputs = [
            (OSError("fetch failed"), OSError, "fetch failed"),
            ("{invalid}", ValueError, "Expecting property name"),
            (json.dumps(data + [row(3, "invalid")]), ValueError, "Invalid isoformat"),
            (json.dumps(data + [row(3, "2026-11-29T00:00:00")]), RuntimeError, "no timezone"),
            ("[]", RuntimeError, "JSON missing"),
            (json.dumps([row(3, NOW + timedelta(days=2))]), RuntimeError, "No articles found"),
            (json.dumps(data[:1]), RuntimeError, "Unexpected item count decrease"),
        ]
        for town in TOWNS:
            with TemporaryDirectory() as tmp:
                module = scraper(town)
                target = Path(tmp) / module.OUTPUT_FILE
                generate(module, target, json.dumps(data), NOW)
                initial = target.read_bytes()
                for bad, error, message in bad_inputs:
                    with self.subTest(town=town, reason=message):
                        with self.assertRaisesRegex(error, message):
                            generate(module, target, bad, NOW)
                        self.assertEqual(target.read_bytes(), initial)

    def test_natural_expiry_and_normal_cap(self):
        for town in TOWNS:
            with self.subTest(town=town), TemporaryDirectory() as tmp:
                module = scraper(town)
                target = Path(tmp) / module.OUTPUT_FILE
                data = [row(n, NOW - timedelta(days=n)) for n in range(1, 31)]
                generate(module, target, json.dumps(data), NOW)
                before = rss_items(target)
                newer = row(31, NOW)
                generate(module, target, json.dumps([newer, *data]), NOW)
                after = rss_items(target)
                self.assertEqual(len(after), 30)
                self.assertEqual(len(before.keys() & after.keys()), 29)
                self.assertTrue(all(before[k] == after[k] for k in before.keys() & after.keys()))

                generate(module, target, json.dumps([newer, *data]), NOW + timedelta(days=62))
                aged = rss_items(target)
                self.assertEqual(len(aged), 29)
                self.assertTrue(aged.keys() <= after.keys())


def compare_live(town, base_ref, dest, snapshots):
    current = scraper(town)
    previous = scraper(town, base_ref)
    output = dest / current.OUTPUT_FILE
    if snapshots:
        data = (snapshots / f"{town.split('_')[1]}.json").read_text(encoding="utf-8-sig")
        now = NOW
    else:
        current.fetch(current.SOURCE_URL)
        data = current.fetch(current.DATA_URL)
        now = datetime.now(JST)
    known = json.loads(data)
    cutoff = now - timedelta(days=90)
    print(f"\n{town} at {now.isoformat()}, official JSON rows: {len(known)}")
    (dest / f"{town}.json").write_text(data, encoding="utf-8")

    with TemporaryDirectory() as tmp:
        prior_output = Path(tmp) / current.OUTPUT_FILE
        shutil.copyfile(ROOT / current.OUTPUT_FILE, prior_output)
        baseline = prior_output.read_bytes()
        old = rss_items(prior_output)
        try:
            generate(previous, prior_output, data, now)
        except RuntimeError as exc:
            if str(exc) != "Invalid publication date":
                raise
            assert prior_output.read_bytes() == baseline
            print(f"Before fix: {exc}; previous RSS still has {len(old)} items")
        else:
            print(f"Before fix: generated {len(rss_items(prior_output))} items")

        output.write_bytes(baseline)
        generate(current, output, data, now)
        new = rss_items(output)
        first = output.read_bytes()
        generate(current, output, data, now)
        assert output.read_bytes() == first

        remaining = old.keys() & new.keys()
        print(f"Count: {len(old)} -> {len(new)}; GUIDs preserved: {len(remaining)}; repeat identical")
        available = {}
        deferred = {}
        for item in known:
            if item["is_category_index"] or item["is_keitai_page"]:
                continue
            date = datetime.fromisoformat(item["publish_datetime"])
            url = current.urljoin(current.SOURCE_URL, item["url"])
            if date > now:
                deferred[url] = date
            elif date >= cutoff:
                available.setdefault(url, date)
        expected = sorted(available, key=available.get, reverse=True)[:current.MAX_ITEMS]
        assert list(new) == expected
        assert all(date == available[url] for url, (_, date) in new.items())
        for url, (title, date) in new.items():
            if url not in old:
                print(f"Added | {date.isoformat()} | {title} | {url}")
            elif old[url] != (title, date):
                print(f"Updated with same GUID | {old[url]} -> {new[url]} | {url}")
        for url, (title, date) in old.items():
            if url in new:
                continue
            if date < cutoff:
                reason = "90-day cutoff"
            elif url in available:
                reason = "30-item cap"
            elif url in deferred:
                reason = "future date"
            else:
                reason = "outside current eligible official rows"
            print(f"Removed ({reason}) | {date.isoformat()} | {title} | {url}")

        for release in sorted(set(deferred.values())):
            projected = Path(tmp) / "projected.xml"
            projected.write_bytes(first)
            generate(current, projected, data, release)
            published = rss_items(projected)
            for url, date in deferred.items():
                if date == release and url not in new:
                    assert published[url][1] == release
                    print(f"Published at boundary | {release.isoformat()} | {url}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--snapshots", type=Path)
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PublicationDateTests)
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        raise SystemExit(1)
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
        for key in TOWNS:
            compare_live(key, args.base_ref, args.output, args.snapshots)
