"""Publish one validated ledger, regenerating from fresh main after push races.

Follows support_shiga/publish.py; never rebases generated history or force pushes.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from scrape_sapporo_consultation import FILE, TZ, run, validate, preserve_history, ET

CODE_PATHS = ('scrape_sapporo_consultation.py', 'publish_sapporo_consultation.py',
              '.github/workflows/update-sapporo-consultation.yml',
              'tests/sapporo_consultation')


def git(repo, *args, check=True):
    return subprocess.run(['git', '-C', str(repo), *args], check=check,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def build(repo, output, fixtures=None, now=None):
    repo, output = Path(repo).resolve(), Path(output).resolve()
    if output == repo or repo in output.parents:
        raise ValueError('preview must be outside the source checkout')
    source = repo / FILE
    validate(ET.fromstring(source.read_bytes()))
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, output / FILE)
    return run(output, fixtures=fixtures, now=now)


def publish(repo, attempts=3, generate=build, before_push=None):
    repo = Path(repo).resolve()
    code_ref = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    if git(repo, 'status', '--porcelain', '--', *CODE_PATHS).stdout:
        raise ValueError('tested implementation is uncommitted')
    for attempt in range(1, attempts + 1):
        git(repo, 'fetch', 'origin', 'main')
        base = git(repo, 'rev-parse', 'refs/remotes/origin/main').stdout.strip()
        if git(repo, 'diff', '--name-only', code_ref, base, '--', *CODE_PATHS).stdout:
            raise ValueError('implementation changed on main; restart with tested latest code')
        with tempfile.TemporaryDirectory(prefix='sapporo-transaction-') as temp:
            work, stage = Path(temp) / 'checkout', Path(temp) / 'output'
            git(repo, 'worktree', 'add', '--detach', str(work), base)
            try:
                result = generate(work, stage)
                if {p.name for p in stage.iterdir()} != {FILE}:
                    raise ValueError('unexpected publication output')
                validate(ET.fromstring((stage / FILE).read_bytes()))
                preserve_history((work / FILE).read_bytes(), (stage / FILE).read_bytes())
                shutil.copyfile(stage / FILE, work / FILE)
                git(work, 'add', '--', FILE)
                changed = git(work, 'diff', '--cached', '--name-only').stdout.splitlines()
                if not set(changed) <= {FILE}:
                    raise ValueError('unexpected staged path')
                if not changed:
                    return dict(status='unchanged', attempt=attempt, base=base, result=result)
                git(work, '-c', 'user.name=github-actions[bot]',
                    '-c', 'user.email=41898282+github-actions[bot]@users.noreply.github.com',
                    'commit', '-m', 'Update Sapporo consultation schedule RSS')
                commit = git(work, 'rev-parse', 'HEAD').stdout.strip()
                if before_push:
                    before_push(attempt, work)
                pushed = git(work, 'push', 'origin', 'HEAD:refs/heads/main', check=False)
                if pushed.returncode == 0:
                    return dict(status='pushed', attempt=attempt, base=base, commit=commit, result=result)
                git(repo, 'fetch', 'origin', 'main')
                if git(repo, 'rev-parse', 'refs/remotes/origin/main').stdout.strip() == base:
                    raise RuntimeError('push failed without main advance: ' + pushed.stderr)
            finally:
                git(repo, 'worktree', 'remove', '--force', str(work), check=False)
    raise RuntimeError('main advanced repeatedly; no remote history overwritten')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, default=Path('.'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--fixtures', type=Path)
    parser.add_argument('--at', type=datetime.fromisoformat)
    args = parser.parse_args()
    if args.publish:
        if args.output or args.fixtures or args.at:
            parser.error('publishing cannot use output, fixtures or a date override')
        if os.environ.get('GITHUB_REF') != 'refs/heads/main':
            parser.error('publishing requires the main workflow')
        result = publish(args.repo)
    else:
        if args.output is None:
            parser.error('--output required for preview')
        result = build(args.repo, args.output, args.fixtures, args.at)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
