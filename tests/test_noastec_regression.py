"""Historical XML and exact workflow-shell regression tests; no internet access."""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

import scrape_noastec as s
import stage_noastec as stage
from test_noastec_safety import response

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/noastec_fixtures'
HASHES = {
    'noastec-seminar.xml': 'ef35b868e615be99478723d56929158fc7f504068d924381a376083ddda362df',
    'noastec-pressrelease.xml': 'd7702c434e4df00dd930aea8175b223b67128a0f0f07352bc6ac0368b307bbde',
    'noastec-subsidy.xml': '98e9e677f728d6a6544df1fb91dff4e943d008ed6a43544415b842709297d7e7',
}


def historical_html(c, new=False):
    root = ET.fromstring((FIXTURES / c['output']).read_bytes())
    soup = '<h1>' + c['label'] + '</h1>'
    from html import escape
    for item in root.findall('./channel/item'):
        soup += '<a href="' + escape(item.findtext('link'), quote=True) + '">' + escape(item.findtext('title')) + '</a>'
    if new:
        soup += '<a href="' + c['url'] + '/post_999999.html">検証用の新記事</a>'
    return soup.encode()


class HistoricalRegression(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.d = Path(self.temp.name)
        for c in s.FEEDS:
            (self.d / c['output']).write_bytes((FIXTURES / c['output']).read_bytes())
        self.before = {c['output']: (self.d / c['output']).read_bytes() for c in s.FEEDS}

    def tearDown(self):
        self.temp.cleanup()

    def run_mock(self, mode='ok'):
        def get(url, **kw):
            c = next(c for c in s.FEEDS if c['url'] == url)
            status = 403 if mode == '403' or (mode == 'mixed' and c == s.FEEDS[0]) else 200
            return response(c, historical_html(c, new=True), status=status)
        with contextlib.redirect_stdout(io.StringIO()):
            return s.run(self.d, get)

    def test_historical_29_exact_hashes_and_no_dates(self):
        total = 0
        for c in s.FEEDS:
            data = self.before[c['output']]
            self.assertEqual(hashlib.sha256(data).hexdigest(), HASHES[c['output']])
            root, items, minimum = s.read_baseline(self.d / c['output'], c)
            self.assertEqual(len(items), c['minimum'])
            self.assertEqual(minimum, c['minimum'])
            self.assertFalse(root.findall('.//pubDate'))
            self.assertFalse(root.findall('.//lastBuildDate'))
            total += len(items)
        self.assertEqual(total, 29)

    def test_all_403_preserves_all_original_bytes_and_stages_nothing(self):
        result = self.run_mock('403')
        self.assertEqual([r['code'] for r in result['results']], ['HTTP_ERROR'] * 3)
        for filename, data in self.before.items():
            self.assertEqual((self.d / filename).read_bytes(), data)
        (self.d / 'noastec-status.json').write_text(json.dumps(result))
        self.assertEqual(stage.verified_files(self.d), [])

    def test_mixed_failure_retains_historical_category(self):
        result = self.run_mock('mixed')
        self.assertEqual([r['status'] for r in result['results']], ['failed', 'updated', 'updated'])
        self.assertEqual((self.d / s.FEEDS[0]['output']).read_bytes(), self.before[s.FEEDS[0]['output']])
        (self.d / 'noastec-status.json').write_text(json.dumps(result))
        self.assertEqual(stage.verified_files(self.d), [c['output'] for c in s.FEEDS[1:]])

    def test_success_preserves_all_29_items_without_invented_dates(self):
        result = self.run_mock()
        self.assertTrue(all(r['status'] == 'updated' for r in result['results']))
        for c in s.FEEDS:
            filename = c['output']
            old = ET.fromstring(self.before[filename]).findall('./channel/item')
            root = ET.fromstring((self.d / filename).read_bytes())
            items = {i.findtext('guid'): i for i in root.findall('./channel/item')}
            self.assertEqual(len(items), c['minimum'] + 1)
            for item in old:
                self.assertEqual(ET.tostring(item), ET.tostring(items[item.findtext('guid')]))
            self.assertFalse(root.findall('.//pubDate'))
            self.assertFalse(root.findall('.//lastBuildDate'))

    def test_historical_rerun_is_idempotent(self):
        self.run_mock()
        first = {c['output']: (self.d / c['output']).read_bytes() for c in s.FEEDS}
        result = self.run_mock()
        self.assertEqual([r['status'] for r in result['results']], ['unchanged'] * 3)
        self.assertEqual(first, {c['output']: (self.d / c['output']).read_bytes() for c in s.FEEDS})

    def test_change_during_fetch_is_not_overwritten(self):
        c = s.FEEDS[0]
        path = self.d / c['output']
        changed = self.before[c['output']] + b'\n<!-- newer writer -->'
        def get(*args, **kwargs):
            path.write_bytes(changed)
            return response(c, historical_html(c, new=True))
        with self.assertRaises(s.GuardError) as exc:
            s.process_feed(c, self.d, get)
        self.assertEqual(exc.exception.code, 'CONCURRENT_CHANGE')
        self.assertEqual(path.read_bytes(), changed)
        self.assertFalse(list(self.d.glob('.*.tmp')))

    def test_undersized_baseline_is_rejected_before_network(self):
        c = s.FEEDS[0]
        root = ET.fromstring(self.before[c['output']])
        channel = root.find('channel')
        channel.remove(channel.find('item'))
        (self.d / c['output']).write_bytes(ET.tostring(root))
        with self.assertRaises(s.GuardError) as exc:
            s.process_feed(c, self.d, lambda *a, **kw: self.fail('network called'))
        self.assertEqual(exc.exception.code, 'BASELINE_ERROR')

    def test_chmod_failure_keeps_original(self):
        c = s.FEEDS[0]
        with patch.object(s.os, 'chmod', side_effect=OSError('chmod failed')):
            with self.assertRaises(OSError):
                s.process_feed(c, self.d, lambda *a, **kw: response(c, historical_html(c, True)))
        self.assertEqual((self.d / c['output']).read_bytes(), self.before[c['output']])
        self.assertFalse(list(self.d.glob('.*.tmp')))

    def test_wrong_channel_identity_is_rejected(self):
        c = s.FEEDS[0]
        path = self.d / c['output']
        path.write_bytes(self.before[c['output']].replace(c['url'].encode(), b'https://example.org/', 1))
        with self.assertRaises(s.GuardError):
            s.read_baseline(path, c)

    def test_invalid_source_count_is_rejected(self):
        c = s.FEEDS[0]
        for count in ['0', '-1', 'eleven', '9999']:
            with self.subTest(count=count):
                root = ET.fromstring(self.before[c['output']])
                ET.SubElement(root.find('channel'), s.SOURCE_COUNT).text = count
                (self.d / c['output']).write_bytes(ET.tostring(root))
                with self.assertRaises(s.GuardError):
                    s.read_baseline(self.d / c['output'], c)

    def test_candidate_with_deleted_item_is_rejected(self):
        c = s.FEEDS[0]
        root, items, minimum = s.read_baseline(self.d / c['output'], c)
        root.find('channel').remove(root.find('./channel/item'))
        with self.assertRaises(s.GuardError):
            s.validate_candidate(ET.tostring(root), items)

    def test_candidate_with_changed_old_title_is_rejected(self):
        c = s.FEEDS[0]
        root, items, minimum = s.read_baseline(self.d / c['output'], c)
        root = copy.deepcopy(root)
        root.find('./channel/item/title').text = 'changed'
        with self.assertRaises(s.GuardError):
            s.validate_candidate(ET.tostring(root), items)

    def test_invalid_xml_character_cannot_be_saved(self):
        c = s.FEEDS[0]
        body = historical_html(c, True).replace('検証用の新記事'.encode(), b'invalid\x01title')
        with self.assertRaises(ET.ParseError):
            s.process_feed(c, self.d, lambda *a, **kw: response(c, body))
        self.assertEqual((self.d / c['output']).read_bytes(), self.before[c['output']])

    def test_cli_all_failures_exit_one_and_write_complete_receipt(self):
        real = s.run
        def run(directory):
            return real(directory, lambda url, **kw: response(next(c for c in s.FEEDS if c['url'] == url), status=403))
        summary = self.d / 'noastec-status.json'
        with patch.object(sys, 'argv', ['script', '--directory', str(self.d), '--summary', str(summary)]), patch.object(s, 'run', side_effect=run), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(s.main(), 1)
        receipt = json.loads(summary.read_text())
        self.assertTrue(receipt['complete'])
        self.assertEqual(len(receipt['results']), 3)
        self.assertEqual(stage.verified_files(self.d), [])

    def test_stale_receipt_removed_if_generation_crashes(self):
        summary = self.d / 'noastec-status.json'
        summary.write_text('{"complete": true}')
        with patch.object(sys, 'argv', ['script', '--summary', str(summary)]), patch.object(s, 'run', side_effect=RuntimeError('crash')):
            with self.assertRaises(RuntimeError):
                s.main()
        self.assertFalse(summary.exists())

    def test_receipt_category_set_is_exact(self):
        result = self.run_mock()
        for mode in ['missing', 'duplicate', 'unknown', 'status']:
            bad = copy.deepcopy(result)
            if mode == 'missing': bad['results'].pop()
            if mode == 'duplicate': bad['results'][-1] = bad['results'][0]
            if mode == 'unknown': bad['results'][-1]['file'] = '../other.xml'
            if mode == 'status': bad['results'][-1]['status'] = 'accepted'
            (self.d / 'noastec-status.json').write_text(json.dumps(bad))
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                stage.verified_files(self.d)


class WorkflowGitRegression(unittest.TestCase):
    """Run the workflow's actual commit shell against a local bare remote."""
    def command(self, directory, *args, check=True):
        return subprocess.run(args, cwd=directory, text=True, capture_output=True, check=check)

    def git(self, directory, *args, check=True):
        return self.command(directory, 'git', *args, check=check)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.top = Path(self.temp.name)
        self.remote = self.top / 'remote.git'
        self.seed = self.top / 'seed'
        self.worker = self.top / 'worker'
        self.other = self.top / 'other'
        self.seed.mkdir()
        self.git(self.top, 'init', '--bare', '-b', 'main', str(self.remote))
        self.git(self.seed, 'init', '-b', 'main')
        self.identity(self.seed)
        for c in s.FEEDS:
            (self.seed / c['output']).write_bytes((FIXTURES / c['output']).read_bytes())
        (self.seed / 'unrelated.xml').write_text('keep original\n')
        (self.seed / 'scrape_noastec.py').write_bytes((ROOT / 'scrape_noastec.py').read_bytes())
        self.git(self.seed, 'add', '.')
        self.git(self.seed, 'commit', '-m', 'historical baseline')
        self.git(self.seed, 'remote', 'add', 'origin', str(self.remote))
        self.git(self.seed, 'push', 'origin', 'main')
        for directory in [self.worker, self.other]:
            self.git(self.top, 'clone', str(self.remote), str(directory))
            self.identity(directory)
        self.initial = self.remote_head()
        self.before = {c['output']: (self.worker / c['output']).read_bytes() for c in s.FEEDS}
        workflow = (ROOT / '.github/workflows/update-noastec.yml').read_text()
        section = workflow.split('      - name: Commit successful RSS files\n', 1)[1]
        section = section.split('        run: |\n', 1)[1].split('\n      - name:', 1)[0]
        self.commit_shell = textwrap.dedent(section)

    def identity(self, directory):
        self.git(directory, 'config', 'user.name', 'Local Validation')
        self.git(directory, 'config', 'user.email', 'validation@example.invalid')

    def tearDown(self):
        self.temp.cleanup()

    def remote_head(self):
        return self.git(self.remote, 'rev-parse', 'main').stdout.strip()

    def generate(self, mode='mixed'):
        def get(url, **kw):
            c = next(c for c in s.FEEDS if c['url'] == url)
            failed = mode == '403' or (mode == 'mixed' and c == s.FEEDS[0])
            return response(c, historical_html(c, True), status=403 if failed else 200)
        with contextlib.redirect_stdout(io.StringIO()):
            result = s.run(self.worker, get)
        (self.worker / 'noastec-status.json').write_text(json.dumps(result))
        return result

    def stage(self, check=True):
        return self.command(self.worker, sys.executable, str(ROOT / 'stage_noastec.py'), check=check)

    def publish(self):
        return self.command(self.worker, 'bash', '-e', '-o', 'pipefail', '-c', self.commit_shell, check=False)

    def upstream(self, filename, value):
        path = self.other / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
        self.git(self.other, 'add', '--', filename)
        self.git(self.other, 'commit', '-m', 'parallel update')
        self.git(self.other, 'push', 'origin', 'main')

    def test_all_403_produces_no_commit_or_push(self):
        self.generate('403')
        self.stage()
        self.assertEqual(self.publish().returncode, 0)
        self.assertEqual(self.remote_head(), self.initial)
        for name, data in self.before.items():
            self.assertEqual((self.worker / name).read_bytes(), data)

    def test_mixed_success_publishes_only_two_categories(self):
        self.generate()
        self.stage()
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        paths = self.git(self.remote, 'diff', '--name-only', self.initial, 'main').stdout.splitlines()
        self.assertEqual(set(paths), {c['output'] for c in s.FEEDS[1:]})
        failed = s.FEEDS[0]['output']
        self.assertEqual(self.git(self.remote, 'show', 'main:' + failed).stdout.encode(), self.before[failed])

    def test_unrelated_update_is_retained_by_rebase(self):
        self.generate()
        self.stage()
        self.upstream('unrelated.xml', 'parallel new value\n')
        upstream = self.remote_head()
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.git(self.remote, 'show', 'main:unrelated.xml').stdout, 'parallel new value\n')
        self.assertEqual(self.git(self.remote, 'rev-parse', 'main^').stdout.strip(), upstream)

    def test_upstream_noastec_xml_change_aborts_publication(self):
        self.generate()
        self.stage()
        filename = s.FEEDS[1]['output']
        self.upstream(filename, self.before[filename].decode() + '\n<!-- upstream newer XML -->')
        upstream = self.remote_head()
        result = self.publish()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('refusing to publish a stale result', result.stdout)
        self.assertEqual(self.remote_head(), upstream)

    def test_upstream_noastec_code_change_aborts_publication(self):
        self.generate()
        self.stage()
        self.upstream('scrape_noastec.py', '# newer code\n')
        upstream = self.remote_head()
        self.assertNotEqual(self.publish().returncode, 0)
        self.assertEqual(self.remote_head(), upstream)

    def test_upstream_new_fixture_aborts_publication(self):
        self.generate()
        self.stage()
        self.upstream('tests/noastec_fixtures/new.xml', 'new fixture\n')
        upstream = self.remote_head()
        self.assertNotEqual(self.publish().returncode, 0)
        self.assertEqual(self.remote_head(), upstream)

    def test_pre_staged_unrelated_change_aborts_staging(self):
        self.generate()
        (self.worker / 'unrelated.xml').write_text('must not publish\n')
        self.git(self.worker, 'add', 'unrelated.xml')
        result = self.stage(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.git(self.worker, 'diff', '--cached', '--name-only').stdout.splitlines(), ['unrelated.xml'])
        self.assertEqual(self.remote_head(), self.initial)

    def test_tampered_receipt_stages_nothing(self):
        self.generate('ok')
        (self.worker / s.FEEDS[1]['output']).write_text('tampered')
        self.assertNotEqual(self.stage(check=False).returncode, 0)
        self.assertEqual(self.git(self.worker, 'diff', '--cached', '--name-only').stdout, '')

    def test_missing_receipt_stages_nothing(self):
        self.assertNotEqual(self.stage(check=False).returncode, 0)
        self.assertEqual(self.git(self.worker, 'diff', '--cached', '--name-only').stdout, '')

    def test_push_race_rejected_without_force_or_remote_data_loss(self):
        self.generate()
        self.stage()
        hook = self.worker / '.git/hooks/pre-push'
        quoted = shlex.quote(str(self.other))
        hook.write_text('#!/bin/sh\nset -e\n' +
            f"printf '%s\\n' 'late update' > {quoted}/unrelated.xml\n" +
            f'git -C {quoted} add unrelated.xml\n' +
            f"git -C {quoted} commit -m 'late parallel update' >/dev/null\n" +
            f'git -C {quoted} push origin main >/dev/null\n')
        hook.chmod(0o755)
        result = self.publish()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.git(self.remote, 'show', 'main:unrelated.xml').stdout, 'late update\n')
        self.assertEqual(self.git(self.remote, 'rev-list', '--count', 'main').stdout.strip(), '2')
        for filename, data in self.before.items():
            self.assertEqual(self.git(self.remote, 'show', 'main:' + filename).stdout.encode(), data)


if __name__ == '__main__':
    unittest.main()
