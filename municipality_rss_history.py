from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path
from xml.etree.ElementTree import Element, ElementTree, SubElement, parse


def write_feed(output_file, channel_title, source_url, items, max_items):
    """Publish the latest list entries and retain up to two windows of history."""
    path = Path(output_file)
    rows = {}
    if path.exists():
        channel = parse(path).find("channel")
        if channel is None:
            raise RuntimeError("Existing RSS channel not found")
        for item in channel.findall("item"):
            link = item.findtext("link")
            if not link or item.findtext("guid") != link or link in rows:
                raise RuntimeError("Invalid or duplicate URL/GUID in existing RSS")
            rows[link] = (parsedate_to_datetime(item.findtext("pubDate")), item)

    newest = sorted(items.values(), key=lambda row: row[0], reverse=True)[:max_items]
    for date, title, url in newest:
        previous = rows.get(url)
        if previous and previous[0] > date:
            continue
        if previous and previous[0] == date and previous[1].findtext("title") == title:
            continue
        item = Element("item")
        SubElement(item, "title").text = title
        SubElement(item, "link").text = url
        SubElement(item, "guid", isPermaLink="true").text = url
        SubElement(item, "pubDate").text = format_datetime(date)
        rows[url] = (date, item)

    recent = sorted(rows.values(), key=lambda row: row[0], reverse=True)[:2 * max_items]
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = channel_title
    SubElement(channel, "link").text = source_url
    SubElement(channel, "description").text = channel_title + " GitHub generated RSS"
    for _, item in recent:
        channel.append(item)
    temp = path.with_suffix(path.suffix + ".tmp")
    ElementTree(rss).write(temp, encoding="utf-8", xml_declaration=True)
    temp.replace(path)
    return len(recent)
