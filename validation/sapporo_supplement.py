"""Non-production prototype. Preserve RSS history; notify schedule revisions.

Existing official subscriptions are deliberately outside this program's scope.
RSS is also the revision ledger, avoiding inconsistent RSS/state file pairs.
"""
import argparse
import copy
from datetime import datetime, date
from email.utils import format_datetime
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import unicodedata
from zoneinfo import ZoneInfo
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

TZ = ZoneInfo("Asia/Tokyo")
NS = "urn:jnet21:sapporo:schedule:v1"
ET.register_namespace("schedule", NS)
CONFIG = [
    ("woman", "女性起業家・経営者向け相談", 2),
    ("consultation-2", "中小企業診断士相談", 1),
]
FILE = "sapporo-consultation-supplement.xml"


def normalize(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def extract(html, slug, title, count, now):
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one("main article .entry-content")
    if body is None:
        raise ValueError("content region missing")
    headings = [h for h in body.find_all("h5") if "相談予定" in h.get_text()]
    if len(headings) != count:
        raise ValueError("unexpected schedule count; refuse partial capture")
    records = []
    for h in headings:
        m = re.fullmatch(r"相談予定\((20\d{2})年(\d{1,2})月\)", normalize(h.get_text()))
        if not m:
            raise ValueError("unrecognized month heading")
        year, month = map(int, m.groups())
        following = (now.year + (now.month == 12), now.month % 12 + 1)
        if (year, month) not in {(now.year, now.month), following}:
            raise ValueError("schedule not for the current or following month; manual review")
        label = h.find_previous("h4").get_text(" ", strip=True)
        lines = []
        for node in h.next_siblings:
            if getattr(node, "name", None) in {"h3", "h4", "h5"}:
                break
            if getattr(node, "name", None):
                text = node.get_text(" ", strip=True)
                if text:
                    lines.append(text)
        if not lines:
            raise ValueError("empty schedule")
        days = re.findall(r"(?<!\d)(\d{1,2})日\(([月火水木金土日])曜日\)", normalize(lines[0]))
        if not days:
            raise ValueError("schedule has no dated appointments")
        for day, weekday in days:
            d = date(year, month, int(day))
            if "月火水木金土日"[d.weekday()] != weekday:
                raise ValueError("appointment weekday mismatch")
        url = f"https://chusho.center.sec.or.jp/establish/{slug}/"
        series = hashlib.sha256((url + normalize(label)).encode()).hexdigest()
        payload = normalize(f"{year}-{month}|{label}|" + "|".join(lines))
        records.append(dict(series=series, fingerprint=hashlib.sha256(payload.encode()).hexdigest(),
                            url=url, title=title, label=label, month=f"{year}年{month}月", lines=lines))
    return records


def validate(root):
    items = root.findall("./channel/item")
    if not items:
        raise ValueError("empty RSS")
    guids = [i.findtext("guid") for i in items]
    if not all(guids) or len(set(guids)) != len(guids):
        raise ValueError("invalid or duplicate GUID")
    for i in items:
        for field in ["series", "fingerprint", "revision"]:
            if not i.findtext(f"{{{NS}}}{field}"):
                raise ValueError("invalid revision ledger")
        if int(i.findtext(f"{{{NS}}}revision")) < 1:
            raise ValueError("invalid revision")
    return items


def generate(before, records, now):
    if len(records) != 3 or len({r["series"] for r in records}) != 3:
        raise ValueError("incomplete source batch")
    if before is None:
        root = ET.Element("rss", version="2.0")
        channel = ET.SubElement(root, "channel")
        ET.SubElement(channel, "title").text = "札幌中小企業支援センター 相談予定・補完監視"
        ET.SubElement(channel, "link").text = "https://chusho.center.sec.or.jp/"
        ET.SubElement(channel, "description").text = "固定ページの月次予定と変更を検知。配信日時は検知日時。"
        old = []
    else:
        root = ET.fromstring(before)
        old = validate(root)
        channel = root.find("channel")
    latest = {}
    for item in old:
        key = item.findtext(f"{{{NS}}}series")
        if key not in latest or int(item.findtext(f"{{{NS}}}revision")) > int(latest[key].findtext(f"{{{NS}}}revision")):
            latest[key] = item
    if latest and set(latest) != {r["series"] for r in records}:
        raise ValueError("consultant identity changed; manual review")
    new = []
    for record in records:
        prev = latest.get(record["series"])
        if prev is not None and prev.findtext(f"{{{NS}}}fingerprint") == record["fingerprint"]:
            continue
        revision = int(prev.findtext(f"{{{NS}}}revision")) + 1 if prev is not None else 1
        item = ET.Element("item")
        ET.SubElement(item, "title").text = f"【{record['month']}・予定更新検知】{record['title']} {record['label']}"
        ET.SubElement(item, "link").text = record["url"]
        ET.SubElement(item, "guid", isPermaLink="false").text = f"urn:jnet21:sapporo:{record['series']}:r{revision}:{record['fingerprint']}"
        ET.SubElement(item, "pubDate").text = format_datetime(now)
        ET.SubElement(item, "description").text = "\n".join([
            "公式ページの予定を初回取得、または変更を検知しました。配信日時は検知日時です。",
            record["month"], record["label"], *record["lines"], record["url"]])
        for key in ["series", "fingerprint"]:
            ET.SubElement(item, f"{{{NS}}}{key}").text = record[key]
        ET.SubElement(item, f"{{{NS}}}revision").text = str(revision)
        new.append(item)
    if before is not None and not new:
        return before, 0
    for i in old:
        channel.remove(i)
    for i in new + old:
        channel.append(copy.deepcopy(i))
    validate(root)
    result = {i.findtext("guid"): i for i in root.findall("./channel/item")}
    for i in old:
        if ET.tostring(result[i.findtext("guid")]) != ET.tostring(i):
            raise ValueError("history changed")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), len(new)


def run(directory, fixtures=None, bootstrap=False, now=None, get=requests.get):
    now = now or datetime.now(TZ)
    directory = Path(directory)
    target = directory / FILE
    before = target.read_bytes() if target.exists() else None
    if before is None and not bootstrap:
        raise ValueError("baseline missing; explicit bootstrap required")
    if before is not None:
        validate(ET.fromstring(before))
    records = []
    for slug, title, count in CONFIG:
        if fixtures is not None:
            html = (Path(fixtures) / f"{slug}.html").read_bytes()
        else:
            url = f"https://chusho.center.sec.or.jp/establish/{slug}/"
            response = get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            if response.url != url or "text/html" not in response.headers.get("Content-Type", ""):
                raise ValueError("unexpected redirect or media type")
            html = response.content
        records.extend(extract(html, slug, title, count, now))
    data, added = generate(before, records, now)
    if data != before:
        directory.mkdir(parents=True, exist_ok=True)
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(dir=directory, delete=False) as f:
                tmp = Path(f.name)
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            validate(ET.fromstring(tmp.read_bytes()))
            if (target.read_bytes() if target.exists() else None) != before:
                raise ValueError("baseline changed concurrently")
            os.replace(tmp, target)
            tmp = None
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)
    return {"added": added, "total": len(ET.fromstring(data).findall("./channel/item")),
            "sha256": hashlib.sha256(data).hexdigest(), "records": records}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--fixtures", type=Path)
    parser.add_argument("--bootstrap", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.directory, args.fixtures, args.bootstrap), ensure_ascii=False, indent=2))
