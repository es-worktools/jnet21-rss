import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

import scrape_support_0298_hiroshima_yorozu as rss


def record(number=1, path="/news/first/", title="お知らせ", stamp="2026-11-16T10:42:03+09:00", section=0):
    return {"guid": rss.GUID_PREFIX + str(number), "title": title, "url": rss.BASE + path,
            "published": stamp, "categories": [rss.SECTIONS[section].label]}


def doc(inside, head="", classes=""):
    return (f"<html><head>{head}</head><body class='{classes}'>"
            "<div class='c-important-news'><time datetime='2026-11-16T10:42:03+09:00'>別記事</time></div>"
            f"<main id='main-content'>{inside}</main></body></html>").encode()


def card(href, title="記事名", stamp=None):
    time = f"<time datetime='{stamp}'>日付</time>" if stamp else ""
    return (f"<li class='p-archive__item'><a class='p-archive__card' href='{href}'>"
            f"<div class='p-archive__meta'>{time}</div><h2 class='p-archive__item-title'>{title}</h2></a></li>")


def listing(section, cards, next_page=None):
    classes = " ".join(section.css.split(".")[1:])
    next_link = (f"<nav class='p-archive__pagination'><a class='next' href='{next_page}'>次へ</a></nav>"
                 if next_page else "")
    return doc(f"<div class='{classes}'><ul class='p-archive__list'>{cards}</ul>{next_link}</div>")


def post(path, number=1, kind="news", short=None, time="", title="個別記事名"):
    element = "news" if kind == "news" else "seminar"
    head = f"<link rel='canonical' href='{path}'><link rel='shortlink' href='/?p={short or number}'>"
    inside = (f"<article class='p-single__{element} post-{number} seminar_kind-{kind}'>"
              f"<h1 class='p-single__title'>{title}</h1>{time}</article>")
    return doc(inside, head, f"single postid-{number}")


def sitemap_xml(root, child, values):
    items = "".join(f"<{child}><loc>{rss.BASE}{value}</loc></{child}>" for value in values)
    return f'<{root} xmlns="{rss.SITEMAP[1:-1]}">{items}</{root}>'.encode()


class ExtractionTests(unittest.TestCase):
    def test_normalizes_tracking_fragments_host_percent_case_and_slash(self):
        variants = ["/news/%e3%81%82/?utm_source=x#part", "http://yorozu-hiroshima.go.jp/news/あ",
                    "/news/%E3%81%82/"]
        self.assertEqual({rss.article_url(v, rss.BASE, "news") for v in variants},
                         {rss.BASE + "/news/%E3%81%82/"})

    def test_rejects_external_encoded_slash_and_non_article(self):
        for url in ("https://example.org/news/a/", "/news/a%2Fb/", "/news/page/2/", "/news/"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                rss.article_url(url, rss.BASE, "news")

    def test_same_wp_id_for_distinct_self_canonical_links(self):
        paths = ["/news/first/", "/onestop/news/first/", "/productivity/news/first/"]
        articles = [rss.detail(rss.BASE + path, "news", lambda url, types: (url, post(path, 926))) for path in paths]
        self.assertEqual({item["guid"] for item in articles}, {rss.GUID_PREFIX + "926"})
        self.assertEqual(len({item["url"] for item in articles}), 3)
        self.assertTrue(all(item["published"] is None for item in articles))

    def test_conflicting_identity_stops(self):
        url = rss.BASE + "/news/first/"
        with self.assertRaisesRegex(ValueError, "conflicting WordPress IDs"):
            rss.detail(url, "news", lambda url, types: (url, post(url, 1, short=2)))

    def test_seminar_date_is_never_publication_date(self):
        url = rss.BASE + "/onestop/seminar/first/"
        stamp = ("<p class='p-single__seminar-date'>開催日 11月26日</p>"
                 "<time datetime='2026-11-26T10:00:00+09:00'>開催日</time>")
        result = rss.detail(url, "seminar", lambda url, types: (url, post(url, kind="seminar", time=stamp)))
        self.assertIsNone(result["published"])

    def test_news_uses_only_individual_news_metadata(self):
        url = rss.BASE + "/news/first/"
        stamp = "<div class='p-single__news-hero-meta'><time datetime='2026-11-12T15:34:00+09:00'>公開日</time></div>"
        result = rss.detail(url, "news", lambda url, types: (url, post(url, time=stamp)))
        self.assertEqual(result["published"], "2026-11-12T15:34:00+09:00")

    def test_pagination_keeps_short_title_and_cross_list_link(self):
        section = rss.SECTIONS[2]
        urls = {
            section.path: listing(section, card("/onestop/seminar/first/", "DX"), section.path + "page/2/"),
            section.path + "page/2/": listing(section, card("/productivity/seminar/second/")),
        }
        rows = rss.archive(section, lambda url, types: (url, urls[url.removeprefix(rss.BASE)]))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[rss.BASE + "/onestop/seminar/first/"], ("DX", None))

    def test_archive_without_cards_stops_even_with_global_notice(self):
        section = rss.SECTIONS[0]
        with self.assertRaisesRegex(ValueError, "no article cards"):
            rss.archive(section, lambda url, types: (url, listing(section, "")))

    def test_pagination_that_repeats_stops(self):
        section = rss.SECTIONS[0]
        same = card("/news/first/")
        pages = {"/news/": listing(section, same, "/news/page/2/"), "/news/page/2/": listing(section, same)}
        with self.assertRaisesRegex(ValueError, "without progress"):
            rss.archive(section, lambda url, types: (url, pages[url.removeprefix(rss.BASE)]))


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.news = "/news/first/"
        self.seminar = "/onestop/seminar/seo/"
        self.lesson = "/onestop/1on1/ai/"
        self.alias = "/productivity/seminar/seo-alias/"
        self.news_stamp = "2026-11-16T10:42:03+09:00"
        news_map, seminar_map = "/wp-sitemap-posts-news-1.xml", "/wp-sitemap-posts-seminar-1.xml"
        self.docs = {
            "/wp-sitemap.xml": sitemap_xml("sitemapindex", "sitemap", [news_map, seminar_map]),
            news_map: sitemap_xml("urlset", "url", [self.news]),
            seminar_map: sitemap_xml("urlset", "url", [self.seminar, self.lesson]),
            self.news: post(self.news, 1),
            self.seminar: post(self.seminar, 2, "seminar"),
            self.alias: post(self.alias, 2, "seminar"),
            self.lesson: post(self.lesson, 3, "1on1"),
        }
        for section, article in zip(rss.SECTIONS, [self.news, self.seminar, self.alias, self.lesson, self.lesson]):
            self.docs[section.path] = listing(section, card(article, stamp=self.news_stamp))

    def fetch(self, url, media):
        return url, self.docs[url.removeprefix(rss.BASE)]

    def test_id_unifies_aliases_and_categories_with_sitemap(self):
        records = rss.collect(self.fetch)
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0]["published"], self.news_stamp)
        self.assertEqual(records[0]["title"], "個別記事名")
        self.assertEqual(records[1]["url"], rss.BASE + self.seminar)
        self.assertEqual(records[1]["categories"], [rss.SECTIONS[1].label, rss.SECTIONS[2].label])
        self.assertEqual(records[2]["categories"], [rss.SECTIONS[3].label, rss.SECTIONS[4].label])

    def test_missing_listing_item_stops_against_sitemap(self):
        unseen = "/news/unseen/"
        self.docs[unseen] = post(unseen, 5)
        self.docs["/wp-sitemap-posts-news-1.xml"] = sitemap_xml("urlset", "url", [self.news, unseen])
        with self.assertRaisesRegex(ValueError, "archive and sitemap disagree"):
            rss.collect(self.fetch)

    def test_failed_article_stops_entire_collection(self):
        del self.docs[self.lesson]
        with self.assertRaises(KeyError):
            rss.collect(self.fetch)

    def test_unrelated_canonical_target_stops(self):
        self.docs[self.alias] = post(self.seminar, 15, "seminar")
        with self.assertRaisesRegex(ValueError, "canonical target"):
            rss.collect(self.fetch)

    def test_conflicting_publication_dates_stop(self):
        stamp = "<div class='p-single__news-hero-meta'><time datetime='2026-11-01T10:42:03+09:00'>日付</time></div>"
        self.docs[self.news] = post(self.news, 1, time=stamp)
        with self.assertRaisesRegex(ValueError, "publication time disagree"):
            rss.collect(self.fetch)


class HistoryTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.first = record()
        self.second = record(2, "/news/second/")

    def build(self, source, out, live, **options):
        rss.write_bundle(self.root / source, self.root / out, collect_live=lambda: live, **options)
        return self.root / out

    def review(self, decisions):
        review = self.root / "review.json"
        review.write_text(json.dumps(decisions), encoding="utf-8")
        return review

    def test_repeated_run_is_byte_identical_even_with_listing_reorder(self):
        a = self.build("none", "a", [self.first, self.second], preview=True)
        b = self.build("a", "b", [self.second, self.first])
        for path in (rss.FEED, rss.HISTORY):
            self.assertEqual((a / path).read_bytes(), (b / path).read_bytes())

    def test_cutover_suppresses_known_and_never_creates_empty_feed(self):
        a = self.build("none", "a", [self.first], review=self.review({self.first["guid"]: "history"}))
        self.assertFalse((a / rss.FEED).exists())
        b = self.build("a", "b", [self.first, self.second])
        nodes = ET.parse(b / rss.FEED).findall("./channel/item")
        self.assertEqual([node.findtext("guid") for node in nodes], [self.second["guid"]])
        self.assertEqual(nodes[0].find("guid").attrib, {"isPermaLink": "false"})
        self.assertEqual(len(rss.read_history(b)), 2)

    def test_cutover_requires_a_complete_review(self):
        with self.assertRaisesRegex(ValueError, "cover every"):
            self.build("none", "a", [self.first, self.second], review=self.review({self.first["guid"]: "publish"}))
        self.assertFalse((self.root / "a").exists())

    def test_without_initialized_history_normal_mode_stops(self):
        with self.assertRaisesRegex(ValueError, "approved review"):
            self.build("none", "a", [self.first])

    def test_reappearance_retains_guid_and_omitted_history_survives(self):
        a = self.build("none", "a", [self.first, self.second], preview=True)
        b = self.build("a", "b", [self.second])
        self.assertEqual((a / rss.FEED).read_bytes(), (b / rss.FEED).read_bytes())
        renamed = {**self.first, "url": rss.BASE + "/news/renamed/", "title": "修正後の見出し"}
        c = self.build("b", "c", [renamed, self.second])
        guids = [item["guid"] for item in rss.read_history(c)]
        self.assertEqual(guids, [self.first["guid"], self.second["guid"]])
        self.assertIn(renamed["url"], (c / rss.FEED).read_text(encoding="utf-8"))

    def test_previous_url_reassigned_to_different_id_stops(self):
        a = self.build("none", "a", [self.first], preview=True)
        reused = {**self.first, "guid": rss.GUID_PREFIX + "3"}
        with self.assertRaisesRegex(ValueError, "different WordPress ID"):
            self.build("a", "b", [reused])
        self.assertTrue((a / rss.FEED).exists())
        self.assertFalse((self.root / "b").exists())

    def test_empty_and_fetch_error_both_leave_baseline_intact(self):
        a = self.build("none", "a", [self.first], preview=True)
        expected = (a / rss.FEED).read_bytes()
        with self.assertRaisesRegex(ValueError, "empty"):
            self.build("a", "b", [])
        with self.assertRaises(OSError):
            def unavailable():
                raise OSError("temporary HTTP failure")
            rss.write_bundle(a, self.root / "b", collect_live=unavailable)
        self.assertEqual((a / rss.FEED).read_bytes(), expected)
        self.assertFalse((self.root / "b").exists())

    def test_missing_or_corrupt_prior_rss_prevents_even_a_fetch(self):
        a = self.build("none", "a", [self.first], preview=True)
        for bad in (None, b"<rss/>"):
            with self.subTest(bad=bad):
                if bad is None:
                    (a / rss.FEED).unlink()
                else:
                    (a / rss.FEED).write_bytes(bad)
                with self.assertRaisesRegex(ValueError, "does not match history"):
                    rss.write_bundle(a, self.root / "b", collect_live=lambda: self.fail("baseline was invalid"))

    def test_duplicate_new_urls_refused(self):
        with self.assertRaisesRegex(ValueError, "shared URL"):
            self.build("none", "a", [self.first, {**self.first, "guid": rss.GUID_PREFIX + "3"}], preview=True)

    def test_approved_visible_item_does_not_disappear_from_public_rss(self):
        a = self.build("none", "a", [self.first, self.second],
                       review=self.review({self.first["guid"]: "publish", self.second["guid"]: "history"}))
        b = self.build("a", "b", [self.second])
        self.assertEqual((a / rss.FEED).read_bytes(), (b / rss.FEED).read_bytes())


if __name__ == "__main__":
    unittest.main()
