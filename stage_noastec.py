"""Stage only outputs authorized by a complete, hash-verified run receipt."""
import hashlib
import json
from pathlib import Path
import subprocess
from scrape_noastec import FEEDS


def verified_files(directory):
    summary = json.loads((directory / 'noastec-status.json').read_text())
    expected = {c['output'] for c in FEEDS}
    results = summary.get('results', [])
    if summary.get('schema') != 1 or summary.get('complete') is not True:
        raise ValueError('incomplete run receipt')
    if len(results) != len(expected) or {r['file'] for r in results} != expected:
        raise ValueError('missing/duplicate/unknown category receipt')
    files = []
    for row in results:
        if row['status'] not in {'updated', 'unchanged', 'failed'}:
            raise ValueError('unknown category status')
        if row['status'] != 'failed':
            actual = hashlib.sha256((directory / row['file']).read_bytes()).hexdigest()
            if actual != row['sha256']:
                raise ValueError('output changed after validation')
        if row['status'] == 'updated':
            files.append(row['file'])
    return files


def main():
    files = verified_files(Path('.'))
    # All receipts are checked before making ANY index mutation.
    staged = subprocess.check_output(['git', 'diff', '--cached', '--name-only', '-z'])
    if staged:
        raise ValueError('index is not empty; refusing to include pre-staged files')
    if files:
        subprocess.run(['git', 'add', '--', *files], check=True)
    print('Validated categories staged:', ', '.join(files) or '(none)')


if __name__ == '__main__':
    main()
