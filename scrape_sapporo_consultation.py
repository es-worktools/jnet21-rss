"""Sapporo's three consultation schedules. RSS is the sole revision ledger.

Existing official subscriptions are deliberately outside this program's scope.
RSS is also the revision ledger, avoiding inconsistent RSS/state file pairs.
"""
import argparse
import copy
import fcntl
from datetime import datetime, date
from email.utils import format_datetime
import hashlib
import html as html_module
import json
import os
from pathlib import Path
import re
import tempfile
import unicodedata
from zoneinfo import ZoneInfo
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

TZ = ZoneInfo("Asia/Tokyo")
NS = "urn:jnet21:sapporo:schedule:v1"
ET.register_namespace("schedule", NS)
CONTENT = 'http://purl.org/rss/1.0/modules/content/'
ET.register_namespace('content', CONTENT)
CONFIG = [
    ("woman", "女性起業家・経営者向け相談", 2),
    ("consultation-2", "中小企業診断士相談", 1),
]
FILE = "sapporo-consultation-supplement.xml"
LABELS = {
    'woman': ('中小企業診断士 小西 麻衣 （こにし まい）',
              '中小企業診断士 木原 真由美 （きはら まゆみ）'),
    'consultation-2': ('窓口相談',),
}
INTRO = '公式ページの予定を初回取得、または変更を検知しました。配信日時は検知日時です。'
HEX = r'[0-9a-f]{64}'


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def identities():
    return {digest(f'https://chusho.center.sec.or.jp/establish/{slug}/' + normalize(label)):
            (f'https://chusho.center.sec.or.jp/establish/{slug}/', label, title)
            for slug, title, _ in CONFIG for label in LABELS[slug]}


def dated_days(line, year, month):
    text = normalize(line)
    dates = re.findall(r'(?<!\d)(\d{1,2})日\(([月火水木金土日])曜日\)', text)
    # Every date token in the appointment line must have a recognized weekday.
    if not dates or len(dates) != len(re.findall(r'\d+日', text)):
        raise ValueError('incomplete or unrecognized appointment date')
    days = []
    for day, weekday in dates:
        d = date(year, month, int(day))
        if '月火水木金土日'[d.weekday()] != weekday:
            raise ValueError('appointment weekday mismatch')
        days.append(int(day))
    if len(set(days)) != len(days) or days != sorted(days):
        raise ValueError('duplicate or unordered appointment date')
    return days


def check_record(record, now=None):
    series = record['series']
    if series not in identities():
        raise ValueError('unknown consultation series')
    url, label, title = identities()[series]
    if (record['url'], normalize(record['label']), record['title']) != (url, normalize(label), title):
        raise ValueError('series identity mismatch')
    m = re.fullmatch(r'(20\d{2})年(\d{1,2})月', record['month'])
    if not m:
        raise ValueError('invalid month')
    year, month = map(int, m.groups())
    date(year, month, 1)
    if now is not None:
        following = (now.year + (now.month == 12), now.month % 12 + 1)
        if (year, month) not in {(now.year, now.month), following}:
            raise ValueError('stale schedule; manual review')
    lines = record['lines']
    if not lines or any(not isinstance(v, str) or not v.strip() or len(v) > 2000 for v in lines):
        raise ValueError('missing or oversized schedule content')
    if any(marker in ''.join(lines) for marker in ('模擬', '試験データ')):
        raise ValueError('test data is prohibited')
    dated_days(lines[0], year, month)
    payload = normalize(f'{year}-{month}|{record["label"]}|' + '|'.join(lines))
    if record['fingerprint'] != digest(payload):
        raise ValueError('fingerprint does not match schedule content')
    return year, month


def normalize(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def extract(html, slug, title, count, now):
    soup = BeautifulSoup(html, "html.parser")
    bodies = soup.select("main article .entry-content")
    if len(bodies) != 1:
        raise ValueError("content region missing")
    body = bodies[0]
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
        previous = h.find_previous(['h3', 'h4'])
        if previous is None or previous.name != 'h4' or previous not in body.descendants:
            raise ValueError('consultation label missing')
        label = previous.get_text(" ", strip=True)
        lines = []
        for node in h.next_siblings:
            if getattr(node, "name", None) in {"h3", "h4", "h5"}:
                break
            if getattr(node, "name", None):
                if node.name != 'p' or node.find(['img', 'iframe', 'table', 'script']):
                    raise ValueError('unexpected schedule structure')
                text = node.get_text(" ", strip=True)
                if text:
                    lines.append(text)
            elif str(node).strip():
                raise ValueError('unexpected unwrapped schedule text')
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
    for record in records:
        check_record(record, now)
    if {r['series'] for r in records} != {k for k, v in identities().items() if f'/{slug}/' in v[0]}:
        raise ValueError('duplicate or missing consultation series')
    return records


def item_record(item):
    text = item.findtext('description') or ''
    if item.find(f'{{{CONTENT}}}encoded') is not None:
        text = html_module.unescape(text)
    lines = text.splitlines()
    series = item.findtext(f'{{{NS}}}series')
    if series not in identities() or len(lines) < 5 or lines[0] != INTRO:
        raise ValueError('invalid history payload')
    url, _, title = identities()[series]
    if lines[-1] != url:
        raise ValueError('history source mismatch')
    return dict(series=series, fingerprint=item.findtext(f'{{{NS}}}fingerprint'),
                url=item.findtext('link'), title=title, label=lines[2], month=lines[1], lines=lines[3:-1])


def validate(root):
    if root.tag != 'rss' or root.get('version') != '2.0' or len(root.findall('channel')) != 1:
        raise ValueError('invalid RSS root')
    channel = root.find('channel')
    if channel.findtext('title') != '札幌中小企業支援センター 相談予定・補完監視' or channel.findtext('link') != 'https://chusho.center.sec.or.jp/':
        raise ValueError('unexpected feed identity')
    items = root.findall("./channel/item")
    if not items:
        raise ValueError("empty RSS")
    guids = [i.findtext("guid") for i in items]
    if not all(guids) or len(set(guids)) != len(guids):
        raise ValueError("invalid or duplicate GUID")
    revisions = {}
    for i in items:
        for field in ['title', 'link', 'guid', 'pubDate', 'description',
                      *(f'{{{NS}}}{k}' for k in ('series', 'fingerprint', 'revision'))]:
            if len(i.findall(field)) != 1 or not i.findtext(field):
                raise ValueError('missing or duplicate item field')
        record = item_record(i)
        check_record(record)
        series, fp = record['series'], record['fingerprint']
        rev = i.findtext(f'{{{NS}}}revision')
        if not re.fullmatch(r'[1-9]\d*', rev) or not re.fullmatch(HEX, fp):
            raise ValueError('invalid revision ledger')
        if i.findtext('guid') != f'urn:jnet21:sapporo:{series}:r{rev}:{fp}' or i.find('guid').get('isPermaLink') != 'false':
            raise ValueError('GUID does not match ledger')
        if parsedate_to_datetime(i.findtext('pubDate')).utcoffset() is None:
            raise ValueError('detection timestamp has no timezone')
        if any(marker in i.findtext('title') for marker in ('模擬', '試験データ')):
            raise ValueError('test article prohibited')
        revisions.setdefault(series, []).append(int(rev))
    if set(revisions) != set(identities()):
        raise ValueError('history series missing')
    for values in revisions.values():
        if sorted(values) != list(range(1, max(values) + 1)):
            raise ValueError('duplicate or missing revision history')
    return items


def preserve_history(before, after):
    prior = validate(ET.fromstring(before))
    current = {i.findtext('guid'): i for i in validate(ET.fromstring(after))}
    for item in prior:
        old = ET.tostring(item)
        if item.findtext('guid') not in current or ET.tostring(current[item.findtext('guid')]) != old:
            raise ValueError('history changed or disappeared')


def generate(before, records, now):
    if now.utcoffset() is None:
        raise ValueError('timezone-aware detection timestamp required')
    if len(records) != 3 or {r['series'] for r in records} != set(identities()):
        raise ValueError("incomplete source batch")
    for r in records:
        check_record(r, now)
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
        if prev is not None:
            previous = item_record(prev)
            current_month = check_record(record)
            previous_month = check_record(previous)
            if current_month < previous_month:
                raise ValueError('schedule month regressed; manual review')
            if current_month == previous_month:
                if len(record['lines']) < len(previous['lines']) or len(dated_days(record['lines'][0], *current_month)) < len(dated_days(previous['lines'][0], *previous_month)):
                    raise ValueError('schedule shrank; possible partial capture, manual review')
        if prev is not None and prev.findtext(f"{{{NS}}}fingerprint") == record["fingerprint"]:
            continue
        revision = int(prev.findtext(f"{{{NS}}}revision")) + 1 if prev is not None else 1
        item = ET.Element("item")
        kind = '初回取得' if prev is None else ('新月予定' if current_month > previous_month else '予定変更')
        ET.SubElement(item, "title").text = f"【{record['month']}・{kind} r{revision}】{record['title']} {record['label']}"
        ET.SubElement(item, "link").text = record["url"]
        ET.SubElement(item, "guid", isPermaLink="false").text = f"urn:jnet21:sapporo:{record['series']}:r{revision}:{record['fingerprint']}"
        ET.SubElement(item, "pubDate").text = format_datetime(now)
        ET.SubElement(item, "description").text = html_module.escape("\n".join([
            INTRO,
            record["month"], record["label"], *record["lines"], record["url"]]))
        ET.SubElement(item, f'{{{CONTENT}}}encoded').text = ''.join(
            '<p>' + html_module.escape(s) + '</p>' for s in
            [INTRO, f'改訂 r{revision}（{kind}）', record['month'], record['label'], *record['lines']]
        ) + '<p><a href="' + html_module.escape(record['url'], quote=True) + '">公式ページを確認</a></p>'
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
    data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    if before is not None:
        preserve_history(before, data)
    return data, len(new)


def run(directory, fixtures=None, bootstrap=False, now=None, get=requests.get):
    # Serialize local writers as well as the workflow's concurrency guard.
    lock = Path(tempfile.gettempdir()) / ('jnet21-sapporo-' + digest(str(Path(directory).resolve())) + '.lock')
    with lock.open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _run(directory, fixtures, bootstrap, now, get)


def _run(directory, fixtures=None, bootstrap=False, now=None, get=requests.get):
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
