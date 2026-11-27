import argparse
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from unicodedata import category, normalize
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup
import requests


SOURCE_URL = "https://www.joho-kochi.or.jp/"
OUTPUT_FILE = Path("joho-kochi-news.xml")
SECTIONS = ("Topics・お知らせ", "セミナー", "展示会・商談会", "補助金")
INITIAL_SOURCE_COUNT = 14
SOURCE_COUNT = "{urn:jnet21-rss:joho-kochi}sourceCount"
DATE_PREFIX = re.compile(r"^(?:New\s*)?(\d{1,2})/(\d{1,2})\s*[-－–]\s*$", re.I)
RSS_POSTED_DATE = re.compile(r"／公式トップ掲載日 (\d{1,2})/(\d{1,2})$")
STATUS_LABEL = re.compile(
    r"[【\[(]\s*(?:new|新着|受付中|申込受付中|受付終了|終了しました)\s*[】\])]"
)
ANNOUNCEMENT_WORDING = (
    (re.compile(r"開催(?:のお知らせ|のご案内|いたします|します)"), "開催"),
    (re.compile(r"出展(?:いたします|します)"), "出展"),
    (re.compile(r"募集(?:のお知らせ|のご案内|について)"), "募集"),
    (re.compile(r"申し込み|申込み"), "申込"),
)
DESCRIPTION = "高知県産業振興センターの公式トップに掲載された新着情報"
ET.register_namespace("kochi", "urn:jnet21-rss:joho-kochi")


def url_key(url):
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username:
        raise ValueError(f"Invalid article URL: {url}")
    host = parts.netloc.lower()
    if host == "www.joho-kochi.or.jp":
        host = "joho-kochi.or.jp"
    query = urlencode([
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
    ])
    return host, parts.path or "/", query


def title_key(title):
    title = STATUS_LABEL.sub("", normalize("NFKC", title).casefold())
    # Retain number boundaries so, for example, 1/11 and 11/1 remain distinguishable.
    parts = re.split(r"(\d+)", title)
    title = "".join(
        f"|{part}|" if index % 2 else "".join(
            char for char in part if not char.isspace() and not category(char).startswith("P")
        )
        for index, part in enumerate(parts)
    )
    for wording, replacement in ANNOUNCEMENT_WORDING:
        title = wording.sub(replacement, title)
    title = title.removesuffix("のお知らせ").removesuffix("のご案内")
    if not title:
        raise ValueError("Article title is empty after normalization")
    return title


def stored_identity(item):
    posted = RSS_POSTED_DATE.search(item.findtext("description", "") or "")
    month_day = tuple(map(int, posted.groups())) if posted else None
    return url_key(item.findtext("link", "")), title_key(item.findtext("title", "")), month_day


def parse_homepage(html):
    soup = BeautifulSoup(html, "html.parser")
    sections_seen = set()
    articles = {}
    for panel in soup.select(".panel"):
        heading = panel.select_one(":scope > .panel-heading")
        if heading is None:
            continue
        section = heading.get_text(" ", strip=True)
        if section not in SECTIONS:
            continue
        lists = panel.select(":scope > .panel-body > ul")
        if len(lists) != 1 or section in sections_seen:
            raise ValueError(f"Unexpected list structure: {section}")
        sections_seen.add(section)
        for row in lists[0].find_all("li", recursive=False):
            link = row.find("a", recursive=False)
            if link is None:
                raise ValueError(f"Article link missing: {section}")
            title = link.get_text(" ", strip=True)
            href = (link.get("href") or "").strip()
            position = next(i for i, node in enumerate(row.contents) if node is link)
            prefix = "".join(
                node.get_text() if hasattr(node, "get_text") else str(node)
                for node in row.contents[:position]
            ).strip()
            posted = DATE_PREFIX.fullmatch(prefix)
            if not title or not href or href.startswith(("#", "?")) or posted is None:
                raise ValueError(f"Invalid article row: {section}: {row.get_text(' ', strip=True)}")
            month, day = map(int, posted.groups())
            date(2000, month, day)  # Validate a month/day without assuming a publication year.
            url = urljoin(SOURCE_URL, href)
            key = url_key(url)
            if key[:2] == ("joho-kochi.or.jp", "/"):
                raise ValueError(f"Article link points to the home page: {section}")
            identity = (key, title_key(title), (month, day))
            articles.setdefault(identity, (title, url, section))

    if sections_seen != set(SECTIONS):
        raise ValueError(f"Missing sections: {', '.join(sorted(set(SECTIONS) - sections_seen))}")
    return articles


def generate(output):
    with requests.get(SOURCE_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60) as response:
        response.raise_for_status()
        articles = parse_homepage(response.content)

    tree = ET.parse(output)
    channel = tree.find("channel")
    if channel is None or tree.getroot().tag != "rss":
        raise ValueError("Existing RSS channel is missing")
    old_items = channel.findall("item")
    old_guids = {item.findtext("guid") for item in old_items}
    if len(old_items) < 30 or len(old_guids) != len(old_items) or not all(old_guids):
        raise ValueError("Existing RSS history is incomplete or has invalid GUIDs")

    previous_count = int(channel.findtext(SOURCE_COUNT, str(INITIAL_SOURCE_COUNT)))
    if not articles or len(articles) * 2 <= previous_count:
        raise ValueError(
            f"Source has {len(articles)} distinct articles, down from {previous_count}. "
            "Existing RSS preserved."
        )

    existing_announcements = {stored_identity(item) for item in old_items}
    new_items = []
    for identity, (title, url, section) in articles.items():
        key, normalized_title, (month, day) = identity
        undated_identity = (key, normalized_title, None)
        if identity in existing_announcements or undated_identity in existing_announcements:
            continue
        serialized = json.dumps(identity, ensure_ascii=False)
        guid = "urn:sha256:" + sha256(serialized.encode("utf-8")).hexdigest()
        if guid in old_guids:
            continue
        item = ET.Element("item")
        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "link").text = url
        ET.SubElement(item, "guid", isPermaLink="false").text = guid
        ET.SubElement(item, "description").text = f"{section}／公式トップ掲載日 {month}/{day}"
        new_items.append(item)

    count_node = channel.find(SOURCE_COUNT)
    if not new_items and count_node is not None and len(articles) == previous_count:
        print(f"Unchanged: source {len(articles)}, RSS {len(old_items)}")
        return

    channel.find("link").text = SOURCE_URL
    channel.find("description").text = DESCRIPTION
    if count_node is None:
        count_node = ET.Element(SOURCE_COUNT)
        channel.insert(3, count_node)
    count_node.text = str(len(articles))
    for index, item in enumerate(new_items, start=list(channel).index(count_node) + 1):
        channel.insert(index, item)

    with NamedTemporaryFile(dir=output.parent, prefix=f".{output.name}.", delete=False) as handle:
        temporary = Path(handle.name)
        try:
            tree.write(handle, encoding="utf-8", xml_declaration=True)
            handle.close()
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
    print(f"Source {len(articles)}, added {len(new_items)}, retained {len(old_items)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT_FILE)
    args = parser.parse_args()
    try:
        generate(args.output)
    except (requests.RequestException, OSError, ValueError, ET.ParseError) as error:
        parser.exit(1, f"Joho Kochi RSS: {error}\n")
