"""Build the Tsuno Town RSS relay from the official RSS 2.0 response."""

import argparse
from email.utils import parsedate_to_datetime
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

SOURCE_URL = "https://www.town.tsuno.lg.jp/tsuno/rss"
OUTPUT_FILE = "municipality-1824-tsuno.xml"
RSS_MEDIA_TYPE = "application/rss+xml"
MAX_RESPONSE_BYTES = 2_000_000
MAX_ITEMS = 30
ARTICLE_URL = re.compile(r"https://www\.town\.tsuno\.lg\.jp/article\?articleId=[A-Za-z0-9_-]+")


def fetch_rss():
    request = Request(
        SOURCE_URL,
        headers={
            "Accept": RSS_MEDIA_TYPE,
            "Cache-Control": "no-cache",
            "User-Agent": "J-Net21-RSS/1.0",
        },
    )
    with urlopen(request, timeout=25) as response:
        print(f"HTTP {response.status}; {response.headers.get('Content-Type')}; {response.url}")
        print(f"Vary: {response.headers.get('Vary', '(none)')}")
        if response.status != 200 or response.url != SOURCE_URL:
            raise ValueError("Unexpected HTTP status or final URL")
        if response.headers.get_content_type() != RSS_MEDIA_TYPE:
            raise ValueError("Official endpoint did not return application/rss+xml")
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError("Official RSS response exceeds the size limit")
    return body


def read_feed(data, *, previous=False):
    root = ET.fromstring(data)
    channels = root.findall("channel")
    if root.tag != "rss" or root.get("version") != "2.0" or len(channels) != 1:
        raise ValueError(f"Expected one RSS 2.0 channel, got XML root {root.tag!r}")
    channel = channels[0]
    for tag in ("title", "link", "description"):
        if not (channel.findtext(tag) or "").strip():
            raise ValueError(f"Missing channel {tag}")
    items = {}
    for item in channel.findall("item"):
        link = (item.findtext("link") or "").strip()
        if not ARTICLE_URL.fullmatch(link) or not (item.findtext("title") or "").strip():
            raise ValueError(f"Missing article title or unexpected article URL: {link!r}")
        if link in items:
            raise ValueError(f"Duplicate article URL: {link}")
        date = parsedate_to_datetime(item.findtext("pubDate") or "")
        if date.utcoffset() is None:
            raise ValueError(f"Missing publication date timezone: {link}")
        guid = item.find("guid")
        if previous:
            if guid is None or guid.text != link or guid.get("isPermaLink") != "true":
                raise ValueError(f"Unexpected existing GUID: {link}")
        else:
            for old_guid in item.findall("guid"):
                item.remove(old_guid)
            ET.SubElement(item, "guid", {"isPermaLink": "true"}).text = link
        items[link] = (date, item)
    if not items:
        raise ValueError("RSS has zero articles")
    return channel, items


def update_feed(source, output, previous=None):
    channel, incoming = read_feed(source)
    retained = {}
    if previous is not None and previous.exists():
        _, retained = read_feed(previous.read_bytes(), previous=True)

    for link, article in incoming.items():
        if link not in retained or article[0] >= retained[link][0]:
            retained[link] = article

    ordered = sorted(retained.items(), key=lambda entry: (entry[1][0], entry[0]), reverse=True)
    root = ET.Element("rss", {"version": "2.0"})
    result = ET.SubElement(root, "channel")
    # The source channel pubDate is the request time. Omitting it keeps the relay
    # unchanged when the article timestamps and content are identical.
    for tag in ("title", "link", "description", "language", "copyright"):
        field = channel.find(tag)
        if field is not None:
            result.append(field)
    for _, (_, item) in ordered[:MAX_ITEMS]:
        result.append(item)
    ET.indent(root, space="  ")
    data = ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"
    read_feed(data, previous=True)

    output.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=output.parent, delete=False) as temporary:
        path = Path(temporary.name)
        try:
            temporary.write(data)
            temporary.close()
            path.replace(output)
        finally:
            path.unlink(missing_ok=True)

    print(f"Official RSS: {len(incoming)} articles; relay: {len(result.findall('item'))} articles")
    for link, (date, item) in incoming.items():
        print(f"  {date.isoformat()} | {item.findtext('title')} | {link}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--snapshot", type=Path, help="Reuse a saved official RSS response")
    parser.add_argument("--save-source", type=Path, help="Save the validated source response for verification")
    args = parser.parse_args()
    source = args.snapshot.read_bytes() if args.snapshot else fetch_rss()
    update_feed(source, args.output, args.previous)
    if args.save_source:
        args.save_source.write_bytes(source)


if __name__ == "__main__":
    main()
