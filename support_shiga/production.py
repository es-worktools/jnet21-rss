"""Build an entire, verified Shiga bundle outside the checkout; never publish here."""
import copy
from datetime import date, datetime, time
from email.utils import parsedate_to_datetime, format_datetime
import hashlib
from html import escape
import json
from pathlib import Path
from xml.etree import ElementTree as ET

from . import search

START = date(2026, 9, 3)
SNAPSHOT_END = date(2026, 11, 6)
SOURCE_COMMIT = '93fcee58efac0ced4b69ed275d5317548f9a0d27'
POLICIES = ('full-history', 'archive-summary')
PUBLIC = 'https://es-worktools.github.io/jnet21-rss/'
STATE = 'support_shiga/state.json'
SEED_HASHES = {
    'notice': '5ef6a446b98ff31c7e4f182c10af5b93e0a97385a8acf751bd27eb7201ec3124',
    'event': 'abc62be1045cdf98c04fe7b3cea3b05aff4a6b773ad1de1b3a9be7ca8d7ff878',
    'recruit': '0a556d18da0ed629779c6380d7fdff9d8713685077b34aa680147283ffeb4912',
}


def paths(slug):
    return (f'support-0205-shiga-{slug}.xml',
            f'archive/support-0205-shiga-{slug}.xml',
            f'archive/support-0205-shiga-{slug}.html')


OUTPUTS = tuple(p for slug in search.CATEGORIES.values() for p in paths(slug))
ALLOWLIST = (*OUTPUTS, STATE)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def items(data, label, allow_summary=False):
    root = ET.fromstring(data)
    if root.tag != 'rss' or root.find('channel') is None:
        raise ValueError('invalid RSS structure')
    result = root.findall('./channel/item')
    urls, guids = set(), set()
    if not result:
        raise ValueError('empty RSS forbidden')
    for i in result:
        url, guid = i.findtext('link'), i.findtext('guid')
        if not i.findtext('title') or not guid or url in urls or guid in guids:
            raise ValueError('missing or duplicate identity')
        if i.findtext('category') != label:
            raise ValueError('category does not match feed')
        dt = parsedate_to_datetime(i.findtext('pubDate'))
        if dt.tzinfo is None:
            raise ValueError('date without timezone')
        summary = guid == f'urn:jnet21:shiga:archive-summary:20261106:{search.CATEGORIES[label]}'
        if summary:
            if not allow_summary or url != PUBLIC + paths(search.CATEGORIES[label])[2]:
                raise ValueError('unexpected summary item')
        else:
            p = search.urlsplit(url or '')
            if (p.scheme != 'https' or p.netloc != 'www.pref.shiga.lg.jp'
                    or not search.re.fullmatch(r'/(?:[a-z0-9_-]+/)+\d+\.html', p.path)
                    or p.query or p.fragment):
                raise ValueError('invalid official article link')
        urls.add(url)
        guids.add(guid)
    return result


def append_items(before, additions):
    if not additions:
        return before
    root = ET.fromstring(before)
    channel = root.find('channel')
    old = channel.findall('item')
    for i in old:
        channel.remove(i)
    for i in additions + old:
        channel.append(copy.deepcopy(i))
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def preserve(before, after):
    old = ET.fromstring(before).findall('./channel/item')
    by_guid = {i.findtext('guid'): ET.tostring(i)
               for i in ET.fromstring(after).findall('./channel/item')}
    if any(by_guid.get(i.findtext('guid')) != ET.tostring(i) for i in old):
        raise ValueError('historical item changed or lost')


def summary_feed(label, seed, day):
    slug = search.CATEGORIES[label]
    root = ET.fromstring(seed)
    channel = root.find('channel')
    count = len(channel.findall('item'))
    for i in list(channel.findall('item')):
        channel.remove(i)
    channel.find('description').text = ('初回437候補は分類別の履歴一覧に全件保存。'
        'このRSSは履歴案内と、基準候補にない記事の初回検知を配信します。')
    i = ET.SubElement(channel, 'item')
    ET.SubElement(i, 'title').text = f'【履歴案内】滋賀県 {label}：初回候補{count}件'
    ET.SubElement(i, 'link').text = PUBLIC + paths(slug)[2]
    ET.SubElement(i, 'guid', isPermaLink='false').text = f'urn:jnet21:shiga:archive-summary:20261106:{slug}'
    ET.SubElement(i, 'category').text = label
    ET.SubElement(i, 'pubDate').text = format_datetime(datetime.combine(day, time(), search.TZ))
    ET.SubElement(i, 'description').text = (f'2026-09-03〜2026-11-06の{count}候補を履歴一覧へ保存。'
        '既読処理や確認済みを意味しません。リンク先で過去分を照合してください。'
        'この案内の日時は補完開始日（JST 00:00）、公式記事の公開日時ではありません。')
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def history_html(label, data):
    rows = sorted(items(data, label), key=lambda i: (parsedate_to_datetime(i.findtext('pubDate')), i.findtext('link')), reverse=True)
    body = ''.join(f'<tr><td>{escape(parsedate_to_datetime(i.findtext("pubDate")).astimezone(search.TZ).date().isoformat())}</td>'
                   f'<td><a href="{escape(i.findtext("link"), quote=True)}">{escape(i.findtext("title"))}</a></td></tr>' for i in rows)
    return ('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>滋賀県 {label} 補完履歴</title><style>body{{font-family:sans-serif;line-height:1.8;max-width:1100px;margin:30px auto;padding:20px}}'
        'td,th{border-bottom:1px solid #ccc;padding:10px;text-align:left}table{border-collapse:collapse;width:100%}td:first-child{white-space:nowrap}</style>'
        f'<h1>滋賀県 {label}：補完履歴 {len(rows)}件</h1><p>2026年9月3日以降の検知履歴。初回437候補を保持し、以後の検知分も追加します。'
        'J-Net21未登録・確認済みの判定ではありません。公式の資料提供日を表示し、時刻は補完RSSで00:00 JSTとしています。'
        '9月2日の9候補は別途照合が必要です。</p>'
        f'<p><a href="support-0205-shiga-{search.CATEGORIES[label]}.xml">全件の履歴RSS</a> / '
        f'<a href="../support-0205-shiga-{search.CATEGORIES[label]}.xml">通常購読用RSS</a></p>'
        '<table><thead><tr><th>資料提供日</th><th>記事</th></tr></thead><tbody>' + body + '</tbody></table></html>').encode()


def load_baseline(repo, policy):
    state_path = repo / STATE
    if not state_path.exists():
        if policy not in POLICIES:
            raise ValueError('first run requires an explicitly approved bootstrap policy')
        if any((repo / p).exists() for p in OUTPUTS):
            raise ValueError('partial baseline exists; refuse bootstrap')
        return None, {}
    state = json.loads(state_path.read_text())
    if (state.get('schema') != 1 or state.get('policy') not in POLICIES
            or state.get('source_commit') != SOURCE_COMMIT
            or set(state.get('hashes', {})) != set(OUTPUTS)):
        raise ValueError('invalid state')
    if policy and policy != state['policy']:
        raise ValueError('policy changes require a separate migration review')
    existing = {}
    for p in OUTPUTS:
        existing[p] = (repo / p).read_bytes()
        if digest(existing[p]) != state['hashes'][p]:
            raise ValueError('baseline checksum mismatch: ' + p)
    return state, existing


def build_bundle(repo, output, policy=None, today=None, get=search.requests.get, fixtures=None):
    repo, output = Path(repo), Path(output)
    day = today or datetime.now(search.TZ).date()
    if day < SNAPSHOT_END:
        raise ValueError('run date predates the validated snapshot')
    if output.exists():
        raise ValueError('output must be a new isolated directory')
    state, existing = load_baseline(repo, policy)
    policy = state['policy'] if state else policy
    if state and day < date.fromisoformat(state['last_query_end']):
        raise ValueError('date went backwards')
    archives, old_live, owners, seed_urls = {}, {}, {}, set()
    for label, slug in search.CATEGORIES.items():
        live_path, archive_path, _ = paths(slug)
        seed = (repo / f'validation/candidate/support-0205-shiga-{slug}.xml').read_bytes()
        if digest(seed) != SEED_HASHES[slug]:
            raise ValueError('validated 437 snapshot changed')
        seed_urls.update(i.findtext('link') for i in items(seed, label))
        archives[label] = existing[archive_path] if state else seed
        old_live[label] = existing[live_path] if state else (
            seed if policy == 'full-history' else summary_feed(label, seed, day))
        items(old_live[label], label, allow_summary=True)
        for i in items(archives[label], label):
            url = i.findtext('link')
            if url in owners:
                raise ValueError('cross-feed duplicate baseline')
            owners[url] = label
    if not seed_urls <= set(owners) or len(seed_urls) != 437:
        raise ValueError('validated initial history lost')
    rows, pages = search.fetch_window(START, day, get=get, fixtures=fixtures)
    if not set(owners).intersection(r['url'] for r in rows):
        raise ValueError('no historical overlap; source identity needs review')
    observed = dict(state.get('observed_categories', {})) if state else dict(owners)
    changes = list(state.get('category_changes', [])) if state else []
    routed = {label: [] for label in search.CATEGORIES}
    for row in rows:
        url, current = row['url'], row['category']
        previous = observed.get(url)
        if previous and previous != current:
            changes.append({'url': url, 'from': previous, 'to': current, 'detected': day.isoformat()})
        observed[url] = current
        # Keep first-seen placement/GUID for existing URLs; do not duplicate on reclassification.
        routed[owners.get(url, current)].append(dict(row, category=owners.get(url, current)))
    outputs, new_counts = {}, {}
    for label, slug in search.CATEGORIES.items():
        before = archives[label]
        # candidate() validates overlap and preserves the whole old item.
        after = search.candidate(label, routed[label], before) if routed[label] else before
        archive_items = items(after, label)
        old_urls = {i.findtext('link') for i in items(before, label)}
        additions = [i for i in archive_items if i.findtext('link') not in old_urls]
        live = after if policy == 'full-history' else append_items(old_live[label], additions)
        items(live, label, allow_summary=True)
        preserve(before, after)
        preserve(old_live[label], live)
        live_path, archive_path, html_path = paths(slug)
        outputs.update({live_path: live, archive_path: after, html_path: history_html(label, after)})
        new_counts[label] = len(additions)
    state_data = {'schema': 1, 'policy': policy, 'source_commit': SOURCE_COMMIT,
                  'last_query_end': day.isoformat(), 'observed_categories': observed,
                  'category_changes': changes, 'hashes': {p: digest(b) for p, b in outputs.items()}}
    outputs[STATE] = (json.dumps(state_data, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode()
    # No source file is written, even if staging fails midway.
    output.mkdir(parents=True)
    for p, data in outputs.items():
        dest = output / p
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        if dest.read_bytes() != data:
            raise OSError('staging verification failed')
    return {'start': START.isoformat(), 'end': day.isoformat(), 'policy': policy,
            'pages': pages, 'new_counts': new_counts,
            'archive_counts': {label: len(items(outputs[paths(slug)[1]], label)) for label, slug in search.CATEGORIES.items()},
            'live_counts': {label: len(items(outputs[paths(slug)[0]], label, True)) for label, slug in search.CATEGORIES.items()},
            'category_changes': changes, 'hashes': state_data['hashes']}
