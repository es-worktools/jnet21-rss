import copy
from datetime import date, datetime
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from support_shiga import production as p, search
from support_shiga import publish as pub

REPO = Path(__file__).resolve().parents[2]
DAY = date(2026, 11, 6)


class BundleSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.pages = search.fetch_window(p.START, DAY, fixtures=REPO / 'validation/fixtures')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.repo = self.home / 'repo'
        shutil.copytree(REPO / 'validation/candidate', self.repo / 'validation/candidate')
        self.n = 0

    def build(self, policy=None, rows=None, day=DAY):
        self.n += 1
        output = self.home / f'output-{self.n}'
        with patch.object(search, 'fetch_window', return_value=(copy.deepcopy(rows if rows is not None else self.rows), self.pages)) as fetch:
            result = p.build_bundle(self.repo, output, policy, day)
        self.assertEqual(fetch.call_args.args[:2], (p.START, day))
        return output, result

    def install(self, output):
        for rel in p.ALLOWLIST:
            dest = self.repo / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(output / rel, dest)

    def baseline(self, policy='archive-summary'):
        output, result = self.build(policy)
        self.install(output)
        return result

    def bytes(self):
        return {str(f.relative_to(self.repo)): f.read_bytes() for f in self.repo.rglob('*') if f.is_file()}

    def test_both_approved_policies_preserve_all_437_candidates(self):
        for policy in p.POLICIES:
            with self.subTest(policy=policy):
                output, result = self.build(policy)
                self.assertEqual(sum(result['archive_counts'].values()), 437)
                self.assertEqual(sum(result['live_counts'].values()), 437 if policy == 'full-history' else 3)
                for label, slug in search.CATEGORIES.items():
                    original = (self.repo / f'validation/candidate/support-0205-shiga-{slug}.xml').read_bytes()
                    self.assertEqual((output / p.paths(slug)[1]).read_bytes(), original)
                    self.assertEqual((output / p.paths(slug)[2]).read_text().count('<tr>'), len(p.items(original, label)) + 1)
                self.assertFalse((self.repo / p.STATE).exists())

    def test_repeat_is_byte_identical_and_never_reannounces_seed(self):
        self.baseline()
        before = self.bytes()
        output, result = self.build()
        for rel in p.ALLOWLIST:
            self.assertEqual((self.repo / rel).read_bytes(), (output / rel).read_bytes())
        self.assertEqual(sum(result['new_counts'].values()), 0)
        self.assertEqual(before, self.bytes())

    def test_new_items_all_categories_and_late_historical_discovery(self):
        self.baseline()
        rows = copy.deepcopy(self.rows)
        for n, label in enumerate(search.CATEGORIES):
            rows.append(dict(category=label, date='2026-09-04', title='後から掲載された過去日記事',
                             url=f'https://www.pref.shiga.lg.jp/test/{990000+n}.html'))
        output, result = self.build(rows=rows)
        self.assertEqual(list(result['new_counts'].values()), [1, 1, 1])
        self.assertEqual(sum(result['archive_counts'].values()), 440)
        self.assertEqual(sum(result['live_counts'].values()), 6)
        for label, slug in search.CATEGORIES.items():
            live, archive, _ = p.paths(slug)
            p.preserve((self.repo / archive).read_bytes(), (output / archive).read_bytes())
            p.preserve((self.repo / live).read_bytes(), (output / live).read_bytes())
            newest = ET.fromstring((output / live).read_bytes()).find('./channel/item')
            self.assertEqual(newest.findtext('pubDate'), 'Fri, 04 Sep 2026 00:00:00 +0900')

    def test_first_run_already_new_items_are_also_delivered(self):
        rows = copy.deepcopy(self.rows)
        rows.append(dict(category='募集', date='2026-11-06', title='追加', url='https://www.pref.shiga.lg.jp/test/990000.html'))
        _, result = self.build('archive-summary', rows)
        self.assertEqual(sum(result['archive_counts'].values()), 438)
        self.assertEqual(sum(result['live_counts'].values()), 4)

    def test_source_deletion_title_date_edits_and_reclassification_keep_items(self):
        self.baseline()
        rows = copy.deepcopy(self.rows)
        changed = next(r for r in rows if r['category'] == 'お知らせ')
        url = changed['url']
        changed.update(category='イベント', title='修正タイトル', date='2026-11-05')
        rows.pop(10)
        output, result = self.build(rows=rows)
        self.assertEqual(sum(result['archive_counts'].values()), 437)
        self.assertEqual(sum(result['new_counts'].values()), 0)
        self.assertEqual(result['category_changes'][0]['url'], url)
        for slug in search.CATEGORIES.values():
            live, archive, _ = p.paths(slug)
            self.assertEqual((output / archive).read_bytes(), (self.repo / archive).read_bytes())
            self.assertEqual((output / live).read_bytes(), (self.repo / live).read_bytes())

    def test_missing_policy_partial_baseline_and_changed_policy_fail(self):
        with self.assertRaises(ValueError):
            self.build()
        path = self.repo / p.OUTPUTS[0]
        path.write_bytes(b'partial')
        with self.assertRaises(ValueError):
            self.build('archive-summary')
        path.unlink()
        self.baseline()
        with self.assertRaises(ValueError):
            self.build('full-history')

    def test_corrupt_missing_and_empty_files_fail_without_touching_source(self):
        self.baseline()
        for rel in p.ALLOWLIST:
            path = self.repo / rel
            saved = path.read_bytes()
            for invalid in (b'', b'broken'):
                path.write_bytes(invalid)
                before = self.bytes()
                with self.assertRaises((ValueError, ET.ParseError)):
                    self.build()
                self.assertEqual(before, self.bytes())
            path.write_bytes(saved)
        path = self.repo / p.OUTPUTS[0]
        path.unlink()
        before = self.bytes()
        with self.assertRaises(FileNotFoundError):
            self.build()
        self.assertEqual(before, self.bytes())

    def test_seed_tamper_and_clock_rollback_fail(self):
        self.baseline()
        with self.assertRaises(ValueError):
            self.build(day=date(2026, 11, 5))
        seed = self.repo / 'validation/candidate/support-0205-shiga-notice.xml'
        seed.write_bytes(seed.read_bytes() + b' ')
        before = self.bytes()
        with self.assertRaises(ValueError):
            self.build()
        self.assertEqual(before, self.bytes())

    def test_execution_day_uses_jst_and_start_remains_fixed(self):
        class Clock(datetime):
            @classmethod
            def now(cls, tz):
                self.assertEqual(str(tz), 'Asia/Tokyo')
                return datetime(2026, 11, 7, 0, 1, tzinfo=tz)
        with patch.object(p, 'datetime', Clock), patch.object(search, 'fetch_window', return_value=(self.rows, self.pages)) as fetch:
            p.build_bundle(self.repo, self.home / 'jst', 'archive-summary')
        self.assertEqual(fetch.call_args.args[:2], (p.START, date(2026, 11, 7)))

    def test_http_and_staging_failure_leave_every_source_byte_unchanged(self):
        self.baseline()
        before = self.bytes()
        with patch.object(search, 'fetch_window', side_effect=OSError('HTTP 503')):
            with self.assertRaises(OSError):
                p.build_bundle(self.repo, self.home / 'failed')
        self.assertEqual(before, self.bytes())
        original = Path.write_bytes
        def fail_second_xml(path, data):
            if path.name == 'support-0205-shiga-event.xml' and 'stage-failure' in str(path):
                raise OSError('disk full after earlier files')
            return original(path, data)
        with patch.object(search, 'fetch_window', return_value=(self.rows, self.pages)), patch.object(Path, 'write_bytes', fail_second_xml):
            with self.assertRaises(OSError):
                p.build_bundle(self.repo, self.home / 'stage-failure')
        self.assertEqual(before, self.bytes())


class GitTransaction(unittest.TestCase):
    # Integration cases use real local Git repositories and a bare main remote.
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.pages = search.fetch_window(p.START, DAY, fixtures=REPO / 'validation/fixtures')

    def setUp(self):
        BundleSafety.setUp(self)
        for rel in pub.CODE_PATHS:
            dest = self.repo / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / rel, dest)
        (self.repo / 'municipality-existing.xml').write_text('unrelated RSS original')
        pub.git(self.repo, 'init', '-b', 'main')
        pub.git(self.repo, 'config', 'user.name', 'local-test')
        pub.git(self.repo, 'config', 'user.email', 'local-test@example.invalid')
        pub.git(self.repo, 'add', '.')
        pub.git(self.repo, 'commit', '-m', 'Initial implementation and unrelated RSS')
        self.remote = self.home / 'remote.git'
        pub.git(self.repo, 'init', '--bare', str(self.remote))
        pub.git(self.repo, 'remote', 'add', 'origin', str(self.remote))
        pub.git(self.repo, 'push', 'origin', 'main')
        self.initial = pub.git(self.repo, 'rev-parse', 'HEAD').stdout.strip()

    def generator(self, work, stage, policy=None):
        with patch.object(search, 'fetch_window', return_value=(self.rows, self.pages)):
            return p.build_bundle(work, stage, policy, DAY)

    def tip(self):
        return pub.git(self.remote, 'rev-parse', 'refs/heads/main').stdout.strip()

    def competitor(self, mode):
        other = self.home / ('competitor-' + str(self.n))
        self.n += 1
        pub.git(self.repo, 'clone', '--branch', 'main', str(self.remote), str(other))
        pub.git(other, 'config', 'user.name', 'competitor')
        pub.git(other, 'config', 'user.email', 'competitor@example.invalid')
        if mode == 'rss':
            (other / 'municipality-existing.xml').write_text('concurrent municipality auto-update')
        elif mode == 'code':
            target = other / 'support_shiga/search.py'
            target.write_text(target.read_text() + '\n# newer implementation\n')
        elif mode == 'shiga':
            rows = copy.deepcopy(self.rows)
            rows.append(dict(category='募集', date='2026-11-06', title='Concurrent Shiga article', url='https://www.pref.shiga.lg.jp/test/999999.html'))
            with patch.object(search, 'fetch_window', return_value=(rows, self.pages)):
                stage = self.home / ('concurrent-bundle-' + str(self.n))
                p.build_bundle(other, stage, 'archive-summary', DAY)
            for rel in p.ALLOWLIST:
                target = other / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(stage / rel, target)
        pub.git(other, 'add', '.')
        pub.git(other, 'commit', '-m', 'Concurrent change')
        pub.git(other, 'push', 'origin', 'main')
        return pub.git(other, 'rev-parse', 'HEAD').stdout.strip()

    def test_transaction_commits_exact_allowlist_and_unchanged_run_does_not_commit(self):
        result = pub.publish(self.repo, 'archive-summary', generate=self.generator)
        self.assertEqual(result['status'], 'pushed')
        names = pub.git(self.remote, 'diff', '--name-only', self.initial, self.tip()).stdout.splitlines()
        self.assertEqual(set(names), set(p.ALLOWLIST))
        tip = self.tip()
        repeat = pub.publish(self.repo, generate=self.generator)
        self.assertEqual(repeat['status'], 'unchanged')
        self.assertEqual(tip, self.tip())

    def test_partial_generation_or_corrupt_third_feed_never_commits(self):
        def fail(work, stage, policy=None):
            self.generator(work, stage, policy)
            (stage / p.paths('recruit')[0]).write_bytes(b'broken third feed')
            return {}
        with self.assertRaises(ValueError):
            pub.publish(self.repo, 'archive-summary', generate=fail)
        self.assertEqual(self.initial, self.tip())
        def disk_failure(work, stage, policy=None):
            stage.mkdir()
            (stage / p.paths('notice')[0]).write_text('partial output')
            raise OSError('disk full')
        with self.assertRaises(OSError):
            pub.publish(self.repo, 'archive-summary', generate=disk_failure)
        self.assertEqual(self.initial, self.tip())

    def test_competing_municipality_update_is_retained_on_retry(self):
        def race(attempt, work):
            if attempt == 1:
                self.competitor('rss')
        result = pub.publish(self.repo, 'archive-summary', generate=self.generator, before_push=race)
        self.assertEqual(result['attempt'], 2)
        self.assertEqual(pub.git(self.remote, 'show', 'main:municipality-existing.xml').stdout,
                         'concurrent municipality auto-update')

    def test_competing_shiga_history_is_regenerated_and_never_lost(self):
        def race(attempt, work):
            if attempt == 1:
                self.competitor('shiga')
        result = pub.publish(self.repo, 'archive-summary', generate=self.generator, before_push=race)
        self.assertEqual(result['attempt'], 2)
        data = pub.git(self.remote, 'show', 'main:archive/support-0205-shiga-recruit.xml').stdout
        self.assertIn('999999.html', data)
        self.assertEqual(len(ET.fromstring(data).findall('./channel/item')), 37)

    def test_implementation_change_stops_instead_of_running_old_code(self):
        def race(attempt, work):
            if attempt == 1:
                self.competitor('code')
        with self.assertRaisesRegex(ValueError, 'implementation changed'):
            pub.publish(self.repo, 'archive-summary', generate=self.generator, before_push=race)
        self.assertIn('newer implementation', pub.git(self.remote, 'show', 'main:support_shiga/search.py').stdout)
        self.assertNotEqual(self.initial, self.tip())

    def test_repeated_competition_stops_after_bounded_retries(self):
        def race(attempt, work):
            other = self.home / ('churn-' + str(attempt))
            pub.git(self.repo, 'clone', '--branch', 'main', str(self.remote), str(other))
            pub.git(other, 'config', 'user.name', 'churn')
            pub.git(other, 'config', 'user.email', 'churn@example.invalid')
            (other / 'municipality-existing.xml').write_text(f'auto-update {attempt}')
            pub.git(other, 'add', '.')
            pub.git(other, 'commit', '-m', 'Another RSS update')
            pub.git(other, 'push', 'origin', 'main')
        with self.assertRaisesRegex(RuntimeError, 'changed repeatedly'):
            pub.publish(self.repo, 'archive-summary', attempts=2, generate=self.generator, before_push=race)
        self.assertEqual(pub.git(self.remote, 'show', 'main:municipality-existing.xml').stdout, 'auto-update 2')
        self.assertEqual(pub.git(self.remote, 'ls-tree', 'main', p.STATE).stdout, '')


if __name__ == '__main__':
    unittest.main(verbosity=2)
