"""Exercise publication against local bare remotes; never the real repository."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import publish_sapporo_consultation as p
import scrape_sapporo_consultation as m
from test_safety import FIX, NOW, records


class Publication(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.remote = self.root / 'remote.git'
        self.repo = self.root / 'repo'
        self.writer = self.root / 'writer'
        subprocess.run(['git', 'init', '--bare', '--initial-branch=main', str(self.remote)], check=True, capture_output=True)
        subprocess.run(['git', 'clone', str(self.remote), str(self.repo)], check=True, capture_output=True)
        for name in ['scrape_sapporo_consultation.py', 'publish_sapporo_consultation.py']:
            (self.repo / name).write_text('tested implementation\n')
        (self.repo / m.FILE).write_bytes((FIX / 'initial3.xml').read_bytes())
        self.commit(self.repo, 'Initial tested baseline')
        p.git(self.repo, 'push', 'origin', 'main')
        subprocess.run(['git', 'clone', str(self.remote), str(self.writer)], check=True, capture_output=True)
        self.before = (FIX / 'initial3.xml').read_bytes()

    def commit(self, repo, message):
        p.git(repo, 'add', '.')
        p.git(repo, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', message)

    def generate(self, repo, output):
        return p.build(repo, output, fixtures=FIX, now=NOW)

    def remote_bytes(self):
        return subprocess.run(['git', '--git-dir', str(self.remote), 'show', 'main:' + m.FILE], check=True, capture_output=True).stdout

    def advance_other_file(self, attempt, work):
        if attempt == 1:
            (self.writer / 'other-feed.xml').write_text('another scheduled workflow update')
            self.commit(self.writer, 'Concurrent unrelated update')
            p.git(self.writer, 'push', 'origin', 'main')

    def test_single_file_publish_then_no_change(self):
        result = p.publish(self.repo, generate=self.generate)
        self.assertEqual((result['status'], result['attempt']), ('pushed', 1))
        self.assertEqual(len(m.validate(m.ET.fromstring(self.remote_bytes()))), 4)
        self.assertEqual(p.publish(self.repo, generate=self.generate)['status'], 'unchanged')
        self.assertEqual((self.repo / m.FILE).read_bytes(), self.before)
        paths = subprocess.run(['git', '--git-dir', str(self.remote), 'diff-tree', '--no-commit-id', '--name-only', '-r', 'main'], check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertEqual(paths, [m.FILE])

    def test_unrelated_push_race_regenerates_from_fresh_main(self):
        result = p.publish(self.repo, generate=self.generate, before_push=self.advance_other_file)
        self.assertEqual((result['status'], result['attempt']), ('pushed', 2))
        content = subprocess.run(['git', '--git-dir', str(self.remote), 'show', 'main:other-feed.xml'], check=True, capture_output=True, text=True).stdout
        self.assertIn('another scheduled', content)

    def test_same_feed_race_keeps_newer_revision_history(self):
        def concurrent(attempt, work):
            if attempt != 1:
                return
            data, _ = m.generate(self.before, records(), NOW)
            batch = records()
            batch[0]['lines'][0] += '（要予約）'
            year, month = 2026, 11
            batch[0]['fingerprint'] = m.digest(m.normalize(f'{year}-{month}|{batch[0]["label"]}|' + '|'.join(batch[0]['lines'])))
            data, _ = m.generate(data, batch, NOW)
            (self.writer / m.FILE).write_bytes(data)
            self.commit(self.writer, 'Concurrent newer revision')
            p.git(self.writer, 'push', 'origin', 'main')
        result = p.publish(self.repo, generate=self.generate, before_push=concurrent)
        items = m.validate(m.ET.fromstring(self.remote_bytes()))
        self.assertEqual((result['status'], result['attempt'], len(items)), ('pushed', 2, 6))
        self.assertIn('r4', items[0].findtext('title'))

    def test_implementation_changed_on_main_stops_retry(self):
        def concurrent(attempt, work):
            (self.writer / 'scrape_sapporo_consultation.py').write_text('changed code')
            self.commit(self.writer, 'Changed production implementation')
            p.git(self.writer, 'push', 'origin', 'main')
        with self.assertRaisesRegex(ValueError, 'implementation changed'):
            p.publish(self.repo, generate=self.generate, before_push=concurrent)
        self.assertEqual(self.before, self.remote_bytes())

    def test_uncommitted_code_rejected(self):
        (self.repo / 'scrape_sapporo_consultation.py').write_text('uncommitted')
        with self.assertRaisesRegex(ValueError, 'uncommitted'):
            p.publish(self.repo, generate=self.generate)
        self.assertEqual(self.before, self.remote_bytes())

    def test_unexpected_output_rejected(self):
        def generate(repo, output):
            result = self.generate(repo, output)
            (output / 'other.xml').write_text('unexpected')
            return result
        with self.assertRaisesRegex(ValueError, 'unexpected publication output'):
            p.publish(self.repo, generate=generate)
        self.assertEqual(self.before, self.remote_bytes())

    def test_partial_or_broken_output_cannot_publish(self):
        def generate(repo, output):
            output.mkdir()
            (output / m.FILE).write_bytes(b'broken')
        with self.assertRaises(m.ET.ParseError):
            p.publish(self.repo, generate=generate)
        self.assertEqual(self.before, self.remote_bytes())

    def test_source_fetch_failure_cannot_publish(self):
        def generate(repo, output):
            raise TimeoutError('source failed')
        with self.assertRaises(TimeoutError):
            p.publish(self.repo, generate=generate)
        self.assertEqual(self.before, self.remote_bytes())

    def test_valid_but_truncated_ledger_cannot_publish(self):
        data, _ = m.generate(self.before, records(), NOW)
        (self.repo / m.FILE).write_bytes(data)
        self.commit(self.repo, 'Retained actual revision')
        p.git(self.repo, 'push', 'origin', 'main')
        def generate(repo, output):
            output.mkdir()
            (output / m.FILE).write_bytes(self.before) # Valid RSS, but drops r2.
        with self.assertRaisesRegex(ValueError, 'history changed or disappeared'):
            p.publish(self.repo, generate=generate)
        self.assertEqual(data, self.remote_bytes())

    def test_repeated_conflict_stops_without_ours_overwriting(self):
        def concurrent(attempt, work):
            (self.writer / 'other-feed.xml').write_text(str(attempt))
            self.commit(self.writer, f'Concurrent update {attempt}')
            p.git(self.writer, 'push', 'origin', 'main')
        with self.assertRaisesRegex(RuntimeError, 'advanced repeatedly'):
            p.publish(self.repo, generate=self.generate, before_push=concurrent)
        self.assertEqual(self.before, self.remote_bytes())
        self.assertEqual(p.git(self.repo, 'worktree', 'list', '--porcelain').stdout.count('worktree '), 1)

    def test_non_conflict_push_error_stops_without_retry(self):
        hook = self.remote / 'hooks' / 'pre-receive'
        hook.write_text('#!/bin/sh\nexit 1\n');hook.chmod(0o755)
        with self.assertRaisesRegex(RuntimeError, 'push failed without main advance'):
            p.publish(self.repo, generate=self.generate)
        self.assertEqual(self.before, self.remote_bytes())


if __name__ == '__main__':
    unittest.main()
