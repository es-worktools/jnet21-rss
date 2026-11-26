import re
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urljoin, urlsplit
from xml.etree.ElementTree import Element, SubElement, fromstring, tostring

import requests
from bs4 import BeautifulSoup

SOURCE_URL = "https://www.b-nest.jp/topics/"
OUTPUT_FILE = Path("bnest-topics.xml")
HEADERS = {"User-Agent": "Mozilla/5.0"}
MAX_ITEMS = 30
CATEGORIES = {"講座・セミナー", "イベント", "各種公募・補助金情報"}
ARTICLE_DATE = re.compile(r"[0-9]{4}年[0-9]{1,2}月[0-9]{1,2}日")


def parse_articles(html):
    soup = BeautifulSoup(html, "html.parser")
    articles = {}
    for card in soup.select(".eventTab > .eventTab__item > .eventItem"):
        category = card.select_one(":scope > .eventItem__head > .tag")
        if category is None:
            raise ValueError("B-nest article card is missing its category")
        if category.get_text(strip=True) not in CATEGORIES:
            continue

        date = card.select_one(":scope > .eventItem__head > .date")
        if date is None or not ARTICLE_DATE.fullmatch(date.get_text(strip=True)):
            raise ValueError("B-nest article card has a missing or invalid date")

        links = {}
        for anchor in card.select(":scope > p a[href]"):
            href = anchor["href"].strip()
            title = anchor.get_text(" ", strip=True)
            if not title or not href or href.startswith("#"):
                continue

            url = urljoin(SOURCE_URL, href)
            parts = urlsplit(url)
            if parts.scheme in {"http", "https"} and parts.hostname:
                links.setdefault(url, title)

        if len(links) != 1:
            raise ValueError("B-nest article card must have one article link")
        url, title = next(iter(links.items()))
        articles.setdefault(url, title)
        if len(articles) == MAX_ITEMS:
            break

    if not articles:
        raise ValueError("B-nest article extraction returned no items")
    return articles


def fetch_topics():
    response = requests.get(SOURCE_URL, headers=HEADERS, timeout=60)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    return response.text


def update_rss(output=OUTPUT_FILE):
    articles = parse_articles(fetch_topics())
    try:
        previous_data = output.read_bytes()
    except FileNotFoundError:
        previous_data = None

    previous = {}
    if previous_data is not None:
        previous = {
            item.findtext("link"): item
            for item in fromstring(previous_data).findall("./channel/item")
        }

    if len(articles) * 2 <= len(previous):
        raise ValueError(
            f"B-nest article count dropped from {len(previous)} to {len(articles)}"
        )

    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = "B-nest セミナー＆イベント情報"
    SubElement(channel, "link").text = SOURCE_URL
    SubElement(channel, "description").text = "B-nest セミナー・イベント・公募・補助金情報"

    for url, title in articles.items():
        item = SubElement(channel, "item")
        SubElement(item, "title").text = title
        SubElement(item, "link").text = url
        existing = previous.get(url)
        guid = existing.find("guid") if existing is not None else None
        if guid is None:
            SubElement(item, "guid").text = url
        else:
            item.append(deepcopy(guid))

        published = existing.find("pubDate") if existing is not None else None
        if published is not None:
            item.append(deepcopy(published))

    data = tostring(rss, encoding="utf-8", xml_declaration=True)
    if previous_data != data:
        # Replace the feed only after the full XML has been written successfully.
        with TemporaryDirectory(dir=output.parent) as directory:
            temporary_path = Path(directory) / output.name
            temporary_path.write_bytes(data)
            temporary_path.replace(output)

    print(output, len(articles))


if __name__ == "__main__":
    update_rss()
