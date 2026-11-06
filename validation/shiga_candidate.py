"""Shiga classified press search to three candidate feeds (no publishing).

Existing official RSS subscriptions are retained separately. Their unavailable
historical XML/GUIDs must never be reconstructed from titles or guessed URLs.
The fixed date window is for retrospective validation, not a production cron.
"""
import argparse
import copy
from datetime import date, datetime, time
from email.utils import format_datetime
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urljoin, urlsplit, parse_qs, urlencode
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BASE = 'https://www.pref.shiga.lg.jp'
SEARCH = BASE + '/cgi-bin/press/index.php'
CATEGORIES = {'お知らせ': 'notice', 'イベント': 'event', '募集': 'recruit'}
TZ = ZoneInfo('Asia/Tokyo')


def parse_date(text):
    m = re.fullmatch(r'(20\d{2})年(\d{1,2})月(\d{1,2})日', text.strip())
    if not m:
        raise ValueError('invalid date')
    return date(*map(int, m.groups()))


def parse_page(html, start, end):
    soup = BeautifulSoup(html, 'html.parser')
    form = soup.select_one('form#press_form_search')
    if not form or form.select_one('[name=ds]').get('value') != start.isoformat() or form.select_one('[name=de]').get('value') != end.isoformat():
        raise ValueError('date window not echoed; refuse unfiltered results')
    table = soup.select_one('table.result-table tbody')
    counts = soup.select('.result-count')
    if table is None or not counts:
        raise ValueError('search structure missing')
    raw = counts[0].get_text(' ', strip=True).replace(',', '')
    m = re.fullmatch(r'(\d+)件中\s*(\d+)～(\d+)件目', raw)
    if not m:
        raise ValueError('unrecognized count')
    total, lo, hi = map(int, m.groups())
    records = []
    for row in table.select('tr'):
        category = row.select_one('td.col-category')
        day = row.select_one('td.col-date')
        a = row.select_one('td.col-title a[href]')
        if category is None or day is None or a is None:
            raise ValueError('incomplete row; never silently skip')
        label = category.get_text(' ', strip=True)
        if label not in CATEGORIES:
            raise ValueError('unknown category')
        dt = parse_date(day.get_text(' ', strip=True))
        if not start <= dt <= end:
            raise ValueError('date outside requested window')
        url = urljoin(BASE, a['href'])
        p = urlsplit(url)
        title = a.get_text(' ', strip=True)
        if p.scheme != 'https' or p.netloc != 'www.pref.shiga.lg.jp' or not re.fullmatch(r'/(?:[a-z0-9_-]+/)+\d+\.html', p.path) or p.query or p.fragment or not title:
            raise ValueError('invalid official article URL/title')
        records.append({'category': label, 'date': dt.isoformat(), 'title': title, 'url': url})
    if not records or len(records) != hi - lo + 1:
        raise ValueError('empty or partial page')
    next_links = {urljoin(SEARCH, a['href']) for a in soup.select('a[href]') if a.get_text(strip=True) == '次へ'}
    if len(next_links) > 1 or bool(next_links) != (hi < total):
        raise ValueError('inconsistent pagination')
    return records, total, lo, hi, next(iter(next_links), None)


def fetch_window(start, end, get=requests.get, fixtures=None):
    params = {'ds': start.isoformat(), 'de': end.isoformat(), 'limit': '300'}
    next_url = SEARCH + '?' + urlencode(params)
    all_rows, seen_urls, totals, pages = [], set(), set(), []
    while next_url:
        if next_url in seen_urls or len(pages) >= 10:
            raise ValueError('pagination loop or validation limit exceeded')
        seen_urls.add(next_url)
        index = len(pages) + 1
        if fixtures:
            html = (Path(fixtures) / f'shiga-search-{index}.html').read_bytes()
        else:
            r = get(next_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
            r.raise_for_status()
            if r.url != next_url or 'text/html' not in r.headers.get('Content-Type', ''):
                raise ValueError('unexpected response')
            html = r.content
        rows, total, lo, hi, href = parse_page(html, start, end)
        if lo != len(all_rows) + 1:
            raise ValueError('page gap or repeated page')
        totals.add(total)
        if len(totals) != 1:
            raise ValueError('source changed while paginating')
        all_rows.extend(rows)
        pages.append({'url': next_url, 'total': total, 'lo': lo, 'hi': hi})
        if href:
            p = urlsplit(href)
            if p.scheme != 'https' or p.netloc != 'www.pref.shiga.lg.jp' or p.path != '/cgi-bin/press/index.php':
                raise ValueError('unsafe next page')
            query = parse_qs(p.query)
            # Carry verified filters even if a next link contains only page=N.
            for k, v in params.items():
                if k in query and query[k] != [v]:
                    raise ValueError('next page changes filters')
                query[k] = [v]
            if query.get('page') != [str(index + 1)]:
                raise ValueError('unexpected next page index')
            next_url = SEARCH + '?' + urlencode({k: v[0] for k, v in query.items()})
        else:
            next_url = None
    if len(all_rows) != next(iter(totals)) or len({r['url'] for r in all_rows}) != len(all_rows):
        raise ValueError('incomplete total or duplicate articles')
    if [r['date'] for r in all_rows] != sorted((r['date'] for r in all_rows), reverse=True):
        raise ValueError('unexpected date order')
    if set(r['category'] for r in all_rows) != set(CATEGORIES):
        raise ValueError('category absent; manual review')
    return all_rows, pages


def candidate(label, records, before=None):
    if not records or any(r['category'] != label for r in records):
        raise ValueError('empty/mixed category')
    if before:
        root = ET.fromstring(before)
        channel = root.find('channel')
        old = root.findall('./channel/item')
        if channel is None or not old:
            raise ValueError('invalid baseline')
        old_by_url = {i.findtext('link'): i for i in old}
        guids = [i.findtext('guid') for i in old]
        if len(old_by_url) != len(old) or not all(guids) or len(set(guids)) != len(guids):
            raise ValueError('invalid baseline identity')
        if not set(old_by_url) & {r['url'] for r in records}:
            raise ValueError('no baseline overlap')
    else:
        root = ET.Element('rss', version='2.0')
        channel = ET.SubElement(root, 'channel')
        ET.SubElement(channel, 'title').text = '滋賀県 報道発表資料 ' + label
        ET.SubElement(channel, 'link').text = SEARCH
        ET.SubElement(channel, 'description').text = '公式検索の分類と資料提供日に基づく補完RSS。日付のみのため時刻はJST 00:00を使用。'
        old, old_by_url = [], {}
    new = []
    for r in records:
        if r['url'] in old_by_url:
            continue  # Preserve the whole old item including GUID/date/title.
        i = ET.Element('item')
        ET.SubElement(i, 'title').text = r['title']
        ET.SubElement(i, 'link').text = r['url']
        ET.SubElement(i, 'guid', isPermaLink='true').text = r['url']
        ET.SubElement(i, 'category').text = label
        dt = datetime.combine(date.fromisoformat(r['date']), time(), TZ)
        ET.SubElement(i, 'pubDate').text = format_datetime(dt)
        ET.SubElement(i, 'description').text = f"資料提供日：{r['date']}（公式は日付のみ掲載）\n分類：{label}\n{r['title']}\n{r['url']}"
        new.append(i)
    if before is not None and not new:
        return before
    for i in old:
        channel.remove(i)
    for i in new + old:
        channel.append(copy.deepcopy(i))
    data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    result = ET.fromstring(data).findall('./channel/item')
    identities = {i.findtext('guid'): i for i in result}
    if len(identities) != len(result) or not result:
        raise ValueError('duplicate/empty output')
    for old_item in old:
        if ET.tostring(identities[old_item.findtext('guid')]) != ET.tostring(old_item):
            raise ValueError('historical item changed')
    return data


def run(directory, start, end, fixtures=None, bootstrap=False, get=requests.get):
    directory = Path(directory)
    before = {}
    for label, slug in CATEGORIES.items():
        p = directory / f'support-0205-shiga-{slug}.xml'
        before[label] = p.read_bytes() if p.exists() else None
        if before[label] is None and not bootstrap:
            raise ValueError('baseline missing; explicit bootstrap required')
    rows, pages = fetch_window(start, end, get=get, fixtures=fixtures)
    outputs = {label: candidate(label, [r for r in rows if r['category'] == label], before[label]) for label in CATEGORIES}
    # All sources and categories must pass before any file is written.
    directory.mkdir(parents=True, exist_ok=True)
    for label, data in outputs.items():
        p = directory / f'support-0205-shiga-{CATEGORIES[label]}.xml'
        if (p.read_bytes() if p.exists() else None) != before[label]:
            raise ValueError('baseline changed concurrently')
    for label, data in outputs.items():
        p = directory / f'support-0205-shiga-{CATEGORIES[label]}.xml'
        if data == before[label]:
            continue
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(dir=directory, delete=False) as f:
                tmp = Path(f.name)
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            ET.fromstring(tmp.read_bytes())
            os.replace(tmp, p)
            tmp = None
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)
    return {'start': start.isoformat(), 'end': end.isoformat(), 'pages': pages,
            'counts': {label: len([r for r in rows if r['category'] == label]) for label in CATEGORIES},
            'rows': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', required=True, type=Path)
    parser.add_argument('--start', required=True, type=date.fromisoformat)
    parser.add_argument('--end', required=True, type=date.fromisoformat)
    parser.add_argument('--fixtures', type=Path)
    parser.add_argument('--bootstrap', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run(args.directory, args.start, args.end, args.fixtures, args.bootstrap), ensure_ascii=False, indent=2))
