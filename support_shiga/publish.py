"""Commit only complete Shiga bundles; retry fast-forward conflicts from fresh main."""
import argparse
from datetime import date
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from .production import ALLOWLIST, POLICIES, build_bundle, load_baseline

CODE_PATHS = (
    'support_shiga/__init__.py', 'support_shiga/search.py',
    'support_shiga/production.py', 'support_shiga/publish.py',
    '.github/workflows/update-support-0205-shiga.yml',
    *(f'validation/candidate/support-0205-shiga-{s}.xml' for s in ('notice', 'event', 'recruit')),
)


def git(repo, *args, check=True):
    return subprocess.run(['git', '-C', str(repo), *args], check=check,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def publish(repo, policy=None, attempts=3, generate=build_bundle, before_push=None):
    repo = Path(repo).resolve()
    code_ref = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    # A caller must test and commit the exact code it is about to execute.
    if git(repo, 'status', '--porcelain', '--', *CODE_PATHS).stdout:
        raise ValueError('production implementation is uncommitted')
    for attempt in range(1, attempts + 1):
        git(repo, 'fetch', 'origin', 'main')
        base = git(repo, 'rev-parse', 'refs/remotes/origin/main').stdout.strip()
        if git(repo, 'diff', '--name-only', code_ref, base, '--', *CODE_PATHS).stdout:
            raise ValueError('production implementation changed on main; restart with latest code')
        with tempfile.TemporaryDirectory(prefix='shiga-transaction-') as temp:
            work = Path(temp) / 'checkout'
            stage = Path(temp) / 'bundle'
            git(repo, 'worktree', 'add', '--detach', str(work), base)
            try:
                result = generate(work, stage, policy=policy)
                actual = {str(p.relative_to(stage)) for p in stage.rglob('*') if p.is_file()}
                if actual != set(ALLOWLIST):
                    raise ValueError('incomplete bundle or unexpected output path')
                load_baseline(stage, policy)
                for path in ALLOWLIST:
                    dest = work / path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(stage / path, dest)
                git(work, 'add', '--', *ALLOWLIST)
                changed = git(work, 'diff', '--cached', '--name-only').stdout.splitlines()
                if not set(changed) <= set(ALLOWLIST):
                    raise ValueError('unexpected staged file')
                if not changed:
                    return {'status': 'unchanged', 'attempt': attempt, 'base': base, 'result': result}
                git(work, '-c', 'user.name=github-actions[bot]',
                    '-c', 'user.email=41898282+github-actions[bot]@users.noreply.github.com',
                    'commit', '-m', 'Update Shiga supplemental RSS transaction')
                commit = git(work, 'rev-parse', 'HEAD').stdout.strip()
                if before_push:
                    before_push(attempt, work)
                pushed = git(work, 'push', 'origin', f'HEAD:refs/heads/main', check=False)
                if pushed.returncode == 0:
                    return {'status': 'pushed', 'attempt': attempt, 'base': base, 'commit': commit, 'result': result}
                # Never rebase previously generated files over newer Shiga history.
                # Regenerate every file against the new main instead; no force-push.
                git(repo, 'fetch', 'origin', 'main')
                tip = git(repo, 'rev-parse', 'refs/remotes/origin/main').stdout.strip()
                if tip == base:
                    raise RuntimeError('push failed without a concurrent main update: ' + pushed.stderr)
            finally:
                git(repo, 'worktree', 'remove', '--force', str(work), check=False)
    raise RuntimeError('main changed repeatedly; stopped without overwriting remote history')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, default=Path('.'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--bootstrap-policy', choices=POLICIES)
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--fixtures', type=Path)
    parser.add_argument('--today', type=date.fromisoformat)
    args = parser.parse_args()
    if args.publish:
        if args.fixtures or args.today or args.output:
            parser.error('publishing cannot use fixtures, a date override, or an output override')
        if os.environ.get('GITHUB_REF') != 'refs/heads/main':
            parser.error('publishing is permitted only by the main workflow')
        result = publish(args.repo, args.bootstrap_policy)
    else:
        if not args.output:
            parser.error('--output is required for a non-publishing build')
        result = build_bundle(args.repo, args.output, args.bootstrap_policy, args.today, fixtures=args.fixtures)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
