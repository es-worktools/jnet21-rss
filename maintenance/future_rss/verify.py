"""Replay municipal RSS validation with cached official data and a fixed clock."""
import contextlib
import csv
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import importlib.util
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

JST = timezone(timedelta(hours=9))
REPO = Path(__file__).resolve().parents[2]
WORKSPACE = REPO.parent
EVIDENCE = WORKSPACE / 'evidence'
REPRESENTATIVES = {
    '1124': 'source order / cutoff continue',
    '1213': 'source order / cutoff break',
    '1336': 'source order / 180 days',
    '1365': 'source order / 30 days',
    '1402': 'source order / 60 days',
    '1464': 'exact time / 90 days, first parser',
    '1667': 'exact time / 90 days, second parser',
    '1346': 'source order / exceptional 15-item limit',
}


def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixed_clock(now):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return now.replace(tzinfo=None)
            return now.astimezone(tz)
    return Clock


def items(path):
    return [
        {'url': item.findtext('link'), 'title': item.findtext('title'),
         'guid': item.findtext('guid'), 'guid_permalink': item.find('guid').get('isPermaLink'),
         'pubdate': item.findtext('pubDate'), 'description': item.findtext('description')}
        for item in ET.parse(path).findall('./channel/item')
    ]


def keyed(rows):
    return {row['url']: row for row in rows}


def run(module, text, now, output, fail_fetch=False):
    def fetch(url):
        if fail_fetch:
            raise OSError('Simulated source acquisition failure')
        return text if url == module.DATA_URL else '<html/>'

    module.datetime = fixed_clock(now)
    module.OUTPUT_FILE = str(output)
    module.fetch = fetch
    with contextlib.redirect_stdout(io.StringIO()):
        module.main()
    return items(output)


def candidate_for(module):
    approved = load_module(REPO / 'scrape_municipality_1671_hisayama.py')
    for name in ('SOURCE_URL', 'DATA_URL', 'CHANNEL_TITLE', 'ALLOWED_DOMAIN', 'MAX_ITEMS'):
        setattr(approved, name, getattr(module, name))
    return approved


def collect_raw(source, module, now, days, stop_at_cutoff):
    all_futures = []
    reachable = set()
    within_scan = True
    cutoff = now - timedelta(days=days)
    for row in source:
        if row['is_category_index'] or row['is_keitai_page']:
            continue
        date = datetime.fromisoformat(row['publish_datetime'])
        if date.utcoffset() is None:
            raise ValueError('source timezone missing')
        if date < cutoff and stop_at_cutoff:
            within_scan = False
        if date < cutoff:
            continue
        url = urljoin(module.SOURCE_URL, row['url'])
        if within_scan:
            reachable.add(url)
        if date > now:
            all_futures.append({'url': url, 'title': row['page_name'],
                                'date': row['publish_datetime'], 'reachable': within_scan})
    return all_futures, reachable


def guard_exact_rss(prior, ordered_eligible, selected, cutoff, future_only, limit):
    """Check the exact-time variant against prior still-eligible identities."""
    def identity(row):
        return (row['guid'], row['guid_permalink'], row['url'])

    def date(row):
        parsed = parsedate_to_datetime(row['pubdate'])
        if parsed.utcoffset() is None:
            raise ValueError('RSS timestamp has no timezone')
        return parsed

    if not selected or len(selected) > limit:
        raise ValueError('empty or oversized RSS')
    expected_snapshot = ordered_eligible[:limit]
    if list(map(identity, selected)) != list(map(identity, expected_snapshot)):
        raise ValueError('selection does not match the eligible source prefix')
    current = keyed(ordered_eligible)
    if len(current) != len(ordered_eligible) or len({row['guid'] for row in ordered_eligible}) != len(current):
        raise ValueError('duplicate RSS link or GUID')
    surviving = {identity(row) for row in selected}
    for row in prior:
        if row['url'] in current and identity(row) != identity(current[row['url']]):
            raise ValueError('existing GUID changed')
        if identity(row) in surviving or date(row) < cutoff:
            continue
        if row['url'] in future_only and row['url'] not in current:
            continue
        if row['url'] in current:
            # The untruncated source contains it and the verified prefix caps it.
            continue
        if len(selected) == limit and all(date(item) > date(row) for item in selected):
            continue
        raise ValueError('unexplained loss of eligible prior item: ' + row['url'])


def sample(url, title, date, category=False, mobile=False):
    return {'url': url, 'page_name': title, 'publish_datetime': date.isoformat(),
            'is_category_index': category, 'is_keitai_page': mobile}


def fixtures(module, days, midnight, stop_at_cutoff, now, work):
    future_at = now + timedelta(minutes=5)
    past = sample('/maintenance-normal', '通常記事', now - timedelta(minutes=1))
    future = sample('/maintenance-future', '将来記事', future_at)
    expired = sample('/maintenance-old', '期間外', now - timedelta(days=days, minutes=1))
    second = sample('/maintenance-later-row', '古い行の後にある通常記事', now - timedelta(days=1))
    excluded = [sample('/maintenance-category', 'カテゴリ', future_at, category=True),
                sample('/maintenance-mobile', '携帯', future_at, mobile=True)]
    data = [future, past, *excluded, expired, second]
    old_output = work / 'old.xml'
    candidate_output = work / 'prototype.xml'
    candidate = candidate_for(module)
    tests = {}
    try:
        base = run(module, json.dumps(data), now, old_output)
        tests['old_future'] = 'pubDateなしで配信' if base[0]['pubdate'] is None else '通常処理'
        assert midnight and base[0]['url'].endswith(future['url'])
        assert base[0]['pubdate'] is None
        assert any(r['url'].endswith(second['url']) for r in base) == (not stop_at_cutoff)
    except RuntimeError as exc:
        assert not midnight and str(exc) == 'Invalid publication date'
        tests['old_future'] = 'Invalid publication date'
    if midnight:
        original_before_due = old_output.read_bytes()
        try:
            run(candidate, json.dumps(data), future_at, old_output)
        except ValueError as exc:
            assert 'Invalid date value or format' in str(exc)
            assert old_output.read_bytes() == original_before_due
        else:
            raise AssertionError('the direct copy should fail on a previous undated RSS row')
        tests['direct_copy_due_existing_undated_item_raises'] = 'PASS'
        # Check the behavior of copying the approved patch without adapting it.
        base = run(module, json.dumps([past, expired, second]), now, old_output)
        result = run(candidate, json.dumps([past, expired, second]), now, work / 'compare.xml')
        tests['direct_copy_changes_existing_pubdate'] = base[0]['pubdate'] != result[0]['pubdate']
        tests['direct_copy_changes_continuation'] = (
            any(x['url'].endswith(second['url']) for x in base) !=
            any(x['url'].endswith(second['url']) for x in result)
        )
        if days != 90:
            probe_age = (90 + days) / 2
            probe = sample('/maintenance-window', '期間比較', now - timedelta(days=probe_age))
            baseline = run(module, json.dumps([past, probe]), now, old_output)
            comparison = run(candidate, json.dumps([past, probe]), now, work / 'compare-window.xml')
            assert (len(baseline), len(comparison)) == ((2, 1) if days > 90 else (1, 2))
            tests['direct_copy_changes_window'] = True
        assert tests['direct_copy_changes_existing_pubdate']
        bumped = sample('/maintenance-sorted-top', '公式順に対する新着', now)
        cap_fixture = [past, bumped, *[
            sample(f'/maintenance-source-order-{i}', str(i), now - timedelta(minutes=i+3))
            for i in range(module.MAX_ITEMS)
        ]]
        original = run(module, json.dumps(cap_fixture), now, work / 'old-cap.xml')
        copied = run(candidate, json.dumps(cap_fixture), now, work / 'copied-cap.xml')
        assert len(original) == len(copied) == module.MAX_ITEMS
        assert original[0]['url'].endswith(past['url'])
        assert copied[0]['url'].endswith(bumped['url'])
        tests['source_order_cap_and_sorting_difference'] = 'PASS'
        return tests

    before = run(candidate, json.dumps(data), now, candidate_output)
    assert len(before) == 2
    assert before[0]['url'].endswith(past['url'])
    assert before[0]['guid'] == before[0]['url']
    assert before[0]['pubdate'] == run(module, json.dumps(data[1:]), now, old_output)[0]['pubdate']
    saved = candidate_output.read_bytes()
    assert run(candidate, json.dumps(data), now, candidate_output) == before
    assert candidate_output.read_bytes() == saved
    reached = run(candidate, json.dumps(data), future_at, candidate_output)
    assert reached[0]['url'].endswith(future['url'])
    assert parsedate_to_datetime(reached[0]['pubdate']) == future_at
    assert keyed(reached)[before[0]['url']]['guid'] == before[0]['guid']
    tests['defer_due_original_timestamp_guids_repeat'] = 'PASS'

    saved = candidate_output.read_bytes()
    bad_date = {**future, 'publish_datetime': '2026-99-27T20:00:00+09:00'}
    missing_zone = {**future, 'publish_datetime': future_at.replace(tzinfo=None).isoformat()}
    cases = [
        ('fetch_error', data, True, 'Simulated source acquisition failure'),
        ('empty', [], False, 'Official news JSON missing'),
        ('only_future', [sample('/later', 'もっと先', future_at + timedelta(hours=1))], False, 'No articles found'),
        ('bad_date', [past, bad_date], False, 'month must be in'),
        ('no_timezone', [past, missing_zone], False, 'has no timezone'),
        ('decrease', [past], False, 'Unexpected item count decrease'),
    ]
    for name, payload, fail_fetch, expected in cases:
        try:
            run(candidate, json.dumps(payload), future_at, candidate_output, fail_fetch=fail_fetch)
        except (RuntimeError, ValueError, OSError) as exc:
            assert expected in str(exc), (name, str(exc), expected)
        else:
            raise AssertionError(name)
        assert candidate_output.read_bytes() == saved
        tests[name] = 'PASS'

    full = [sample(f'/maintenance-cap-{i}', str(i), now - timedelta(minutes=i+1))
            for i in range(module.MAX_ITEMS + 2)]
    cap = run(candidate, json.dumps(full), now, work / 'cap.xml')
    assert len(cap) == module.MAX_ITEMS
    assert cap[-1]['url'].endswith(f'/maintenance-cap-{module.MAX_ITEMS-1}')
    tests['limit'] = 'PASS'

    replace = sample('/maintenance-different', '別記事', now - timedelta(minutes=2))
    base_path = work / 'membership.xml'
    prior = run(candidate, json.dumps([past, second]), now, base_path)
    swapped = run(candidate, json.dumps([past, replace]), now, base_path)
    assert len(prior) == len(swapped)
    try:
        guard_exact_rss(prior, swapped, swapped, now-timedelta(days=days), set(), module.MAX_ITEMS)
    except ValueError as exc:
        assert 'unexplained loss' in str(exc)
    else:
        raise AssertionError('same-count replacement was not caught')
    tests['same_count_replacement'] = '件数のみは通過、GUID照合は検出'
    guard_exact_rss(prior, swapped, swapped, now-timedelta(days=days), {prior[-1]['url']}, module.MAX_ITEMS)
    guard_exact_rss(prior, swapped, swapped, now-timedelta(hours=12), set(), module.MAX_ITEMS)
    newest = sample('/maintenance-new-top', '新着', now)
    capped = run(candidate, json.dumps([newest, *full[:-3]]), now, work / 'cap-new.xml')
    assert len(capped) == module.MAX_ITEMS
    guard_exact_rss(cap, capped, capped, now-timedelta(days=days), set(), module.MAX_ITEMS)
    substituted = sample('/maintenance-older-replacement', '下位の別記事', now - timedelta(days=1))
    capped_loss = run(candidate, json.dumps([*full[:module.MAX_ITEMS-1], substituted]), now, work / 'cap-loss.xml')
    try:
        guard_exact_rss(cap, capped_loss, capped_loss, now-timedelta(days=days), set(), module.MAX_ITEMS)
    except ValueError as exc:
        assert 'unexplained loss' in str(exc)
    else:
        raise AssertionError('same-count replacement at the cap was not caught')
    changed_guid = [dict(row) for row in cap]
    changed_guid[0]['guid'] = 'unexpected-guid'
    try:
        guard_exact_rss(cap, changed_guid, changed_guid, now-timedelta(days=days), set(), module.MAX_ITEMS)
    except ValueError as exc:
        assert 'existing GUID changed' in str(exc)
    else:
        raise AssertionError('changed GUID was not caught')

    edge = sample('/maintenance-window-edge', '期間境界', now - timedelta(days=days))
    edge_rows = run(candidate, json.dumps([past, expired, edge]), now, work / 'edge.xml')
    assert len(edge_rows) == 2 and edge_rows[-1]['url'].endswith(edge['url'])
    tests['expiry_deferral_deterministic_cap'] = 'PASS'
    tests['full_cap_loss_guid_and_cutoff_boundary'] = 'PASS'
    return tests


def main():
    source_meta = json.loads((EVIDENCE / 'official.json').read_text())
    result = {}
    csv_input = next((WORKSPACE / 'upload').glob('*.csv'))
    with csv_input.open(encoding='utf-8-sig') as source_file:
        for row in csv.DictReader(source_file):
            if row['該当条件'] != '同型のJSON取得':
                continue
            key = row['管理番号']
            filename = row['停止条件のコード'].split('/')[-1].split('#')[0]
            code = (REPO / filename).read_text()
            defaults = load_module(REPO / filename)
            current_rss = REPO / defaults.OUTPUT_FILE
            module = load_module(REPO / filename)
            now = datetime.fromisoformat(source_meta[key]['json']['started_at'])
            days = int(code.split('timedelta(days=')[1].split(')')[0])
            midnight = 'astimezone(JST).replace(hour=0' in code
            stop_at_cutoff = 'if date < cutoff: break' in code
            metadata = source_meta[key]
            verification = {'midnight': midnight, 'days': days, 'cap': module.MAX_ITEMS,
                            'stop_at_cutoff': stop_at_cutoff, 'source': module.SOURCE_URL,
                            'data_url': module.DATA_URL, 'as_of': now.isoformat(),
                            'samples': {}, 'current_items': len(items(current_rss))}
            result[key] = verification
            with TemporaryDirectory() as temporary:
                work = Path(temporary)
                if key in REPRESENTATIVES or not midnight:
                    verification['samples'] = fixtures(module, days, midnight, stop_at_cutoff, now, work)
                if any(x.get('status') != 200 for x in metadata.values()):
                    verification['error'] = 'HTTP or transport verification incomplete'
                    continue
                if any(x['final'].split('/')[2] != module.ALLOWED_DOMAIN for x in metadata.values()):
                    verification['error'] = 'JSON redirect changed domain'
                    continue
                raw = (EVIDENCE / f'official-{key}.body').read_text(encoding='utf-8-sig')
                source_rows = json.loads(raw)
                future, reachable = collect_raw(source_rows, module, now, days, stop_at_cutoff)
                verification['json_rows'] = len(source_rows)
                verification['reachable'] = len(reachable)
                verification['future'] = future
                verification['prior_missing'] = []
                prior = keyed(items(current_rss))
                for record in future:
                    record['main_rss'] = prior.get(record['url'])
                try:
                    baseline = run(module, raw, now, work / 'unchanged.xml')
                    verification['baseline'] = len(baseline)
                    verification['baseline_new_count'] = len(set(keyed(baseline)) - set(prior))
                    verification['baseline_missing_count'] = len(set(prior) - set(keyed(baseline)))
                    verification['identical_main'] = (work / 'unchanged.xml').read_bytes() == current_rss.read_bytes()
                    verification['baseline_future'] = sorted(set(keyed(baseline)) & {x['url'] for x in future})
                except Exception as exc:
                    verification['baseline_error'] = f'{type(exc).__name__}: {exc}'
                    baseline = None
                if midnight:
                    # Remove just the future list rows in a separate simulation.
                    # Keep each original scope, cutoff, ordering and pubDate conventions.
                    due = [
                        r for r in source_rows
                        if r['is_category_index'] or r['is_keitai_page'] or
                        datetime.fromisoformat(r['publish_datetime']) <= now
                    ]
                    if baseline is not None:
                        only_due = run(module, json.dumps(due), now, work / 'only-due.xml')
                        extra = [r for r in only_due if r['url'] not in keyed(baseline)]
                        verification['freed_slots'] = [dict(r, already_in_main=r['url'] in prior) for r in extra]
                    continue

                prototype = candidate_for(module)
                candidate_path = work / 'preserved.xml'
                candidate_path.write_bytes(current_rss.read_bytes())
                try:
                    proposed = run(prototype, raw, now, candidate_path)
                    verification['approved_patch'] = len(proposed)
                    verification['approved_identical_baseline'] = proposed == baseline
                    verification['approved_matches_main'] = candidate_path.read_bytes() == current_rss.read_bytes()
                    if baseline is None:
                        verification['prior_missing'] = [r for r in proposed if r['url'] not in prior]
                    # Render a separate untruncated source to audit old GUIDs and the inclusion boundary.
                    uncapped = candidate_for(module)
                    uncapped.MAX_ITEMS = len(source_rows)
                    all_due = run(uncapped, raw, now, work / 'uncapped.xml')
                    try:
                        deferred = {r['url'] for r in future} - set(keyed(all_due))
                        guard_exact_rss(list(prior.values()), all_due, proposed,
                                        now - timedelta(days=days), deferred, prototype.MAX_ITEMS)
                        verification['enhanced_guard'] = 'PASS'
                    except ValueError as exc:
                        verification['enhanced_guard'] = str(exc)
                    new_urls = set(keyed(proposed)) - set(prior)
                    missing_urls = set(prior) - set(keyed(proposed))
                    verification['snapshot_additions'] = [r for r in proposed if r['url'] in new_urls]
                    verification['snapshot_removals'] = [
                        dict(r, still_in_source=r['url'] in reachable)
                        for r in prior.values() if r['url'] in missing_urls
                    ]
                except Exception as exc:
                    verification['approved_error'] = f'{type(exc).__name__}: {exc}'
    (EVIDENCE / 'json-validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print('Validated', len(result), 'sources and', len(REPRESENTATIVES), 'fixture representatives')


def run_fixtures():
    now = datetime(2026, 11, 27, 18, 30, tzinfo=JST)
    exact_sources = ('1464', '1496', '1541', '1557', '1561', '1578',
                     '1667', '1670', '1683', '1691', '1695')
    for key in sorted(set(REPRESENTATIVES) | set(exact_sources)):
        script = next(REPO.glob(f'scrape_municipality_{key}_*.py'))
        code = script.read_text()
        module = load_module(script)
        days = int(code.split('timedelta(days=')[1].split(')')[0])
        midnight = 'astimezone(JST).replace(hour=0' in code
        with TemporaryDirectory() as temporary:
            checks = fixtures(module, days, midnight, 'if date < cutoff: break' in code,
                              now, Path(temporary))
        print(key, json.dumps(checks, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures-only', action='store_true', help='Run offline synthetic checks')
    if parser.parse_args().fixtures_only:
        run_fixtures()
    else:
        main()
