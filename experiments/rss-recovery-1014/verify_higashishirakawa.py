"""Isolated proof of concept: no production writes, no automatic fallback/switch."""
import argparse
import copy
import hashlib
import html as escaping
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.request import Request, build_opener, HTTPRedirectHandler
from xml.etree import ElementTree as ET
from lxml import html

OFFICIAL = 'https://www.vill.higashishirakawa.gifu.jp/'
SIMPLE = 'http://www.50913.ne.jp/higashishirakawa/index.html'
WELFARE = urljoin(SIMPLE, 'sonfuku.html')
JST = timezone(timedelta(hours=9))
PRODUCTION_NAME = 'municipality-1014-higashishirakawa.xml'
DATE_TITLE = re.compile(r'^(20\d{2})\.(\d{1,2})\.(\d{1,2})\s*(.+)$')

def norm(text):
    return re.sub(r'\s+', ' ', text or '').strip()

def match_title(text):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', text or ''))

def checked_url(url):
    p = urlparse(url)
    if p.username or p.password or p.port or p.params or p.query:
        raise RuntimeError('Unexpected URL components: ' + url)
    if p.scheme == 'https' and p.netloc == 'www.vill.higashishirakawa.gifu.jp':
        return url
    if p.scheme == 'http' and p.netloc == 'www.50913.ne.jp' and p.path.startswith('/higashishirakawa/') and '..' not in p.path:
        return url
    raise RuntimeError('Unapproved source: ' + url)

class RestrictedRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        checked_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

class Fetcher:
    def __init__(self, evidence):
        self.evidence = Path(evidence)
        self.evidence.mkdir(parents=True, exist_ok=True)
        self.manifest = []
        self.opener = build_opener(RestrictedRedirect())

    def get(self, url):
        checked_url(url)
        plain_url = urldefrag(url)[0]
        with self.opener.open(Request(plain_url, headers={'User-Agent': 'Mozilla/5.0 JNet21-RSS-validation'}), timeout=40) as r:
            checked_url(r.url)
            body = r.read(8_000_001)
            if len(body) > 8_000_000:
                raise RuntimeError('Response too large')
            if r.status != 200:
                raise RuntimeError('Unexpected status')
            entry = dict(url=url, final_url=r.url, status=r.status, size=len(body), sha256=hashlib.sha256(body).hexdigest(), checked_at=datetime.now(JST).isoformat(), content_type=r.headers.get('Content-Type'))
        name = hashlib.sha256(plain_url.encode()).hexdigest()[:16] + '.bin'
        (self.evidence / name).write_bytes(body)
        entry['file'] = name
        self.manifest.append(entry)
        (self.evidence / 'manifest.json').write_text(json.dumps(self.manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        return body

def authority(body):
    doc = html.fromstring(body)
    links = [urljoin(OFFICIAL, a) for a in doc.xpath('//a/@href')]
    if SIMPLE not in links or 'メンテナンス' not in doc.text_content():
        raise RuntimeError('Current official maintenance notice does not authorize the simple site; manual review required')

def section_for(doc, fragment):
    anchors = doc.xpath('//a[@name=$key or @id=$key]', key=fragment)
    if len(anchors) != 1:
        raise RuntimeError('Missing/ambiguous article anchor: ' + fragment)
    for parent in anchors[0].iterancestors('div'):
        if 'hpb-lay-photo1' in parent.get('class', '').split():
            return parent
    raise RuntimeError('Article section changed')

def parse_index(body):
    doc = html.fromstring(body)
    if '東白川村公式ホームページ(簡易版)' not in doc.xpath('string(//title)'):
        raise RuntimeError('Unexpected simple page identity')
    candidates = []
    seen = set()
    # Date-prefixed list entries, never event dates from headings or PDF names.
    notice_lists = doc.xpath('//div[@id="Layer9"]/ul')
    if len(notice_lists) != 1:
        raise RuntimeError('Dated notice list layout changed')
    entries = notice_lists[0].xpath('./li')
    if not entries or any(len(li.xpath('./a[@href]')) != 1 for li in entries):
        raise RuntimeError('Notice row missing a unique article link')
    for a in notice_lists[0].xpath('./li/a[@href]'):
        title = norm(a.text_content())
        m = DATE_TITLE.fullmatch(title)
        if not m:
            raise RuntimeError('Undated/changed notice entry: ' + title)
        y, month, day = map(int, m.groups()[:3])
        date = datetime(y, month, day, tzinfo=JST)
        if date > datetime.now(JST):
            raise RuntimeError('Future publication date requires review')
        url = checked_url(urljoin(SIMPLE, a.get('href')))
        p = urlparse(url)
        if urldefrag(url)[0] != SIMPLE or not p.fragment:
            raise RuntimeError('Notice URL layout changed')
        if url in seen:
            raise RuntimeError('Duplicate notice URL')
        seen.add(url)
        section = section_for(doc, p.fragment)
        headings = section.xpath('.//td[contains(@class,"hpb-subh02-cell1")]')
        if len(headings) != 1 or match_title(m.group(4)) not in match_title(headings[0].text_content()):
            raise RuntimeError('Notice title does not match article section')
        pdfs = [checked_url(urljoin(SIMPLE, u)) for u in section.xpath('.//a/@href') if urlparse(u).path.lower().endswith('.pdf')]
        text = norm(section.text_content())
        if not pdfs or len(text) < 50:
            raise RuntimeError('Article body/attachment missing')
        candidates.append(dict(title=norm(m.group(4)), url=url, date=date.isoformat(), date_source='official dated notice list', body=text, pdfs=sorted(set(pdfs))))
    if not candidates:
        raise RuntimeError('No dated notices; preserve previous feed')
    local_pages = sorted(set(checked_url(urljoin(SIMPLE, u)) for u in doc.xpath('//a/@href') if u.lower().endswith('.html') and not u.startswith(('mailto:', 'tel:'))))
    if local_pages != [WELFARE]:
        raise RuntimeError('Simple site page inventory changed; review coverage')
    return candidates

def parse_welfare(body):
    doc = html.fromstring(body)
    headings = [norm(x.text_content()) for x in doc.xpath('//td[contains(@class,"hpb-subh02-cell1")]')]
    if '戸籍の郵送請求' not in headings:
        raise RuntimeError('Welfare page structure changed')
    pdfs = sorted(set(checked_url(urljoin(WELFARE, u)) for u in doc.xpath('//a/@href') if urlparse(u).path.lower().endswith('.pdf')))
    if not pdfs:
        raise RuntimeError('Welfare PDF missing')
    return dict(title='戸籍の郵送請求', url=WELFARE, date=None, disposition='reference-only: no publication date, not a dated news notice', pdfs=pdfs)

def description(row):
    links = ''.join('<li><a href="' + escaping.escape(u, quote=True) + '">' + escaping.escape(u.rsplit('/',1)[-1]) + '</a></li>' for u in row['pdfs'])
    return '<p>公式簡易版による暫定監視。掲載範囲は限定されています。</p><p>' + escaping.escape(row['body']) + '</p><ul>' + links + '</ul>'

def merge(baseline_bytes, candidates):
    root = ET.fromstring(baseline_bytes)
    channel = root.find('channel')
    if root.tag != 'rss' or channel is None or channel.findtext('title') != '1014_岐阜県東白川村':
        raise RuntimeError('Unexpected baseline feed identity')
    existing = channel.findall('item')
    if not existing:
        raise RuntimeError('Empty baseline is not safe')
    result = copy.deepcopy(root)
    out = result.find('channel')
    by_guid = {}
    by_title_date = {}
    for item in out.findall('item'):
        guid = item.findtext('guid')
        if not guid or guid in by_guid:
            raise RuntimeError('Missing or duplicate baseline GUID')
        checked_url(item.findtext('link'))
        date = parsedate_to_datetime(item.findtext('pubDate'))
        by_guid[guid] = item
        by_title_date.setdefault((match_title(item.findtext('title')), date.date().isoformat()), []).append(item)
    added, aliases, updated = [], [], []
    for row in candidates:
        date = datetime.fromisoformat(row['date'])
        if date.tzinfo is None:
            raise RuntimeError('Date timezone missing')
        candidates_by_title = by_title_date.get((match_title(row['title']), date.date().isoformat()), [])
        if row['url'] in by_guid:
            item = by_guid[row['url']]
            if match_title(item.findtext('title')) != match_title(row['title']) or parsedate_to_datetime(item.findtext('pubDate')).date() != date.date():
                raise RuntimeError('Existing temporary URL reused for another title/date; review required')
            updated.append(row['url'])
        elif len(candidates_by_title) == 1:
            item = candidates_by_title[0]
            aliases.append(dict(simple_url=row['url'], retained_guid=item.findtext('guid'), title=row['title'], date=date.date().isoformat()))
        elif candidates_by_title:
            raise RuntimeError('Ambiguous title/date match')
        else:
            item = ET.SubElement(out, 'item')
            ET.SubElement(item, 'title').text = row['title']
            ET.SubElement(item, 'link').text = row['url']
            ET.SubElement(item, 'guid', isPermaLink='true').text = row['url']
            ET.SubElement(item, 'pubDate').text = format_datetime(date)
            by_guid[row['url']] = item
            by_title_date.setdefault((match_title(row['title']), date.date().isoformat()), []).append(item)
            added.append({k:v for k,v in row.items() if k != 'body'})
        item.find('link').text = row['url']
        desc = item.find('description')
        if desc is None:
            desc = ET.SubElement(item, 'description')
        desc.text = description(row)
    # Preserve every baseline GUID/date. No truncation during temporary operation.
    for old in existing:
        new = by_guid.get(old.findtext('guid'))
        if new is None or new.findtext('pubDate') != old.findtext('pubDate'):
            raise RuntimeError('Baseline retention failed')
    items = out.findall('item')
    for item in items:
        out.remove(item)
    for item in sorted(items, key=lambda x: parsedate_to_datetime(x.findtext('pubDate')), reverse=True):
        out.append(item)
    out.find('description').text = '1014_岐阜県東白川村 暫定検証RSS：公式簡易版の掲載情報を補完。通常サイトの全情報は網羅しません。'
    xml = ET.tostring(result, encoding='utf-8', xml_declaration=True)
    if len(ET.fromstring(xml).findall('./channel/item')) < len(existing):
        raise RuntimeError('Output lost baseline items')
    return xml, dict(baseline_count=len(existing), dated_notices=len(candidates), added=added, aliases=aliases, updated=updated, output_count=len(items), preserved_baseline_guids=True)

def safe_write(path, payload):
    path = Path(path)
    if path.name == PRODUCTION_NAME:
        raise RuntimeError('Prototype refuses production output filename')
    ET.fromstring(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_bytes(payload)
    tmp.replace(path)

def run(baseline, output, evidence, fixtures=None):
    if Path(output).resolve() == Path(baseline).resolve() or Path(output).name == PRODUCTION_NAME:
        raise RuntimeError('Prototype output must be isolated')
    if fixtures:
        folder = Path(fixtures)
        official = (folder/'official-home.html').read_bytes()
        index = (folder/'simple-index.html').read_bytes()
        welfare = (folder/'sonfuku.html').read_bytes()
        authority(official)
        rows = parse_index(index)
        ref = parse_welfare(welfare)
        def get_pdf(u): return (folder/u.rsplit('/',1)[-1]).read_bytes()
    else:
        f = Fetcher(evidence)
        authority(f.get(OFFICIAL))
        rows = parse_index(f.get(SIMPLE))
        ref = parse_welfare(f.get(WELFARE))
        get_pdf = f.get
    pdfs = sorted(set(u for row in rows + [ref] for u in row['pdfs']))
    for u in pdfs:
        data = get_pdf(u)
        if not data.startswith(b'%PDF-') or len(data) < 100:
            raise RuntimeError('Attachment not a valid PDF response: ' + u)
    payload, report = merge(Path(baseline).read_bytes(), rows)
    report.update(reference_only=[ref], pdfs_verified=pdfs, automatic_switchback=False, scope='Limited to explicitly listed dated notices; not full normal-site coverage')
    # Output is untouched until all sources, structure, PDFs, baseline and XML pass.
    safe_write(output, payload)
    Path(str(output)+'.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--baseline', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--evidence', required=True)
    p.add_argument('--fixtures')
    a = p.parse_args()
    run(a.baseline, a.output, a.evidence, a.fixtures)
