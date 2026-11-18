"""Build the Hiroshima Yorozu RSS and its history in an isolated directory."""

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

BASE = "https://www.yorozu-hiroshima.go.jp"
HOST = urlsplit(BASE).hostname
FEED = Path("support-0298-hiroshima-yorozu.xml")
HISTORY = Path("support_0298_hiroshima_yorozu/history.json")
REVIEW = Path("cutover-review.json")
SITEMAP = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
GUID_PREFIX = "urn:hiroshima-yorozu:wp:"
MAX_PAGES = 30
MAX_BYTES = 4_000_000


@dataclass(frozen=True)
class Section:
    path: str
    label: str
    css: str
    kind: str


SECTIONS = (
    Section("/news/", "お知らせ", ".p-archive--news", "news"),
    Section("/onestop/seminar/", "ワンストップ・セミナー", ".p-archive--seminar.p-archive--onestop", "seminar"),
    Section("/productivity/seminar/", "生産性向上・セミナー", ".p-archive--seminar.p-archive--seisansei", "seminar"),
    Section("/onestop/1on1/", "ワンストップ・マンツーマン勉強会", ".p-archive--seminar.p-archive--onestop", "1on1"),
    Section("/productivity/1on1/", "生産性向上・マンツーマン勉強会", ".p-archive--seminar.p-archive--seisansei", "1on1"),
)
LABELS = {section.label: section.kind for section in SECTIONS}
ARTICLE = re.compile(r"/(?:(?:onestop|productivity)/)?(news|seminar|1on1)/([^/]+)/")
WP_ID = re.compile(r"[1-9][0-9]*")


def official_parts(value):
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or parts.netloc.lower() not in (HOST, HOST.removeprefix("www.")):
        raise ValueError(f"URL outside official site: {value}")
    return parts


def article_url(href, origin, kind):
    parts = official_parts(urljoin(origin, href))
    path = parts.path.rstrip("/") + "/"
    match = ARTICLE.fullmatch(path)
    if not match or match[1] != kind:
        raise ValueError(f"unexpected {kind} article URL: {href}")
    slug = unquote(match[2], errors="strict")
    if slug in (".", "..", "page", "feed", "embed") or re.search(r"[/\\\x00-\x20\x7f]", slug):
        raise ValueError(f"invalid article slug: {href}")
    return BASE + path[:match.start(2)] + quote(slug, safe="-._~") + "/"


class OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parts = official_parts(newurl)
        if parts.scheme != "https":
            raise ValueError(f"insecure redirect: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = build_opener(OfficialRedirect())


def fetch(url, media_type):
    request = Request(url, headers={"User-Agent": "RSS Monitor 0298 (GitHub public feed)"})
    with OPENER.open(request, timeout=20) as response:
        if response.status != 200 or response.headers.get_content_type() not in media_type:
            raise ValueError(f"unexpected response: {response.status} {response.url}")
        raw = response.read(MAX_BYTES + 1)
        if not raw or len(raw) > MAX_BYTES:
            raise ValueError(f"invalid response length: {response.url}")
        return response.url, raw


def html(url, client):
    final, raw = client(url, ("text/html", "application/xhtml+xml"))
    return final, BeautifulSoup(raw, "html.parser", from_encoding="utf-8")


def label_text(tag):
    return re.sub(r"[ \t\r\n\f]+", " ", tag.get_text(" ", strip=True)).strip() if tag else ""


def published(value):
    dt = datetime.fromisoformat(value)
    if dt.utcoffset() is None or "T" not in value:
        raise ValueError(f"publication timestamp lacks time or zone: {value}")
    return dt.isoformat(timespec="seconds")


def timestamp_nodes(nodes):
    values = {published(node["datetime"]) for node in nodes}
    if len(values) > 1:
        raise ValueError("conflicting publication timestamps")
    return next(iter(values), None)


def archive(section, client):
    rows = {}
    for page in range(1, MAX_PAGES + 1):
        path = section.path if page == 1 else f"{section.path}page/{page}/"
        url = BASE + path
        final, soup = html(url, client)
        wrapper = soup.select_one(f"main#main-content {section.css}")
        if final != url or not wrapper:
            raise ValueError(f"archive unavailable or changed: {url}")
        cards = wrapper.select(".p-archive__list li.p-archive__item")
        if not cards:
            raise ValueError(f"archive contains no article cards: {url}")
        before = len(rows)
        for item in cards:
            link = item.select_one("a.p-archive__card[href]")
            title = label_text(item.select_one("h2.p-archive__item-title"))
            if not link or not title:
                raise ValueError(f"malformed article card: {url}")
            pretty = article_url(link["href"], url, section.kind)
            stamp = timestamp_nodes(item.select(".p-archive__meta time[datetime]")) if section.kind == "news" else None
            if pretty in rows and rows[pretty] != (title, stamp):
                raise ValueError(f"conflicting archive cards: {pretty}")
            rows[pretty] = (title, stamp)
        if page > 1 and len(rows) == before:
            raise ValueError(f"archive pagination repeats without progress: {url}")
        next_links = wrapper.select(".p-archive__pagination a.next[href]")
        next_url = f"{BASE}{section.path}page/{page + 1}/"
        if not next_links:
            return rows
        if len(next_links) != 1 or urljoin(url, next_links[0]["href"]) != next_url:
            raise ValueError(f"archive next link changed: {url}")
    raise ValueError(f"archive exceeds {MAX_PAGES} pages: {section.path}")


def xml_document(url, client, root):
    final, raw = client(url, ("application/xml", "text/xml"))
    if final != url or b"<!DOCTYPE" in raw.upper():
        raise ValueError(f"unexpected sitemap response: {url}")
    xml = ET.fromstring(raw)
    if xml.tag != SITEMAP + root:
        raise ValueError(f"unexpected sitemap root: {url}")
    return xml


def sitemap(client):
    index = xml_document(BASE + "/wp-sitemap.xml", client, "sitemapindex")
    expected = {"news": set(), "seminar": set(), "1on1": set()}
    for post_type, kinds in (("news", ("news",)), ("seminar", ("seminar", "1on1"))):
        pages = {}
        for node in index.findall(f"{SITEMAP}sitemap/{SITEMAP}loc"):
            value = node.text or ""
            match = re.fullmatch(re.escape(BASE) + rf"/wp-sitemap-posts-{post_type}-([1-9][0-9]*)\.xml", value)
            if match:
                pages[int(match[1])] = value
        if not pages or sorted(pages) != list(range(1, len(pages) + 1)) or len(pages) > MAX_PAGES:
            raise ValueError(f"missing or incomplete {post_type} sitemap index")
        for url in pages.values():
            xml = xml_document(url, client, "urlset")
            entries = xml.findall(f"{SITEMAP}url/{SITEMAP}loc")
            if not entries:
                raise ValueError(f"empty sitemap: {url}")
            for loc in entries:
                path = urlsplit(loc.text or "").path
                match = ARTICLE.fullmatch(path)
                if not match or match[1] not in kinds:
                    raise ValueError(f"unclassified sitemap article: {loc.text}")
                expected[match[1]].add(article_url(loc.text, url, match[1]))
    return expected


def detail(url, kind, client):
    final, soup = html(url, client)
    root = soup.select_one("main#main-content article.p-single__news" if kind == "news"
                           else "main#main-content article.p-single__seminar")
    title = label_text(root.select_one("h1.p-single__title")) if root else ""
    canonical = soup.select("head link[rel~=canonical][href]")
    shortlink = soup.select("head link[rel~=shortlink][href]")
    if not root or not title or not soup.body or len(canonical) != 1 or len(shortlink) != 1:
        raise ValueError(f"missing title or WordPress identity metadata: {url}")
    if kind != "news" and f"seminar_kind-{kind}" not in root.get("class", []):
        raise ValueError(f"unexpected seminar type: {url}")
    ids = [c.removeprefix("postid-") for c in soup.body.get("class", []) if c.startswith("postid-")]
    short = official_parts(urljoin(final, shortlink[0]["href"]))
    if (len(ids) != 1 or not WP_ID.fullmatch(ids[0]) or short.path != "/"
            or parse_qs(short.query) != {"p": ids} or f"post-{ids[0]}" not in root.get("class", [])):
        raise ValueError(f"conflicting WordPress IDs: {url}")
    article_url(final, url, kind)
    link = article_url(canonical[0]["href"], final, kind)
    pubdate = timestamp_nodes(root.select(".p-single__news-hero-meta time[datetime]")) if kind == "news" else None
    return {"guid": GUID_PREFIX + ids[0], "title": title, "url": link, "published": pubdate}


def link_priority(url):
    return (urlsplit(url).path.count("/"), "/productivity/" in url, url)


def collect(client=fetch):
    archives = {section: archive(section, client) for section in SECTIONS}
    mapped = sitemap(client)
    details = {kind: {} for kind in mapped}
    for kind, catalog in mapped.items():
        links = catalog | {url for section, rows in archives.items() if section.kind == kind for url in rows}
        records = {url: detail(url, kind, client) for url in sorted(links)}
        for url, record in records.items():
            canonical = record["url"]
            if canonical == url:
                continue
            target = records.get(canonical) or detail(canonical, kind, client)
            if target != record:
                raise ValueError(f"canonical target does not confirm the same article: {url}")
        details[kind] = records

    articles = {}
    mismatches = 0
    for section, rows in archives.items():
        for url, (title, stamp) in rows.items():
            record = details[section.kind][url]
            guid = record["guid"]
            mismatches += title != record["title"]
            if stamp and record["published"] and stamp != record["published"]:
                raise ValueError(f"archive and article publication time disagree: {url}")
            candidate = {**record, "published": record["published"] or stamp}
            if guid not in articles:
                articles[guid] = {**candidate, "categories": [section.label]}
                continue
            current = articles[guid]
            if (current["title"] != candidate["title"] or current["published"] != candidate["published"]
                    or LABELS[current["categories"][0]] != section.kind):
                raise ValueError(f"inconsistent copies of article: {guid}")
            current["url"] = min(current["url"], candidate["url"], key=link_priority)
            if section.label not in current["categories"]:
                current["categories"].append(section.label)

    for kind, urls in mapped.items():
        listed = {item["guid"] for item in articles.values() if LABELS[item["categories"][0]] == kind}
        indexed = {details[kind][url]["guid"] for url in urls}
        if listed != indexed:
            raise ValueError(f"{kind} archive and sitemap disagree: archive-only={sorted(listed - indexed)}, "
                             f"sitemap-only={sorted(indexed - listed)}")
        for url in urls:
            record = details[kind][url]
            item = articles[record["guid"]]
            if record["title"] != item["title"] or (record["published"] and record["published"] != item["published"]):
                raise ValueError(f"sitemap copy metadata disagrees: {url}")
            item["url"] = min(item["url"], record["url"], key=link_priority)
    if not articles:
        raise ValueError("no verified articles")
    print("ARCHIVES", {section.label: len(rows) for section, rows in archives.items()})
    print("SITEMAP", {kind: len(rows) for kind, rows in mapped.items()}, "TITLE_DIFFERENCES", mismatches)
    return list(articles.values())


def validate(items):
    seen_guids = set()
    seen_urls = set()
    for item in items:
        if set(item) != {"guid", "title", "url", "published", "categories", "visible"}:
            raise ValueError("unexpected history item fields")
        guid, link, categories = item["guid"], item["url"], item["categories"]
        if not isinstance(guid, str) or not guid.startswith(GUID_PREFIX) or not WP_ID.fullmatch(guid[len(GUID_PREFIX):]):
            raise ValueError(f"invalid GUID: {guid}")
        if (not isinstance(categories, list) or not categories or len(set(categories)) != len(categories)
                or any(category not in LABELS for category in categories)
                or len({LABELS[category] for category in categories}) != 1):
            raise ValueError(f"invalid categories: {guid}")
        kind = LABELS[categories[0]]
        if (not isinstance(item["title"], str) or not item["title"].strip()
                or type(item["visible"]) is not bool or link != article_url(link, BASE, kind)):
            raise ValueError(f"invalid article fields: {guid}")
        stamp = item["published"]
        if stamp is not None and (kind != "news" or published(stamp) != stamp):
            raise ValueError(f"invalid publication field: {guid}")
        if guid in seen_guids or link in seen_urls:
            raise ValueError(f"duplicate GUID or shared URL: {guid} {link}")
        seen_guids.add(guid)
        seen_urls.add(link)


def render(items):
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "広島県よろず支援拠点"
    ET.SubElement(channel, "link").text = BASE + "/"
    ET.SubElement(channel, "description").text = "公式のお知らせ・セミナー・マンツーマン勉強会"
    for item in items:
        if not item["visible"]:
            continue
        entry = ET.SubElement(channel, "item")
        ET.SubElement(entry, "title").text = item["title"]
        ET.SubElement(entry, "link").text = item["url"]
        ET.SubElement(entry, "guid", {"isPermaLink": "false"}).text = item["guid"]
        for category in item["categories"]:
            ET.SubElement(entry, "category").text = category
        if item["published"]:
            ET.SubElement(entry, "pubDate").text = format_datetime(datetime.fromisoformat(item["published"]))
    if not channel.findall("item"):
        return None
    ET.indent(rss, space="  ")
    data = ET.tostring(rss, "utf-8", xml_declaration=True) + b"\n"
    ET.fromstring(data)
    return data


def read_history(root):
    raw = json.loads((root / HISTORY).read_text(encoding="utf-8"))
    if set(raw) != {"version", "items"} or raw["version"] != 1 or not isinstance(raw["items"], list) or not raw["items"]:
        raise ValueError("history empty or unsupported")
    items = raw["items"]
    validate(items)
    public = render(items)
    rss = root / FEED
    if (public is None and rss.exists()) or (public is not None and (not rss.is_file() or rss.read_bytes() != public)):
        raise ValueError("existing RSS does not match history; restore the last verified pair")
    return items


def merge(old, live, decisions=None):
    prior = {item["guid"]: item for item in old}
    current = {item["guid"]: item for item in live}
    new_urls = {item["url"]: item["guid"] for item in live}
    if any(new_urls.get(item["url"], guid) != guid for guid, item in prior.items()):
        raise ValueError("a previously tracked article URL now belongs to a different WordPress ID")
    if not live or len(current) != len(live):
        raise ValueError("empty or duplicate current article input")
    if decisions is not None and (set(decisions) != set(current)
                                  or any(status not in ("publish", "history") for status in decisions.values())):
        raise ValueError("review must cover every currently verified GUID with publish/history")
    new = [{**item, "visible": decisions[item["guid"]] == "publish" if decisions is not None else True}
           for item in live if item["guid"] not in prior]
    retained = []
    for guid, previous in prior.items():
        item = current.get(guid)
        if not item:
            retained.append(previous)
            continue
        if LABELS[item["categories"][0]] != LABELS[previous["categories"][0]]:
            raise ValueError(f"article type changed for a previously tracked ID: {guid}")
        retained.append({**item, "visible": previous["visible"], "published": previous["published"] or item["published"]})
    result = new + retained
    validate(result)
    return result


def write_bundle(source, output, *, preview=False, review=None, collect_live=collect):
    source, output = source.resolve(), output.resolve()
    if output == source or output.exists():
        raise ValueError("output must be a new isolated directory")
    existing = (source / HISTORY).exists() or (source / FEED).exists()
    if existing and (preview or review is not None):
        raise ValueError("bootstrap cannot replace a prior history or RSS")
    if not existing and not preview and review is None:
        raise ValueError("approved review required to initialize history")
    old = read_history(source) if existing else []
    live = collect_live()
    decisions = json.loads(review.read_text(encoding="utf-8")) if review else None
    if review is not None and not isinstance(decisions, dict):
        raise ValueError("review must be a GUID-to-decision JSON object")
    items = merge(old, live, decisions)
    public = render(items)
    output.mkdir(parents=True)
    (output / HISTORY).parent.mkdir()
    (output / HISTORY).write_text(json.dumps({"version": 1, "items": items}, ensure_ascii=False, indent=2) + "\n",
                                  encoding="utf-8")
    if public is not None:
        (output / FEED).write_bytes(public)
    if preview:
        (output / REVIEW).write_text(json.dumps({item["guid"]: "review" for item in items}, indent=2) + "\n",
                                     encoding="utf-8")
    if read_history(output) != items:
        raise ValueError("candidate history round trip failed")
    prior = {item["guid"] for item in old}
    current = {item["guid"] for item in live}
    print("RESULT", f"observed={len(live)}", f"stored={len(items)}", f"new={len(current - prior)}",
          f"retained_off_list={len(prior - current)}", f"rss={sum(i['visible'] for i in items)}",
          f"published_dates={sum(i['published'] is not None for i in live)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="directory containing the previous history and RSS")
    parser.add_argument("--output", type=Path, required=True, help="new directory for the validated candidate")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preview-all", action="store_true", help="bootstrap candidate for comparison only")
    mode.add_argument("--bootstrap-review", type=Path, help="reviewed publish/history decision for every observed GUID")
    args = parser.parse_args()
    write_bundle(args.source, args.output, preview=args.preview_all, review=args.bootstrap_review)


if __name__ == "__main__":
    main()
