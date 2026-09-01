import hashlib
import re
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from urllib.parse import urljoin
from xml.etree.ElementTree import Element, SubElement, ElementTree

import requests
from bs4 import BeautifulSoup, NavigableString, Tag


SOURCE_URL = "https://www.apc.jeed.go.jp/info_list.html"
OUTPUT_FILE = "apc-info.xml"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
}

JST = timezone(timedelta(hours=9))

DATE_RE = re.compile(
    r"令和\s*(元|\d+)年\s*(\d{1,2})月\s*(\d{1,2})日"
)

YEAR_ONLY_RE = re.compile(r"^\d{4}年$")

KNOWN_CATEGORIES = {
    "在職者",
    "求職者",
    "事業主",
    "お知らせ",
}


def normalize(text):
    text = re.sub(r"\s+", " ", text or "").strip()

    text = re.sub(
        r"\s*アップロード\s*$",
        "",
        text,
    )

    return text


def parse_reiwa_date(text):
    match = DATE_RE.search(text)

    if not match:
        return None

    era_year = match.group(1)

    if era_year == "元":
        reiwa_year = 1
    else:
        reiwa_year = int(era_year)

    year = 2018 + reiwa_year
    month = int(match.group(2))
    day = int(match.group(3))

    return datetime(
        year,
        month,
        day,
        9,
        0,
        tzinfo=JST,
    )


def find_section_heading(soup, title):
    for heading in soup.find_all("h2"):
        if normalize(
            heading.get_text(" ", strip=True)
        ) == title:
            return heading

    return None


def extract_entries_from_section(heading, section_name):
    entries = []

    if heading is None:
        return entries

    date_nodes = []

    for element in heading.next_elements:
        if isinstance(element, Tag):
            if (
                element.name == "h2"
                and element is not heading
            ):
                break

        if not isinstance(
            element,
            NavigableString,
        ):
            continue

        text = normalize(str(element))

        if DATE_RE.fullmatch(text):
            date_nodes.append(element)

    for date_node in date_nodes:
        date_text = normalize(str(date_node))

        texts = []
        links = []

        for element in date_node.next_elements:
            if element is date_node:
                continue

            if isinstance(element, Tag):
                if element.name == "h2":
                    break

                if element.name == "a":
                    href = (
                        element.get("href")
                        or ""
                    ).strip()

                    link_text = normalize(
                        element.get_text(
                            " ",
                            strip=True,
                        )
                    )

                    if href:
                        links.append(
                            (
                                link_text,
                                urljoin(
                                    SOURCE_URL,
                                    href,
                                ),
                            )
                        )

                continue

            if not isinstance(
                element,
                NavigableString,
            ):
                continue

            text = normalize(str(element))

            if not text:
                continue

            if DATE_RE.fullmatch(text):
                break

            if YEAR_ONLY_RE.fullmatch(text):
                continue

            # ナビゲーション等が混ざるのを防ぐ
            if text in {
                "高度ポリテクセンター",
                "前ページへ",
                "ページの先頭へ",
                "グローバルメニューへ戻る",
                "本文へ戻る",
            }:
                continue

            if text not in texts:
                texts.append(text)

        if not texts and not links:
            continue

        category = ""

        if texts and texts[0] in KNOWN_CATEGORIES:
            category = texts.pop(0)

        # タイトル決定
        title = ""

        if texts:
            title = texts[0]

        # 「以下のセミナーが～」だけでは内容が分からないため
        # 最初のコース名もタイトルへ付加
        if (
            title.startswith("以下のセミナー")
            and links
        ):
            course_title = links[0][0]

            if course_title:
                title = (
                    title
                    + " "
                    + course_title
                )

        if not title and links:
            title = links[0][0]

        if not title:
            continue

        # 最も具体的なリンクを使用。
        # リンクがないお知らせは一覧ページへ戻す。
        item_url = SOURCE_URL

        if links:
            item_url = links[0][1]

        description_parts = []

        if category:
            description_parts.append(
                category
            )

        description_parts.extend(texts)

        description = normalize(
            " ".join(description_parts)
        )

        guid_source = "|".join(
            [
                section_name,
                date_text,
                category,
                title,
                item_url,
            ]
        )

        guid = hashlib.sha256(
            guid_source.encode("utf-8")
        ).hexdigest()

        pub_date = parse_reiwa_date(
            date_text
        )

        entries.append(
            {
                "date_text": date_text,
                "pub_date": pub_date,
                "category": category,
                "title": title,
                "url": item_url,
                "description": description,
                "guid": guid,
                "section": section_name,
            }
        )

    return entries


response = requests.get(
    SOURCE_URL,
    headers=HEADERS,
    timeout=60,
)

response.raise_for_status()

soup = BeautifulSoup(
    response.content,
    "html.parser",
)

important_heading = find_section_heading(
    soup,
    "重要なお知らせ",
)

normal_heading = find_section_heading(
    soup,
    "お知らせ",
)

entries = []

entries.extend(
    extract_entries_from_section(
        important_heading,
        "重要なお知らせ",
    )
)

entries.extend(
    extract_entries_from_section(
        normal_heading,
        "お知らせ",
    )
)

if not entries:
    raise RuntimeError(
        "高度ポリテクセンターのお知らせを"
        "1件も取得できませんでした"
    )


# 同一GUIDの重複除去
unique_entries = {}

for entry in entries:
    unique_entries[
        entry["guid"]
    ] = entry

entries = list(
    unique_entries.values()
)

entries.sort(
    key=lambda x: (
        x["pub_date"]
        or datetime(
            1900,
            1,
            1,
            tzinfo=JST,
        )
    ),
    reverse=True,
)

# 最近のお知らせだけで十分
entries = entries[:30]


rss = Element(
    "rss",
    version="2.0",
)

channel = SubElement(
    rss,
    "channel",
)

SubElement(
    channel,
    "title",
).text = (
    "高度ポリテクセンター｜お知らせ"
)

SubElement(
    channel,
    "link",
).text = SOURCE_URL

SubElement(
    channel,
    "description",
).text = (
    "高度ポリテクセンターの"
    "重要なお知らせ・お知らせ"
)

SubElement(
    channel,
    "lastBuildDate",
).text = format_datetime(
    datetime.now(JST)
)

for entry in entries:
    item = SubElement(
        channel,
        "item",
    )

    SubElement(
        item,
        "title",
    ).text = entry["title"]

    SubElement(
        item,
        "link",
    ).text = entry["url"]

    guid = SubElement(
        item,
        "guid",
    )

    guid.set(
        "isPermaLink",
        "false",
    )

    guid.text = (
        "apc-info-"
        + entry["guid"]
    )

    if entry["pub_date"]:
        SubElement(
            item,
            "pubDate",
        ).text = format_datetime(
            entry["pub_date"]
        )

    description = entry["description"]

    if entry["section"] == "重要なお知らせ":
        description = (
            "【重要なお知らせ】 "
            + description
        )

    SubElement(
        item,
        "description",
    ).text = description


ElementTree(rss).write(
    OUTPUT_FILE,
    encoding="utf-8",
    xml_declaration=True,
)

print(
    OUTPUT_FILE,
    len(entries),
)

print()
print("--- ITEMS ---")

for entry in entries[:10]:
    print(
        entry["date_text"],
        entry["title"],
        entry["url"],
        sep=" | ",
    )
