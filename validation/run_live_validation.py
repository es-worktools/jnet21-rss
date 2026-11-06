"""Read-only GitHub Actions check. All RSS writes are in a temp directory."""
from datetime import date
import hashlib
import json
from pathlib import Path
import tempfile
import shiga_candidate as shiga
import sapporo_supplement as sapporo

with tempfile.TemporaryDirectory() as tmp:
    base = Path(tmp)
    sg = shiga.run(base/'shiga', date(2026,9,3), date(2026,11,6), bootstrap=True)
    sp = sapporo.run(base/'sapporo', bootstrap=True)
    repeated = sapporo.run(base/'sapporo')
    if repeated['added'] != 0:
        raise RuntimeError('unexpected second-fetch schedule change; review required')
    for label, slug in shiga.CATEGORIES.items():
        path = base/'shiga'/f'support-0205-shiga-{slug}.xml'
        before = path.read_bytes()
        if shiga.candidate(label, [r for r in sg['rows'] if r['category']==label], before) != before:
            raise RuntimeError('unchanged Shiga source changed RSS')
    receipt = {
        'shiga_counts': sg['counts'], 'shiga_pages': sg['pages'],
        'shiga_url_count': len({r['url'] for r in sg['rows']}),
        'sapporo_added': sp['added'], 'sapporo_total': sp['total'],
        'sapporo_repeat_added': repeated['added'],
        'sapporo_fingerprints': [r['fingerprint'] for r in sp['records']],
        'rss_sha256': {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in base.rglob('*.xml')},
        'production_write': False,
    }
    print('VALIDATION_RESULT_JSON ' + json.dumps(receipt, ensure_ascii=False))
